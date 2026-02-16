"""Qt signal bridge for PlaybackEngine.

Translates engine callbacks into Qt signals for thread-safe UI updates.
This is the ONLY file in the player module that imports PySide6.
"""

from PySide6.QtCore import QObject, Signal, Slot

from vdj_manager.player.engine import PlaybackEngine, PlaybackState, TrackInfo


class PlaybackBridge(QObject):
    """Wraps PlaybackEngine with Qt signals.

    The engine uses plain callbacks (API-ready), but Qt UI needs signals
    for cross-thread safety. This bridge converts engine callbacks into
    Qt signals that can be safely connected to UI slots.
    """

    state_changed = Signal(str)
    track_changed = Signal(object)
    position_changed = Signal(float, float)
    volume_changed = Signal(int)
    speed_changed = Signal(float)
    queue_changed = Signal(list)
    track_finished = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = PlaybackEngine()
        self._engine.on_state_change(self._emit_state)
        self._engine.on_track_change(self._emit_track)
        self._engine.on_position_change(self._emit_position)
        self._engine.on_queue_change(self._emit_queue)
        self._engine.on_track_finished(self._emit_track_finished)

    @property
    def engine(self) -> PlaybackEngine:
        """Access the underlying PlaybackEngine."""
        return self._engine

    def initialize(self) -> bool:
        """Initialize VLC. Returns False if VLC not available."""
        return self._engine.initialize()

    def shutdown(self) -> None:
        """Release VLC resources."""
        self._engine.shutdown()

    # --- Slots for UI ---

    @Slot()
    def play(self):
        self._engine.play()

    @Slot()
    def pause(self):
        self._engine.pause()

    @Slot()
    def toggle_play_pause(self):
        self._engine.toggle_play_pause()

    @Slot()
    def stop(self):
        self._engine.stop()

    @Slot(float)
    def seek(self, pos: float):
        self._engine.seek(pos)

    @Slot(int)
    def set_volume(self, vol: int):
        old = self._engine.get_volume()
        self._engine.set_volume(vol)
        if self._engine.get_volume() != old:
            self.volume_changed.emit(self._engine.get_volume())

    @Slot(float)
    def set_speed(self, speed: float):
        old = self._engine.get_speed()
        self._engine.set_speed(speed)
        if self._engine.get_speed() != old:
            self.speed_changed.emit(self._engine.get_speed())

    @Slot()
    def next_track(self):
        self._engine.next_track()

    @Slot()
    def previous_track(self):
        self._engine.previous_track()

    @Slot(object)
    def play_track(self, track: TrackInfo):
        self._engine.play(track)

    @Slot(list, int)
    def set_queue(self, tracks: list, start_index: int = 0):
        self._engine.set_queue(tracks, start_index)

    @Slot(object)
    def add_to_queue(self, track: TrackInfo):
        self._engine.add_to_queue(track)

    @Slot(object)
    def insert_next(self, track: TrackInfo):
        self._engine.insert_next(track)

    @Slot()
    def clear_queue(self):
        self._engine.clear_queue()

    @Slot()
    def shuffle_queue(self):
        self._engine.shuffle_queue()

    @Slot(str)
    def set_repeat_mode(self, mode: str):
        self._engine.set_repeat_mode(mode)

    # --- Internal: engine callbacks -> Qt signals ---

    def _emit_state(self, state):
        self.state_changed.emit(state.value if isinstance(state, PlaybackState) else str(state))

    def _emit_track(self, track):
        self.track_changed.emit(track)

    def _emit_position(self, pos, dur):
        self.position_changed.emit(pos, dur)

    def _emit_queue(self, queue):
        self.queue_changed.emit(queue)

    def _emit_track_finished(self, track):
        self.track_finished.emit(track)
