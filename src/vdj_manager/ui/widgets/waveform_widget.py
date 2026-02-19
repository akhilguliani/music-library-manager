"""Waveform display widget with playhead, editable cue points, and click-to-seek."""

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QInputDialog, QMenu, QWidget


@dataclass
class CuePointData:
    """Internal representation of a cue point."""

    pos: float  # time in seconds
    name: str  # display label
    num: int | None = None  # VDJ cue number (1-8)


# 8 distinct colors for cue markers
CUE_COLORS = [
    QColor("#ff9800"),  # orange
    QColor("#4caf50"),  # green
    QColor("#e91e63"),  # pink
    QColor("#9c27b0"),  # purple
    QColor("#00bcd4"),  # cyan
    QColor("#ffeb3b"),  # yellow
    QColor("#ff5722"),  # deep orange
    QColor("#8bc34a"),  # light green
]


class WaveformWidget(QWidget):
    """Interactive waveform widget with editable cue points.

    Features:
    - Mirrored waveform bars with gradient fills
    - White playhead line
    - Color-coded numbered cue point markers
    - Click-to-seek on empty areas
    - Drag cue markers to move them
    - Right-click to add/rename/delete cue points

    Signals:
        seek_requested(float): Position in seconds where user clicked.
        cues_changed(list): Full list of cue dicts when any cue is modified.
    """

    seek_requested = Signal(float)
    cues_changed = Signal(list)

    # Colors
    COLOR_PLAYED_TOP = QColor("#4fc3f7")
    COLOR_PLAYED_BOT = QColor("#0288d1")
    COLOR_UNPLAYED_TOP = QColor("#1565c0")
    COLOR_UNPLAYED_BOT = QColor("#0d47a1")
    COLOR_PLAYHEAD = QColor("#ffffff")
    COLOR_BG = QColor("#0d1117")

    MAX_CUES = 8
    CUE_HIT_RADIUS = 8  # pixels

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peaks: np.ndarray | None = None
        self._position = 0.0  # 0.0 to 1.0
        self._duration = 0.0
        self._cue_points: list[CuePointData] = []
        self._hovered_cue_index: int = -1
        self._dragging_cue_index: int = -1
        self.setMinimumHeight(80)
        self.setMouseTracking(True)
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

    def set_cue_points(self, cues: list) -> None:
        """Set cue point markers.

        Accepts list of (time_s, label) tuples or list of dicts with
        pos/name/num keys.
        """
        self._cue_points = []
        for i, cue in enumerate(cues):
            if isinstance(cue, dict):
                self._cue_points.append(
                    CuePointData(
                        pos=cue["pos"],
                        name=cue.get("name", f"Cue {i + 1}"),
                        num=cue.get("num"),
                    )
                )
            else:
                time_s, label = cue
                self._cue_points.append(CuePointData(pos=time_s, name=label, num=i + 1))
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

    # --- Hit detection ---

    def _cue_at_x(self, x: float) -> int:
        """Return index of cue point at pixel x, or -1."""
        if self._duration <= 0:
            return -1
        w = self.width()
        for i, cue in enumerate(self._cue_points):
            cx = cue.pos / self._duration * w
            if abs(x - cx) <= self.CUE_HIT_RADIUS:
                return i
        return -1

    def _next_cue_number(self) -> int:
        """Find the lowest available cue number (1-8)."""
        used = {c.num for c in self._cue_points if c.num is not None}
        for n in range(1, 9):
            if n not in used:
                return n
        return len(self._cue_points) + 1

    def _emit_cues_changed(self) -> None:
        """Emit full cue list as dicts."""
        cue_dicts = [{"pos": c.pos, "name": c.name, "num": c.num} for c in self._cue_points]
        self.cues_changed.emit(cue_dicts)

    # --- Mouse events ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._duration <= 0:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            cue_idx = self._cue_at_x(event.position().x())
            if cue_idx >= 0:
                self._dragging_cue_index = cue_idx
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
                ratio = event.position().x() / self.width()
                ratio = max(0.0, min(1.0, ratio))
                self.seek_requested.emit(ratio * self._duration)

        elif event.button() == Qt.MouseButton.RightButton:
            cue_idx = self._cue_at_x(event.position().x())
            if cue_idx >= 0:
                self._show_cue_context_menu(event.globalPosition().toPoint(), cue_idx)
            else:
                self._show_add_cue_menu(event.globalPosition().toPoint(), event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging_cue_index >= 0:
            ratio = max(0.0, min(1.0, event.position().x() / self.width()))
            self._cue_points[self._dragging_cue_index].pos = ratio * self._duration
            self.update()
        else:
            cue_idx = self._cue_at_x(event.position().x())
            if cue_idx != self._hovered_cue_index:
                self._hovered_cue_index = cue_idx
                cursor = (
                    Qt.CursorShape.OpenHandCursor
                    if cue_idx >= 0
                    else Qt.CursorShape.PointingHandCursor
                )
                self.setCursor(cursor)
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_cue_index >= 0:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._dragging_cue_index = -1
            self._emit_cues_changed()
            self.update()

    def leaveEvent(self, event) -> None:
        self._hovered_cue_index = -1
        self.update()

    # --- Context menus ---

    def _show_cue_context_menu(self, global_pos, cue_index: int) -> None:
        menu = QMenu(self)
        cue = self._cue_points[cue_index]

        rename_action = menu.addAction(f'Rename "{cue.name}"...')
        delete_action = menu.addAction("Delete Cue Point")

        action = menu.exec(global_pos)
        if action == rename_action:
            text, ok = QInputDialog.getText(self, "Rename Cue", "Name:", text=cue.name)
            if ok and text.strip():
                self._cue_points[cue_index].name = text.strip()
                self._emit_cues_changed()
                self.update()
        elif action == delete_action:
            del self._cue_points[cue_index]
            self._emit_cues_changed()
            self.update()

    def _show_add_cue_menu(self, global_pos, pixel_x: float) -> None:
        if len(self._cue_points) >= self.MAX_CUES:
            return
        menu = QMenu(self)
        add_action = menu.addAction("Add Cue Point Here")
        action = menu.exec(global_pos)
        if action == add_action:
            ratio = max(0.0, min(1.0, pixel_x / self.width()))
            pos = ratio * self._duration
            num = self._next_cue_number()
            self._cue_points.append(CuePointData(pos=pos, name=f"Cue {num}", num=num))
            self._emit_cues_changed()
            self.update()

    # --- Painting ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        mid_y = h / 2

        # Background
        painter.fillRect(0, 0, w, h, self.COLOR_BG)

        if self._peaks is None or len(self._peaks) == 0:
            painter.setPen(QColor("#555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No waveform data")
            painter.end()
            return

        # Draw mirrored waveform bars with gradients
        num_bars = len(self._peaks)
        bar_width = max(1.0, w / num_bars)
        playhead_x = self._position * w

        for i in range(num_bars):
            x = i * bar_width
            peak_val = float(self._peaks[i])
            bar_half_h = peak_val * (mid_y - 2)

            if bar_half_h < 1:
                continue

            played = x < playhead_x

            # Gradient for upper half
            grad = QLinearGradient(0, mid_y - bar_half_h, 0, mid_y)
            if played:
                grad.setColorAt(0, self.COLOR_PLAYED_TOP)
                grad.setColorAt(1, self.COLOR_PLAYED_BOT)
            else:
                grad.setColorAt(0, self.COLOR_UNPLAYED_TOP)
                grad.setColorAt(1, self.COLOR_UNPLAYED_BOT)

            bx = int(x)
            bw = max(1, int(bar_width))
            upper_h = max(1, int(bar_half_h))

            # Upper bar
            painter.fillRect(bx, int(mid_y - bar_half_h), bw, upper_h, grad)
            # Lower bar (mirror)
            painter.fillRect(bx, int(mid_y), bw, upper_h, grad)

        # Center line
        painter.setPen(QPen(QColor("#333"), 1))
        painter.drawLine(0, int(mid_y), w, int(mid_y))

        # Draw cue points
        if self._duration > 0:
            badge_font = QFont()
            badge_font.setPixelSize(10)
            badge_font.setBold(True)
            painter.setFont(badge_font)

            for i, cue in enumerate(self._cue_points):
                cx = int(cue.pos / self._duration * w)
                color = CUE_COLORS[i % len(CUE_COLORS)]
                is_hover = i == self._hovered_cue_index
                is_drag = i == self._dragging_cue_index

                # Vertical line
                pen_width = 3 if is_hover else 2
                if is_drag:
                    painter.setPen(QPen(color, pen_width, Qt.PenStyle.DashLine))
                else:
                    painter.setPen(QPen(color, pen_width))
                painter.drawLine(cx, 0, cx, h)

                # Numbered badge at top
                label = str(cue.num or i + 1)
                badge_w, badge_h = 18, 16
                badge_x = cx - badge_w // 2
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(badge_x, 1, badge_w, badge_h, 3, 3)
                painter.setPen(QColor("#fff"))
                painter.drawText(badge_x, 1, badge_w, badge_h, Qt.AlignmentFlag.AlignCenter, label)

                # Name label below badge
                if cue.name and not cue.name.startswith("Cue "):
                    painter.setPen(color)
                    painter.drawText(cx + 3, badge_h + 12, cue.name)

        # Draw playhead
        painter.setPen(QPen(self.COLOR_PLAYHEAD, 2))
        px = int(playhead_x)
        painter.drawLine(px, 0, px, h)

        painter.end()

    @staticmethod
    def _fmt(seconds: float) -> str:
        m, s = divmod(int(max(0, seconds)), 60)
        return f"{m}:{s:02d}"
