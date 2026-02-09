"""Tests for PlaybackBridge Qt signal adapter."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication

from vdj_manager.player.bridge import PlaybackBridge
from vdj_manager.player.engine import PlaybackState, TrackInfo


@pytest.fixture(scope="module")
def qapp():
    """Create QCoreApplication for Qt tests."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


class TestPlaybackBridge:
    """Tests for PlaybackBridge signal emission."""

    def test_state_changed_signal(self, qapp):
        """Engine state callback should emit Qt signal."""
        bridge = PlaybackBridge()
        received = []
        bridge.state_changed.connect(lambda s: received.append(s))

        bridge._emit_state(PlaybackState.PLAYING)
        qapp.processEvents()
        assert received == ["playing"]

    def test_track_changed_signal(self, qapp):
        """Engine track callback should emit Qt signal."""
        bridge = PlaybackBridge()
        received = []
        bridge.track_changed.connect(lambda t: received.append(t))

        track = TrackInfo(file_path="/test.mp3", title="Test")
        bridge._emit_track(track)
        qapp.processEvents()
        assert len(received) == 1
        assert received[0].title == "Test"

    def test_position_changed_signal(self, qapp):
        """Engine position callback should emit Qt signal."""
        bridge = PlaybackBridge()
        received = []
        bridge.position_changed.connect(lambda p, d: received.append((p, d)))

        bridge._emit_position(30.0, 240.0)
        qapp.processEvents()
        assert received == [(30.0, 240.0)]

    def test_queue_changed_signal(self, qapp):
        """Engine queue callback should emit Qt signal."""
        bridge = PlaybackBridge()
        received = []
        bridge.queue_changed.connect(lambda q: received.append(len(q)))

        bridge._emit_queue([TrackInfo(file_path="/a.mp3")])
        qapp.processEvents()
        assert received == [1]

    def test_track_finished_signal(self, qapp):
        """Engine track_finished callback should emit Qt signal."""
        bridge = PlaybackBridge()
        received = []
        bridge.track_finished.connect(lambda t: received.append(t))

        track = TrackInfo(file_path="/done.mp3")
        bridge._emit_track_finished(track)
        qapp.processEvents()
        assert len(received) == 1

    def test_volume_changed_signal(self, qapp):
        """set_volume should emit volume_changed signal."""
        bridge = PlaybackBridge()
        received = []
        bridge.volume_changed.connect(lambda v: received.append(v))

        bridge.set_volume(60)
        qapp.processEvents()
        assert received == [60]

    def test_speed_changed_signal(self, qapp):
        """set_speed should emit speed_changed signal."""
        bridge = PlaybackBridge()
        received = []
        bridge.speed_changed.connect(lambda s: received.append(s))

        bridge.set_speed(1.5)
        qapp.processEvents()
        assert received == [1.5]

    def test_engine_accessible(self, qapp):
        """Bridge should expose the underlying engine."""
        bridge = PlaybackBridge()
        assert bridge.engine is not None
        assert isinstance(bridge.engine.state, PlaybackState)
