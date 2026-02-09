"""Tests for WaveformWidget."""

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.widgets.waveform_widget import WaveformWidget


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

        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent

        # Click at 50% of width
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

        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent

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

    def test_cue_points(self, qapp):
        widget = WaveformWidget()
        cues = [(30.0, "1"), (60.0, "2")]
        widget.set_cue_points(cues)
        assert widget._cue_points == cues
