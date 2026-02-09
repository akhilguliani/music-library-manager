"""Clickable 5-star rating widget."""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent


class StarRatingWidget(QWidget):
    """Interactive 5-star rating widget.

    Displays filled and empty stars. Click to set rating, click
    same star again to clear rating to 0.

    Signals:
        rating_changed(int): Emitted when user changes rating (0-5).
    """

    rating_changed = Signal(int)

    STAR_COUNT = 5
    STAR_SIZE = 20
    STAR_SPACING = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rating = 0
        self._hover_rating = -1
        self._read_only = False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        w = self.STAR_COUNT * (self.STAR_SIZE + self.STAR_SPACING) - self.STAR_SPACING
        return QSize(w, self.STAR_SIZE + 4)

    @property
    def rating(self) -> int:
        return self._rating

    @rating.setter
    def rating(self, value: int) -> None:
        value = max(0, min(5, value))
        if value != self._rating:
            self._rating = value
            self.update()

    def set_read_only(self, read_only: bool) -> None:
        self._read_only = read_only
        self.setCursor(
            Qt.CursorShape.ArrowCursor if read_only else Qt.CursorShape.PointingHandCursor
        )

    def _star_at(self, x: int) -> int:
        """Return 1-based star index at x position, or 0 if outside."""
        for i in range(self.STAR_COUNT):
            left = i * (self.STAR_SIZE + self.STAR_SPACING)
            right = left + self.STAR_SIZE
            if left <= x <= right:
                return i + 1
        return 0

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._read_only or event.button() != Qt.MouseButton.LeftButton:
            return
        star = self._star_at(int(event.position().x()))
        if star > 0:
            new_rating = 0 if star == self._rating else star
            self._rating = new_rating
            self.update()
            self.rating_changed.emit(new_rating)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._read_only:
            return
        star = self._star_at(int(event.position().x()))
        if star != self._hover_rating:
            self._hover_rating = star
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover_rating = -1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        display_rating = self._hover_rating if self._hover_rating > 0 else self._rating

        for i in range(self.STAR_COUNT):
            x = i * (self.STAR_SIZE + self.STAR_SPACING)
            filled = i < display_rating
            self._draw_star(painter, x, 2, self.STAR_SIZE, filled)

        painter.end()

    def _draw_star(self, painter: QPainter, x: int, y: int, size: int, filled: bool) -> None:
        """Draw a single star at the given position."""
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF

        import math

        cx = x + size / 2
        cy = y + size / 2
        outer_r = size / 2
        inner_r = outer_r * 0.4

        points = []
        for j in range(10):
            angle = math.pi / 2 + j * math.pi / 5
            r = outer_r if j % 2 == 0 else inner_r
            px = cx + r * math.cos(angle)
            py = cy - r * math.sin(angle)
            points.append(QPointF(px, py))

        polygon = QPolygonF(points)

        if filled:
            painter.setBrush(QColor("#ffc107"))
            painter.setPen(QPen(QColor("#ffa000"), 1))
        else:
            painter.setBrush(QColor("#444"))
            painter.setPen(QPen(QColor("#666"), 1))

        painter.drawPolygon(polygon)
