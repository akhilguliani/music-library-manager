"""Tests for EmptyStateWidget."""

from __future__ import annotations

import sys

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from vdj_manager.ui.widgets.empty_state import EmptyStateWidget


@pytest.fixture(scope="module")
def qapp():
    """Provide a QApplication instance for the test module."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestEmptyStateWidget:
    """Tests for the EmptyStateWidget."""

    def test_creation(self, qapp: QApplication) -> None:
        """Widget can be created without error."""
        widget = EmptyStateWidget()
        assert widget is not None

    def test_with_all_elements(self, qapp: QApplication) -> None:
        """Icon, title, and description labels are all present."""
        widget = EmptyStateWidget(
            icon="📁",
            title="No database loaded",
            description="Select a database and click Load to get started.",
        )
        layout = widget.layout()
        assert layout is not None
        assert layout.count() == 3

        labels = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            assert item is not None
            w = item.widget()
            assert isinstance(w, QLabel)
            labels.append(w)

        assert labels[0].text() == "📁"
        assert labels[1].text() == "No database loaded"
        assert labels[2].text() == "Select a database and click Load to get started."

    def test_title_only(self, qapp: QApplication) -> None:
        """Only title is shown when icon and description are omitted."""
        widget = EmptyStateWidget(title="Nothing here")
        layout = widget.layout()
        assert layout is not None
        assert layout.count() == 1

        item = layout.itemAt(0)
        assert item is not None
        w = item.widget()
        assert isinstance(w, QLabel)
        assert w.text() == "Nothing here"

    def test_centered_alignment(self, qapp: QApplication) -> None:
        """Layout alignment is centered."""
        widget = EmptyStateWidget(title="Centered")
        layout = widget.layout()
        assert layout is not None
        assert layout.alignment() == Qt.AlignmentFlag.AlignCenter

    def test_title_text_property(self, qapp: QApplication) -> None:
        """title_text property returns the correct title value."""
        widget = EmptyStateWidget(
            icon="🎵",
            title="My Title",
            description="Some description.",
        )
        assert widget.title_text == "My Title"

    def test_title_text_property_empty(self, qapp: QApplication) -> None:
        """title_text returns empty string when no title is set."""
        widget = EmptyStateWidget(icon="🎵")
        assert widget.title_text == ""
