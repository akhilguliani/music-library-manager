"""Waveform display widget with playhead and click-to-seek."""

import numpy as np

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent


class WaveformWidget(QWidget):
    """Custom widget that draws a waveform from peak data.

    Features:
    - Vertical bars from peak array
    - Played portion in lighter color, unplayed in darker
    - White playhead line
    - Cue point markers (orange vertical lines with labels)
    - Click-to-seek

    Signals:
        seek_requested(float): Position in seconds where user clicked.
    """

    seek_requested = Signal(float)

    # Colors
    COLOR_PLAYED = QColor("#4fc3f7")
    COLOR_UNPLAYED = QColor("#1565c0")
    COLOR_PLAYHEAD = QColor("#ffffff")
    COLOR_CUE = QColor("#ff9800")
    COLOR_BG = QColor("#0d1117")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peaks: np.ndarray | None = None
        self._position = 0.0  # 0.0 to 1.0
        self._duration = 0.0
        self._cue_points: list[tuple[float, str]] = []  # (time_s, label)
        self.setMinimumHeight(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_peaks(self, peaks: np.ndarray) -> None:
        """Set waveform peak data (0.0-1.0 array)."""
        self._peaks = peaks
        self.update()

    def set_position(self, ratio: float) -> None:
        """Set playhead position as 0.0-1.0 ratio."""
        self._position = max(0.0, min(1.0, ratio))
        self.update()

    def set_duration(self, duration: float) -> None:
        """Set track duration in seconds for seek calculation."""
        self._duration = duration

    def set_cue_points(self, cues: list[tuple[float, str]]) -> None:
        """Set cue point markers. Each is (time_seconds, label)."""
        self._cue_points = cues
        self.update()

    def clear(self) -> None:
        """Clear waveform data."""
        self._peaks = None
        self._position = 0.0
        self._duration = 0.0
        self._cue_points = []
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(600, 100)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._duration > 0:
            ratio = event.position().x() / self.width()
            ratio = max(0.0, min(1.0, ratio))
            self.seek_requested.emit(ratio * self._duration)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, self.COLOR_BG)

        if self._peaks is None or len(self._peaks) == 0:
            painter.setPen(QColor("#555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No waveform data")
            painter.end()
            return

        # Draw waveform bars
        num_bars = len(self._peaks)
        bar_width = max(1, w / num_bars)
        playhead_x = self._position * w

        for i in range(num_bars):
            x = i * bar_width
            peak_val = float(self._peaks[i])
            bar_height = peak_val * (h - 4)

            color = self.COLOR_PLAYED if x < playhead_x else self.COLOR_UNPLAYED
            painter.fillRect(
                int(x), int(h / 2 - bar_height / 2),
                max(1, int(bar_width) - 1), max(1, int(bar_height)),
                color,
            )

        # Draw cue points
        if self._duration > 0:
            painter.setPen(QPen(self.COLOR_CUE, 2))
            for time_s, label in self._cue_points:
                cx = int(time_s / self._duration * w)
                painter.drawLine(cx, 0, cx, h)
                painter.drawText(cx + 3, 12, label)

        # Draw playhead
        painter.setPen(QPen(self.COLOR_PLAYHEAD, 2))
        px = int(playhead_x)
        painter.drawLine(px, 0, px, h)

        painter.end()
