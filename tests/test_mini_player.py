"""Tests for the MiniPlayer widget."""

import pytest
from PySide6.QtWidgets import QApplication

from vdj_manager.player.bridge import PlaybackBridge
from vdj_manager.player.engine import PlaybackState, TrackInfo
from vdj_manager.ui.widgets.mini_player import MiniPlayer


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mini_player(qapp):
    """Create a MiniPlayer with a real PlaybackBridge (no VLC init)."""
    bridge = PlaybackBridge()
    player = MiniPlayer(bridge)
    return player, bridge


class TestMiniPlayer:
    """Tests for MiniPlayer widget."""

    def test_initial_state(self, mini_player):
        """MiniPlayer should show 'No track loaded' initially."""
        player, _ = mini_player
        assert player.title_label.text() == "No track loaded"
        assert player.artist_label.text() == ""
        assert player.time_label.text() == "0:00 / 0:00"

    def test_fixed_height(self, mini_player):
        """MiniPlayer should have fixed 60px height."""
        player, _ = mini_player
        assert player.maximumHeight() == 60

    def test_state_changed_playing(self, qapp, mini_player):
        """State 'playing' should show pause icon."""
        player, bridge = mini_player
        bridge._emit_state(PlaybackState.PLAYING)
        qapp.processEvents()
        assert "\u23f8" in player.play_btn.text()

    def test_state_changed_paused(self, qapp, mini_player):
        """State 'paused' should show play icon."""
        player, bridge = mini_player
        bridge._emit_state(PlaybackState.PAUSED)
        qapp.processEvents()
        assert "\u25b6" in player.play_btn.text()

    def test_state_changed_stopped(self, qapp, mini_player):
        """State 'stopped' should show play icon."""
        player, bridge = mini_player
        bridge._emit_state(PlaybackState.STOPPED)
        qapp.processEvents()
        assert "\u25b6" in player.play_btn.text()

    def test_track_changed_updates_labels(self, qapp, mini_player):
        """Track change should update title and artist labels."""
        player, bridge = mini_player
        track = TrackInfo(file_path="/test.mp3", title="Test Song", artist="Test Artist")
        bridge._emit_track(track)
        qapp.processEvents()
        assert player.title_label.text() == "Test Song"
        assert player.artist_label.text() == "Test Artist"

    def test_track_changed_fallback_to_filename(self, qapp, mini_player):
        """Track without title should show filename stem."""
        player, bridge = mini_player
        track = TrackInfo(file_path="/music/cool_track.mp3")
        bridge._emit_track(track)
        qapp.processEvents()
        assert player.title_label.text() == "cool_track"
        assert player.artist_label.text() == "Unknown Artist"

    def test_position_changed_updates_slider(self, qapp, mini_player):
        """Position update should move the progress slider."""
        player, bridge = mini_player
        bridge._emit_position(60.0, 240.0)
        qapp.processEvents()
        # 60/240 = 0.25 * 1000 = 250
        assert player.progress_slider.value() == 250

    def test_position_changed_updates_time_label(self, qapp, mini_player):
        """Position update should format the time display."""
        player, bridge = mini_player
        bridge._emit_position(90.0, 240.0)
        qapp.processEvents()
        assert player.time_label.text() == "1:30 / 4:00"

    def test_position_zero_duration(self, qapp, mini_player):
        """Position with zero duration should not crash."""
        player, bridge = mini_player
        bridge._emit_position(0.0, 0.0)
        qapp.processEvents()
        assert player.time_label.text() == "0:00 / 0:00"

    def test_volume_changed_updates_slider(self, qapp, mini_player):
        """Volume change from bridge should update slider without feedback loop."""
        player, bridge = mini_player
        bridge.volume_changed.emit(50)
        qapp.processEvents()
        assert player.volume_slider.value() == 50

    def test_expand_button_emits_signal(self, qapp, mini_player):
        """Expand button should emit expand_requested signal."""
        player, _ = mini_player
        received = []
        player.expand_requested.connect(lambda: received.append(True))
        player.expand_btn.click()
        qapp.processEvents()
        assert received == [True]

    def test_vlc_unavailable_disables_controls(self, mini_player):
        """set_vlc_unavailable should disable all transport controls."""
        player, _ = mini_player
        player.set_vlc_unavailable()
        assert not player.play_btn.isEnabled()
        assert not player.next_btn.isEnabled()
        assert not player.prev_btn.isEnabled()
        assert not player.progress_slider.isEnabled()
        assert not player.volume_slider.isEnabled()
        assert "VLC not found" in player.title_label.text()

    def test_fmt_helper(self):
        """_fmt should format seconds as m:ss."""
        assert MiniPlayer._fmt(0) == "0:00"
        assert MiniPlayer._fmt(61) == "1:01"
        assert MiniPlayer._fmt(3661) == "61:01"
        assert MiniPlayer._fmt(-5) == "0:00"
