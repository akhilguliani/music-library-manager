"""Tests for the PlaybackEngine and TrackInfo."""

from unittest.mock import MagicMock, patch

from vdj_manager.player.engine import PlaybackEngine, PlaybackState, TrackInfo

# =============================================================================
# TrackInfo tests
# =============================================================================


class TestTrackInfo:
    """Tests for TrackInfo dataclass."""

    def test_defaults(self):
        t = TrackInfo(file_path="/path/to/song.mp3")
        assert t.file_path == "/path/to/song.mp3"
        assert t.title == ""
        assert t.artist == ""
        assert t.album == ""
        assert t.duration_s == 0.0
        assert t.bpm is None
        assert t.key is None
        assert t.energy is None
        assert t.mood is None
        assert t.rating is None
        assert t.cue_points == []

    def test_to_dict(self):
        t = TrackInfo(
            file_path="/song.mp3",
            title="Test Song",
            artist="Test Artist",
            bpm=128.0,
        )
        d = t.to_dict()
        assert d["file_path"] == "/song.mp3"
        assert d["title"] == "Test Song"
        assert d["artist"] == "Test Artist"
        assert d["bpm"] == 128.0
        assert d["cue_points"] == []

    def test_from_song(self):
        """Test creating TrackInfo from a Song model."""
        from vdj_manager.core.models import Infos, Poi, Scan, Song, Tags

        song = Song(
            FilePath="/path/to/track.mp3",
            tags=Tags(
                Author="DJ Test",
                Title="Bangin Tune",
                Album="Test Album",
                Key="8A",
                Rating=4,
                Grouping="7",
            ),
            infos=Infos(SongLength=240.5),
            scan=Scan(Bpm=0.46875),  # 128 BPM
            pois=[
                Poi(Type="cue", Pos=0.0, Num=1, Name="Intro"),
                Poi(Type="cue", Pos=32.0, Num=2, Name="Drop"),
                Poi(Type="beatgrid", Pos=0.0, Bpm=0.46875),
            ],
        )
        t = TrackInfo.from_song(song)
        assert t.file_path == "/path/to/track.mp3"
        assert t.title == "Bangin Tune"
        assert t.artist == "DJ Test"
        assert t.album == "Test Album"
        assert t.duration_s == 240.5
        assert abs(t.bpm - 128.0) < 0.1
        assert t.key == "8A"
        assert t.energy == 7
        assert t.rating == 4
        assert len(t.cue_points) == 2  # Only cue type, not beatgrid
        assert t.cue_points[0]["name"] == "Intro"
        assert t.cue_points[1]["pos"] == 32.0

    def test_from_song_minimal(self):
        """Test from_song with a song that has no tags/infos."""
        from vdj_manager.core.models import Song

        song = Song(FilePath="/bare.mp3")
        t = TrackInfo.from_song(song)
        assert t.file_path == "/bare.mp3"
        assert t.title == ""
        assert t.artist == ""
        assert t.duration_s == 0.0
        assert t.bpm is None
        assert t.cue_points == []


# =============================================================================
# PlaybackEngine state management tests
# =============================================================================


class TestPlaybackEngineState:
    """Tests for PlaybackEngine state management (no VLC needed)."""

    def setup_method(self):
        self.engine = PlaybackEngine()

    def test_initial_state(self):
        assert self.engine.state == PlaybackState.STOPPED
        assert self.engine.current_track is None
        assert self.engine.position == 0.0
        assert self.engine.duration == 0.0
        assert self.engine.get_volume() == 80
        assert self.engine.get_speed() == 1.0
        assert not self.engine.is_muted
        assert not self.engine.is_initialized

    def test_volume_clamping(self):
        self.engine.set_volume(150)
        assert self.engine.get_volume() == 100
        self.engine.set_volume(-10)
        assert self.engine.get_volume() == 0
        self.engine.set_volume(50)
        assert self.engine.get_volume() == 50

    def test_speed_clamping(self):
        self.engine.set_speed(3.0)
        assert self.engine.get_speed() == 2.0
        self.engine.set_speed(0.1)
        assert self.engine.get_speed() == 0.5
        self.engine.set_speed(1.5)
        assert self.engine.get_speed() == 1.5

    def test_toggle_mute(self):
        assert not self.engine.is_muted
        self.engine.toggle_mute()
        assert self.engine.is_muted
        self.engine.toggle_mute()
        assert not self.engine.is_muted

    def test_repeat_mode(self):
        assert self.engine.repeat_mode == "none"
        self.engine.set_repeat_mode("one")
        assert self.engine.repeat_mode == "one"
        self.engine.set_repeat_mode("all")
        assert self.engine.repeat_mode == "all"
        self.engine.set_repeat_mode("invalid")
        assert self.engine.repeat_mode == "all"  # Unchanged

    def test_shuffle_toggle(self):
        assert not self.engine.is_shuffle
        self.engine.shuffle_queue()
        assert self.engine.is_shuffle
        self.engine.shuffle_queue()
        assert not self.engine.is_shuffle

    def test_get_state_serializable(self):
        state = self.engine.get_state()
        assert state["state"] == "stopped"
        assert state["current_track"] is None
        assert state["volume"] == 80
        assert state["speed"] == 1.0
        assert state["shuffle"] is False
        assert state["repeat_mode"] == "none"


# =============================================================================
# Queue management tests
# =============================================================================


class TestPlaybackEngineQueue:
    """Tests for queue management."""

    def setup_method(self):
        self.engine = PlaybackEngine()
        self.tracks = [TrackInfo(file_path=f"/track{i}.mp3", title=f"Track {i}") for i in range(5)]

    def test_empty_queue(self):
        assert self.engine.queue == []
        assert self.engine.queue_index == -1

    def test_add_to_queue(self):
        self.engine.add_to_queue(self.tracks[0])
        self.engine.add_to_queue(self.tracks[1])
        assert len(self.engine.queue) == 2
        assert self.engine.queue[0].file_path == "/track0.mp3"
        assert self.engine.queue[1].file_path == "/track1.mp3"

    def test_remove_from_queue(self):
        for t in self.tracks[:3]:
            self.engine.add_to_queue(t)
        self.engine.remove_from_queue(1)
        assert len(self.engine.queue) == 2
        assert self.engine.queue[0].file_path == "/track0.mp3"
        assert self.engine.queue[1].file_path == "/track2.mp3"

    def test_remove_invalid_index(self):
        self.engine.add_to_queue(self.tracks[0])
        self.engine.remove_from_queue(5)  # Out of range
        assert len(self.engine.queue) == 1

    def test_reorder_queue(self):
        for t in self.tracks[:4]:
            self.engine.add_to_queue(t)
        self.engine.reorder_queue(0, 2)
        assert self.engine.queue[0].file_path == "/track1.mp3"
        assert self.engine.queue[1].file_path == "/track2.mp3"
        assert self.engine.queue[2].file_path == "/track0.mp3"

    def test_reorder_same_index(self):
        for t in self.tracks[:3]:
            self.engine.add_to_queue(t)
        self.engine.reorder_queue(1, 1)  # No-op
        assert self.engine.queue[1].file_path == "/track1.mp3"

    def test_clear_queue(self):
        for t in self.tracks:
            self.engine.add_to_queue(t)
        self.engine.clear_queue()
        assert self.engine.queue == []
        assert self.engine.queue_index == -1

    def test_get_queue_list(self):
        self.engine.add_to_queue(self.tracks[0])
        ql = self.engine.get_queue_list()
        assert len(ql) == 1
        assert ql[0]["file_path"] == "/track0.mp3"

    def test_get_history_list(self):
        assert self.engine.get_history_list() == []

    def test_history_max_size(self):
        """History should be limited to max_history entries."""
        self.engine._max_history = 5
        for i in range(10):
            self.engine._add_to_history(TrackInfo(file_path=f"/track{i}.mp3"))
        assert len(self.engine.history) == 5
        # Most recent first
        assert self.engine.history[0].file_path == "/track9.mp3"


# =============================================================================
# Callback tests
# =============================================================================


class TestPlaybackEngineCallbacks:
    """Tests for observer pattern callbacks."""

    def setup_method(self):
        self.engine = PlaybackEngine()

    def test_state_change_callback(self):
        states = []
        self.engine.on_state_change(lambda s: states.append(s))
        self.engine._set_state(PlaybackState.PLAYING)
        assert states == [PlaybackState.PLAYING]

    def test_track_change_callback(self):
        tracks = []
        self.engine.on_track_change(lambda t: tracks.append(t))
        track = TrackInfo(file_path="/test.mp3", title="Test")
        self.engine._current_track = track
        self.engine._fire_track_callbacks()
        assert len(tracks) == 1
        assert tracks[0].title == "Test"

    def test_position_change_callback(self):
        positions = []
        self.engine.on_position_change(lambda p, d: positions.append((p, d)))
        self.engine._position_s = 30.0
        self.engine._duration_s = 240.0
        self.engine._fire_position_callbacks()
        assert positions == [(30.0, 240.0)]

    def test_queue_change_callback(self):
        queues = []
        self.engine.on_queue_change(lambda q: queues.append(len(q)))
        self.engine.add_to_queue(TrackInfo(file_path="/a.mp3"))
        assert queues == [1]
        self.engine.add_to_queue(TrackInfo(file_path="/b.mp3"))
        assert queues == [1, 2]

    def test_callback_exception_does_not_propagate(self):
        """A failing callback should not break other callbacks."""
        results = []

        def bad_callback(s):
            raise RuntimeError("oops")

        def good_callback(s):
            results.append(s)

        self.engine.on_state_change(bad_callback)
        self.engine.on_state_change(good_callback)
        self.engine._set_state(PlaybackState.PLAYING)
        assert results == [PlaybackState.PLAYING]

    def test_no_callback_on_same_state(self):
        """State callback should not fire when state doesn't change."""
        states = []
        self.engine.on_state_change(lambda s: states.append(s))
        self.engine._state = PlaybackState.STOPPED
        self.engine._set_state(PlaybackState.STOPPED)  # Same state
        assert states == []


# =============================================================================
# VLC initialization tests
# =============================================================================


class TestPlaybackEngineVLC:
    """Tests that require mocked VLC."""

    def test_initialize_success(self):
        mock_vlc = MagicMock()
        mock_instance = MagicMock()
        mock_player = MagicMock()
        mock_vlc.Instance.return_value = mock_instance
        mock_instance.media_player_new.return_value = mock_player
        mock_vlc.EventType.MediaPlayerEndReached = "end_reached"

        with patch.dict("sys.modules", {"vlc": mock_vlc}):
            engine = PlaybackEngine()
            result = engine.initialize()
            assert result is True
            assert engine.is_initialized

    def test_initialize_no_vlc(self):
        with patch.dict("sys.modules", {"vlc": None}):
            engine = PlaybackEngine()
            result = engine.initialize()
            assert result is False
            assert not engine.is_initialized

    def test_play_without_init(self):
        """Play should be a no-op when not initialized."""
        engine = PlaybackEngine()
        track = TrackInfo(file_path="/test.mp3")
        engine.play(track)  # Should not raise
        assert engine.state == PlaybackState.STOPPED

    def test_shutdown(self):
        mock_vlc = MagicMock()
        mock_instance = MagicMock()
        mock_player = MagicMock()
        mock_vlc.Instance.return_value = mock_instance
        mock_instance.media_player_new.return_value = mock_player
        mock_vlc.EventType.MediaPlayerEndReached = "end_reached"

        with patch.dict("sys.modules", {"vlc": mock_vlc}):
            engine = PlaybackEngine()
            engine.initialize()
            engine.shutdown()
            assert not engine.is_initialized
            mock_player.stop.assert_called_once()
            mock_player.release.assert_called_once()
            mock_instance.release.assert_called_once()
