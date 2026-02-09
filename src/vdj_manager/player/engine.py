"""UI-agnostic playback engine using python-vlc.

This module has ZERO Qt dependencies. It can be wrapped by FastAPI
for a web frontend or used directly from tests.
"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from vdj_manager.core.models import Song


class PlaybackState(str, Enum):
    """Playback state enumeration."""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass
class TrackInfo:
    """Lightweight track reference for the player queue.

    Decoupled from Song model -- only needs what the player needs.
    """

    file_path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration_s: float = 0.0
    bpm: Optional[float] = None
    key: Optional[str] = None
    energy: Optional[int] = None
    mood: Optional[str] = None
    rating: Optional[int] = None
    cue_points: list[dict] = field(default_factory=list)

    @classmethod
    def from_song(cls, song: "Song") -> "TrackInfo":
        """Create TrackInfo from a VDJ Song model."""
        cues = []
        for poi in song.cue_points:
            cues.append({
                "pos": poi.pos,
                "name": poi.name or f"Cue {poi.num or ''}".strip(),
                "num": poi.num,
            })

        return cls(
            file_path=song.file_path,
            title=(song.tags.title or "") if song.tags else "",
            artist=(song.tags.author or "") if song.tags else "",
            album=(song.tags.album or "") if song.tags else "",
            duration_s=(song.infos.song_length or 0.0) if song.infos else 0.0,
            bpm=song.actual_bpm,
            key=(song.tags.key or None) if song.tags else None,
            energy=song.energy,
            mood=song.mood,
            rating=(song.tags.rating or None) if song.tags else None,
            cue_points=cues,
        )

    def to_dict(self) -> dict:
        """Serialize to dict for API responses."""
        return {
            "file_path": self.file_path,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration_s": self.duration_s,
            "bpm": self.bpm,
            "key": self.key,
            "energy": self.energy,
            "mood": self.mood,
            "rating": self.rating,
            "cue_points": self.cue_points,
        }


class PlaybackEngine:
    """Manages VLC playback, queue, history, and play counts.

    Thread-safe. All public methods can be called from any thread.
    State changes are delivered via registered callbacks (not Qt signals).
    """

    def __init__(self) -> None:
        self._vlc_instance = None
        self._media_player = None
        self._lock = threading.RLock()

        # State
        self._state = PlaybackState.STOPPED
        self._current_track: Optional[TrackInfo] = None
        self._position_s: float = 0.0
        self._duration_s: float = 0.0
        self._volume: int = 80
        self._speed: float = 1.0
        self._is_muted: bool = False
        self._initialized: bool = False

        # Queue & history
        self._queue: list[TrackInfo] = []
        self._queue_index: int = -1
        self._history: list[TrackInfo] = []
        self._max_history: int = 100
        self._shuffle: bool = False
        self._repeat_mode: str = "none"  # "none", "one", "all"

        # Callbacks (observer pattern for API-readiness)
        self._on_state_change: list[Callable] = []
        self._on_track_change: list[Callable] = []
        self._on_position_change: list[Callable] = []
        self._on_queue_change: list[Callable] = []
        self._on_track_finished: list[Callable] = []

        # Position polling thread
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_running = False

    # --- Lifecycle ---

    def initialize(self) -> bool:
        """Create VLC instance. Returns False if VLC not found."""
        try:
            import vlc

            self._vlc_instance = vlc.Instance("--no-xlib", "--quiet")
            self._media_player = self._vlc_instance.media_player_new()

            # Register VLC end-reached event
            em = self._media_player.event_manager()
            em.event_attach(
                vlc.EventType.MediaPlayerEndReached, self._on_vlc_end_reached
            )

            self._initialized = True
            return True
        except (ImportError, OSError, AttributeError):
            self._initialized = False
            return False

    @property
    def is_initialized(self) -> bool:
        """Whether VLC was successfully initialized."""
        return self._initialized

    def shutdown(self) -> None:
        """Release VLC resources."""
        self._stop_position_polling()
        with self._lock:
            if self._media_player is not None:
                self._media_player.stop()
                self._media_player.release()
                self._media_player = None
            if self._vlc_instance is not None:
                self._vlc_instance.release()
                self._vlc_instance = None
            self._initialized = False

    # --- Playback control ---

    def play(self, track: Optional[TrackInfo] = None) -> None:
        """Play track (or resume if no track given)."""
        with self._lock:
            if not self._initialized:
                return

            if track is not None:
                self._load_track(track)
                self._media_player.play()
                self._set_state(PlaybackState.PLAYING)
                self._start_position_polling()
            elif self._state == PlaybackState.PAUSED:
                self._media_player.play()
                self._set_state(PlaybackState.PLAYING)
                self._start_position_polling()
            elif self._state == PlaybackState.STOPPED and self._current_track:
                self._load_track(self._current_track)
                self._media_player.play()
                self._set_state(PlaybackState.PLAYING)
                self._start_position_polling()

    def pause(self) -> None:
        """Pause playback."""
        with self._lock:
            if not self._initialized:
                return
            if self._state == PlaybackState.PLAYING:
                self._media_player.pause()
                self._set_state(PlaybackState.PAUSED)

    def stop(self) -> None:
        """Stop playback."""
        with self._lock:
            if not self._initialized:
                return
            self._media_player.stop()
            self._stop_position_polling()
            self._position_s = 0.0
            self._set_state(PlaybackState.STOPPED)
            self._fire_position_callbacks()

    def toggle_play_pause(self) -> None:
        """Toggle between play and pause."""
        if self._state == PlaybackState.PLAYING:
            self.pause()
        else:
            self.play()

    def seek(self, position_s: float) -> None:
        """Seek to position in seconds."""
        with self._lock:
            if not self._initialized or self._media_player is None:
                return
            duration_ms = self._media_player.get_length()
            if duration_ms > 0:
                pos_ms = int(position_s * 1000)
                self._media_player.set_time(max(0, min(pos_ms, duration_ms)))
                self._position_s = position_s
                self._fire_position_callbacks()

    def seek_relative(self, delta_s: float) -> None:
        """Seek relative to current position."""
        self.seek(self._position_s + delta_s)

    # --- Volume / speed ---

    def set_volume(self, vol: int) -> None:
        """Set volume (0-100)."""
        with self._lock:
            self._volume = max(0, min(100, vol))
            if self._initialized and self._media_player:
                self._media_player.audio_set_volume(self._volume)

    def get_volume(self) -> int:
        """Get current volume."""
        return self._volume

    def set_speed(self, speed: float) -> None:
        """Set playback speed (0.5-2.0)."""
        with self._lock:
            self._speed = max(0.5, min(2.0, speed))
            if self._initialized and self._media_player:
                self._media_player.set_rate(self._speed)

    def get_speed(self) -> float:
        """Get current playback speed."""
        return self._speed

    def toggle_mute(self) -> None:
        """Toggle mute state."""
        with self._lock:
            self._is_muted = not self._is_muted
            if self._initialized and self._media_player:
                self._media_player.audio_set_mute(self._is_muted)

    @property
    def is_muted(self) -> bool:
        """Whether audio is muted."""
        return self._is_muted

    # --- Queue management ---

    def set_queue(self, tracks: list[TrackInfo], start_index: int = 0) -> None:
        """Set the playback queue and optionally start playing."""
        with self._lock:
            self._queue = list(tracks)
            self._queue_index = max(0, min(start_index, len(self._queue) - 1)) if self._queue else -1
            self._fire_queue_callbacks()
            if self._queue and 0 <= self._queue_index < len(self._queue):
                self.play(self._queue[self._queue_index])

    def add_to_queue(self, track: TrackInfo) -> None:
        """Add a track to the end of the queue."""
        with self._lock:
            self._queue.append(track)
            self._fire_queue_callbacks()

    def remove_from_queue(self, index: int) -> None:
        """Remove a track from the queue by index."""
        with self._lock:
            if 0 <= index < len(self._queue):
                self._queue.pop(index)
                # Adjust current index if needed
                if index < self._queue_index:
                    self._queue_index -= 1
                elif index == self._queue_index:
                    self._queue_index = min(self._queue_index, len(self._queue) - 1)
                self._fire_queue_callbacks()

    def reorder_queue(self, from_idx: int, to_idx: int) -> None:
        """Move a track within the queue."""
        with self._lock:
            if (
                0 <= from_idx < len(self._queue)
                and 0 <= to_idx < len(self._queue)
                and from_idx != to_idx
            ):
                track = self._queue.pop(from_idx)
                self._queue.insert(to_idx, track)
                # Update current index
                if from_idx == self._queue_index:
                    self._queue_index = to_idx
                elif from_idx < self._queue_index <= to_idx:
                    self._queue_index -= 1
                elif to_idx <= self._queue_index < from_idx:
                    self._queue_index += 1
                self._fire_queue_callbacks()

    def clear_queue(self) -> None:
        """Clear the queue."""
        with self._lock:
            self._queue.clear()
            self._queue_index = -1
            self._fire_queue_callbacks()

    def next_track(self) -> None:
        """Advance to the next track in the queue."""
        with self._lock:
            if not self._queue:
                return
            if self._shuffle:
                remaining = [
                    i for i in range(len(self._queue)) if i != self._queue_index
                ]
                if remaining:
                    self._queue_index = random.choice(remaining)
                elif self._repeat_mode == "all":
                    self._queue_index = random.randint(0, len(self._queue) - 1)
                else:
                    return
            elif self._queue_index + 1 < len(self._queue):
                self._queue_index += 1
            elif self._repeat_mode == "all":
                self._queue_index = 0
            else:
                return
            self.play(self._queue[self._queue_index])
            self._fire_queue_callbacks()

    def previous_track(self) -> None:
        """Go to the previous track in the queue."""
        with self._lock:
            if not self._queue:
                return
            # If more than 3 seconds in, restart current track
            if self._position_s > 3.0 and self._current_track:
                self.seek(0)
                return
            if self._queue_index > 0:
                self._queue_index -= 1
            elif self._repeat_mode == "all":
                self._queue_index = len(self._queue) - 1
            else:
                self.seek(0)
                return
            self.play(self._queue[self._queue_index])
            self._fire_queue_callbacks()

    def shuffle_queue(self) -> None:
        """Toggle shuffle mode."""
        with self._lock:
            self._shuffle = not self._shuffle

    @property
    def is_shuffle(self) -> bool:
        """Whether shuffle mode is active."""
        return self._shuffle

    def set_repeat_mode(self, mode: str) -> None:
        """Set repeat mode: 'none', 'one', 'all'."""
        if mode in ("none", "one", "all"):
            self._repeat_mode = mode

    @property
    def repeat_mode(self) -> str:
        """Current repeat mode."""
        return self._repeat_mode

    # --- State getters (for API serialization) ---

    @property
    def state(self) -> PlaybackState:
        """Current playback state."""
        return self._state

    @property
    def current_track(self) -> Optional[TrackInfo]:
        """Currently loaded track."""
        return self._current_track

    @property
    def position(self) -> float:
        """Current playback position in seconds."""
        return self._position_s

    @property
    def duration(self) -> float:
        """Duration of current track in seconds."""
        return self._duration_s

    @property
    def queue(self) -> list[TrackInfo]:
        """Current queue (copy)."""
        return list(self._queue)

    @property
    def queue_index(self) -> int:
        """Index of current track in queue."""
        return self._queue_index

    @property
    def history(self) -> list[TrackInfo]:
        """Play history (most recent first)."""
        return list(self._history)

    def get_state(self) -> dict:
        """Return full player state as a serializable dict (API-ready)."""
        return {
            "state": self._state.value,
            "current_track": self._current_track.to_dict() if self._current_track else None,
            "position_s": self._position_s,
            "duration_s": self._duration_s,
            "volume": self._volume,
            "speed": self._speed,
            "is_muted": self._is_muted,
            "shuffle": self._shuffle,
            "repeat_mode": self._repeat_mode,
            "queue_index": self._queue_index,
            "queue_length": len(self._queue),
        }

    def get_queue_list(self) -> list[dict]:
        """Return queue as list of dicts."""
        return [t.to_dict() for t in self._queue]

    def get_history_list(self) -> list[dict]:
        """Return history as list of dicts."""
        return [t.to_dict() for t in self._history]

    # --- Observer pattern ---

    def on_state_change(self, callback: Callable) -> None:
        """Register callback for state changes. Receives (PlaybackState)."""
        self._on_state_change.append(callback)

    def on_track_change(self, callback: Callable) -> None:
        """Register callback for track changes. Receives (TrackInfo)."""
        self._on_track_change.append(callback)

    def on_position_change(self, callback: Callable) -> None:
        """Register callback for position changes. Receives (float, float)."""
        self._on_position_change.append(callback)

    def on_queue_change(self, callback: Callable) -> None:
        """Register callback for queue changes. Receives (list[TrackInfo])."""
        self._on_queue_change.append(callback)

    def on_track_finished(self, callback: Callable) -> None:
        """Register callback for track completion. Receives (TrackInfo)."""
        self._on_track_finished.append(callback)

    # --- Internal ---

    def _load_track(self, track: TrackInfo) -> None:
        """Load a track into VLC media player."""
        if self._media_player is None or self._vlc_instance is None:
            return

        # Add current track to history before switching
        if self._current_track is not None and self._state != PlaybackState.STOPPED:
            self._add_to_history(self._current_track)

        self._current_track = track
        media = self._vlc_instance.media_new(track.file_path)
        self._media_player.set_media(media)
        self._position_s = 0.0
        self._duration_s = track.duration_s

        # Apply current settings
        self._media_player.audio_set_volume(self._volume)
        self._media_player.set_rate(self._speed)

        self._fire_track_callbacks()

    def _add_to_history(self, track: TrackInfo) -> None:
        """Add a track to play history."""
        self._history.insert(0, track)
        if len(self._history) > self._max_history:
            self._history = self._history[: self._max_history]

    def _set_state(self, new_state: PlaybackState) -> None:
        """Update state and fire callbacks."""
        if self._state != new_state:
            self._state = new_state
            self._fire_state_callbacks()

    def _on_vlc_end_reached(self, event) -> None:
        """VLC event: track ended."""
        # Fire track finished callbacks (for play count)
        if self._current_track:
            for cb in self._on_track_finished:
                try:
                    cb(self._current_track)
                except Exception:
                    logger.warning("track_finished callback error", exc_info=True)

        # Handle repeat mode
        if self._repeat_mode == "one" and self._current_track:
            # Use a timer thread to avoid VLC deadlock
            threading.Thread(
                target=self._replay_current, daemon=True
            ).start()
        else:
            threading.Thread(
                target=self._advance_after_end, daemon=True
            ).start()

    def _replay_current(self) -> None:
        """Replay the current track (called from thread)."""
        time.sleep(0.1)  # Small delay to avoid VLC race
        if self._current_track:
            self.play(self._current_track)

    def _advance_after_end(self) -> None:
        """Advance to next track after end reached (called from thread)."""
        time.sleep(0.1)  # Small delay to avoid VLC race
        self.next_track()

    def _start_position_polling(self) -> None:
        """Start polling VLC for position every 100ms."""
        if self._poll_running:
            return
        self._poll_running = True
        self._poll_thread = threading.Thread(
            target=self._poll_position, daemon=True
        )
        self._poll_thread.start()

    def _stop_position_polling(self) -> None:
        """Stop position polling thread."""
        self._poll_running = False
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

    def _poll_position(self) -> None:
        """Poll VLC for current position (runs in background thread)."""
        while self._poll_running:
            with self._lock:
                if self._media_player is not None and self._state == PlaybackState.PLAYING:
                    pos_ms = self._media_player.get_time()
                    dur_ms = self._media_player.get_length()
                    if pos_ms >= 0:
                        self._position_s = pos_ms / 1000.0
                    if dur_ms > 0:
                        self._duration_s = dur_ms / 1000.0
                    self._fire_position_callbacks()
            time.sleep(0.1)

    # --- Callback firing ---

    def _fire_state_callbacks(self) -> None:
        for cb in self._on_state_change:
            try:
                cb(self._state)
            except Exception:
                logger.warning("state_change callback error", exc_info=True)

    def _fire_track_callbacks(self) -> None:
        for cb in self._on_track_change:
            try:
                cb(self._current_track)
            except Exception:
                logger.warning("track_change callback error", exc_info=True)

    def _fire_position_callbacks(self) -> None:
        for cb in self._on_position_change:
            try:
                cb(self._position_s, self._duration_s)
            except Exception:
                logger.debug("position_change callback error", exc_info=True)

    def _fire_queue_callbacks(self) -> None:
        for cb in self._on_queue_change:
            try:
                cb(list(self._queue))
            except Exception:
                logger.warning("queue_change callback error", exc_info=True)
