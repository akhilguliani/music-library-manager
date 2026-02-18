"""Tests for StarRatingWidget."""

import pytest
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.widgets.star_rating_widget import StarRatingWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestStarRating:
    """Tests for StarRatingWidget."""

    def test_initial_rating_is_zero(self, qapp):
        widget = StarRatingWidget()
        assert widget.rating == 0

    def test_set_rating(self, qapp):
        widget = StarRatingWidget()
        widget.rating = 3
        assert widget.rating == 3

    def test_rating_clamped_to_range(self, qapp):
        widget = StarRatingWidget()
        widget.rating = 10
        assert widget.rating == 5
        widget.rating = -1
        assert widget.rating == 0

    def test_rating_changed_signal(self, qapp):
        widget = StarRatingWidget()
        received = []
        widget.rating_changed.connect(lambda r: received.append(r))

        # Simulate clicking star 3 (center of star 3)
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        star_x = 2 * (widget.STAR_SIZE + widget.STAR_SPACING) + widget.STAR_SIZE // 2
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(star_x, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(event)
        assert received == [3]
        assert widget.rating == 3

    def test_click_same_star_clears(self, qapp):
        """Clicking the same star again should clear the rating."""
        widget = StarRatingWidget()
        widget._rating = 3

        received = []
        widget.rating_changed.connect(lambda r: received.append(r))

        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        star_x = 2 * (widget.STAR_SIZE + widget.STAR_SPACING) + widget.STAR_SIZE // 2
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(star_x, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(event)
        assert received == [0]
        assert widget.rating == 0

    def test_read_only_ignores_clicks(self, qapp):
        widget = StarRatingWidget()
        widget.set_read_only(True)

        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(event)
        assert widget.rating == 0

    def test_size_hint(self, qapp):
        widget = StarRatingWidget()
        size = widget.sizeHint()
        expected_w = 5 * (20 + 4) - 4  # 116
        assert size.width() == expected_w
        assert size.height() == 24
