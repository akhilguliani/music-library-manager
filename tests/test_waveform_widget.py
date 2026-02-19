"""Tests for WaveformWidget."""

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.widgets.waveform_widget import CuePointData, WaveformWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestWaveformWidget:
    """Tests for WaveformWidget."""

    def test_initial_state(self, qapp):
        widget = WaveformWidget()
        assert widget._peaks is None
        assert widget._position == 0.0
        assert widget._duration == 0.0
        assert widget._cue_points == []

    def test_set_peaks(self, qapp):
        widget = WaveformWidget()
        peaks = np.array([0.1, 0.5, 0.9, 0.3])
        widget.set_peaks(peaks)
        assert widget._peaks is not None
        assert len(widget._peaks) == 4

    def test_set_position_clamped(self, qapp):
        widget = WaveformWidget()
        widget.set_position(0.5)
        assert widget._position == 0.5
        widget.set_position(1.5)
        assert widget._position == 1.0
        widget.set_position(-0.5)
        assert widget._position == 0.0

    def test_set_duration(self, qapp):
        widget = WaveformWidget()
        widget.set_duration(240.0)
        assert widget._duration == 240.0

    def test_seek_signal_emitted(self, qapp):
        widget = WaveformWidget()
        widget.set_duration(240.0)
        widget.resize(800, 100)

        received = []
        widget.seek_requested.connect(lambda pos: received.append(pos))

        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        # Click at 50% of width (no cue points nearby)
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(400, 50),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(event)
        assert len(received) == 1
        assert abs(received[0] - 120.0) < 1.0  # 50% of 240s

    def test_no_seek_when_no_duration(self, qapp):
        widget = WaveformWidget()
        widget.resize(800, 100)

        received = []
        widget.seek_requested.connect(lambda pos: received.append(pos))

        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(400, 50),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(event)
        assert received == []

    def test_clear(self, qapp):
        widget = WaveformWidget()
        widget.set_peaks(np.array([0.5, 0.5]))
        widget.set_duration(100.0)
        widget.set_position(0.5)
        widget.clear()
        assert widget._peaks is None
        assert widget._duration == 0.0
        assert widget._position == 0.0

    def test_set_cue_points_tuples(self, qapp):
        """Backward compat: should accept (time, label) tuples."""
        widget = WaveformWidget()
        widget.set_cue_points([(30.0, "Intro"), (60.0, "Drop")])
        assert len(widget._cue_points) == 2
        assert widget._cue_points[0].pos == 30.0
        assert widget._cue_points[0].name == "Intro"
        assert widget._cue_points[0].num == 1

    def test_set_cue_points_dicts(self, qapp):
        """Should accept dict format with pos/name/num."""
        widget = WaveformWidget()
        widget.set_cue_points([{"pos": 30.0, "name": "X", "num": 3}])
        assert widget._cue_points[0].num == 3
        assert widget._cue_points[0].name == "X"


class TestCueHitDetection:
    """Tests for cue point hit detection."""

    def test_cue_at_x_hit(self, qapp):
        widget = WaveformWidget()
        widget.resize(800, 100)
        widget.set_duration(240.0)
        widget.set_cue_points([{"pos": 60.0, "name": "C1", "num": 1}])
        # Cue at 60/240 = 25% = pixel 200
        assert widget._cue_at_x(200) == 0
        assert widget._cue_at_x(205) == 0  # within hit radius
        assert widget._cue_at_x(300) == -1  # miss

    def test_cue_at_x_no_duration(self, qapp):
        widget = WaveformWidget()
        assert widget._cue_at_x(100) == -1

    def test_next_cue_number(self, qapp):
        widget = WaveformWidget()
        assert widget._next_cue_number() == 1

        widget.set_cue_points(
            [
                {"pos": 10.0, "name": "C1", "num": 1},
                {"pos": 20.0, "name": "C3", "num": 3},
            ]
        )
        assert widget._next_cue_number() == 2  # skips used 1 and 3


class TestCueEditing:
    """Tests for cue point editing interactions."""

    def test_emit_cues_changed(self, qapp):
        widget = WaveformWidget()
        widget.set_duration(240.0)
        received = []
        widget.cues_changed.connect(lambda cues: received.append(cues))

        widget._cue_points.append(CuePointData(pos=30.0, name="Test", num=1))
        widget._emit_cues_changed()

        assert len(received) == 1
        assert received[0][0]["pos"] == 30.0
        assert received[0][0]["name"] == "Test"
        assert received[0][0]["num"] == 1

    def test_delete_cue_emits_signal(self, qapp):
        widget = WaveformWidget()
        widget.set_duration(240.0)
        widget.set_cue_points(
            [
                {"pos": 30.0, "name": "C1", "num": 1},
                {"pos": 60.0, "name": "C2", "num": 2},
            ]
        )
        received = []
        widget.cues_changed.connect(lambda cues: received.append(cues))

        del widget._cue_points[0]
        widget._emit_cues_changed()

        assert len(received) == 1
        assert len(received[0]) == 1
        assert received[0][0]["num"] == 2

    def test_drag_moves_cue(self, qapp):
        """Left-click + drag on cue should update its position."""
        widget = WaveformWidget()
        widget.resize(800, 100)
        widget.set_duration(240.0)
        widget.set_cue_points([{"pos": 120.0, "name": "Mid", "num": 1}])

        received = []
        widget.cues_changed.connect(lambda cues: received.append(cues))

        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        # Press on cue at pixel 400 (50% of 800 = 120s)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(400, 50),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(press)
        assert widget._dragging_cue_index == 0

        # Drag to pixel 600 (75% = 180s)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(600, 50),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mouseMoveEvent(move)
        assert abs(widget._cue_points[0].pos - 180.0) < 1.0

        # Release
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(600, 50),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mouseReleaseEvent(release)
        assert widget._dragging_cue_index == -1
        assert len(received) == 1
        assert abs(received[0][0]["pos"] - 180.0) < 1.0

    def test_left_click_empty_area_seeks(self, qapp):
        """Left-click on empty area (no cue) should still emit seek."""
        widget = WaveformWidget()
        widget.resize(800, 100)
        widget.set_duration(240.0)

        seek_received = []
        cue_received = []
        widget.seek_requested.connect(lambda pos: seek_received.append(pos))
        widget.cues_changed.connect(lambda cues: cue_received.append(cues))

        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(400, 50),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(event)
        assert len(seek_received) == 1
        assert abs(seek_received[0] - 120.0) < 1.0
        assert cue_received == []  # no cue changes

    def test_hover_detection(self, qapp):
        """Mouse move should update hovered cue index."""
        widget = WaveformWidget()
        widget.resize(800, 100)
        widget.set_duration(240.0)
        widget.set_cue_points([{"pos": 60.0, "name": "C1", "num": 1}])

        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        # Move to cue position (pixel 200)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(200, 50),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mouseMoveEvent(move)
        assert widget._hovered_cue_index == 0

        # Move away
        move2 = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(500, 50),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mouseMoveEvent(move2)
        assert widget._hovered_cue_index == -1

    def test_leave_clears_hover(self, qapp):
        widget = WaveformWidget()
        widget._hovered_cue_index = 2
        widget.leaveEvent(None)
        assert widget._hovered_cue_index == -1
