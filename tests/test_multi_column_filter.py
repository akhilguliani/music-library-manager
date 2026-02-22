"""Tests for MultiColumnFilterProxyModel."""

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.models.multi_column_filter import MultiColumnFilterProxyModel


@pytest.fixture(scope="module")
def app():
    """Create a QApplication for testing."""
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        app = QApplication(["test"])
        yield app


@pytest.fixture
def source_model(app):
    """Create a source model with sample data."""
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["Title", "Artist", "Genre"])

    rows = [
        ("Song A", "Artist One", "Dance"),
        ("Song B", "Artist Two", "House"),
        ("Song C", "Artist One", "Techno"),
        ("Song D", "Artist Three", "Dance"),
    ]
    for title, artist, genre in rows:
        model.appendRow([QStandardItem(title), QStandardItem(artist), QStandardItem(genre)])

    return model


class TestMultiColumnFilter:
    """Tests for MultiColumnFilterProxyModel."""

    def test_creation(self, app):
        """Test proxy model can be created."""
        proxy = MultiColumnFilterProxyModel()
        assert proxy is not None

    def test_no_filter_passes_all(self, source_model):
        """Test all rows pass with no filters set."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        assert proxy.rowCount() == 4

    def test_single_column_filter(self, source_model):
        """Test filtering by a single column."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        proxy.set_column_filter(2, "Dance")  # Genre column
        assert proxy.rowCount() == 2

    def test_multiple_column_filters_and_logic(self, source_model):
        """Test multiple column filters use AND logic."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        proxy.set_column_filter(1, "Artist One")  # Artist
        proxy.set_column_filter(2, "Dance")  # Genre
        assert proxy.rowCount() == 1  # Only "Song A"

        # Verify the correct row
        data = proxy.data(proxy.index(0, 0), Qt.ItemDataRole.DisplayRole)
        assert data == "Song A"

    def test_case_insensitive(self, source_model):
        """Test filtering is case-insensitive."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        proxy.set_column_filter(2, "dance")
        assert proxy.rowCount() == 2

    def test_regex_pattern(self, source_model):
        """Test regex pattern matching."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        proxy.set_column_filter(2, "Dance|House")
        assert proxy.rowCount() == 3  # Dance + House

    def test_invalid_regex_treated_as_literal(self, source_model):
        """Test invalid regex is treated as a literal substring."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        proxy.set_column_filter(0, "[invalid")  # Invalid regex
        assert proxy.rowCount() == 0  # No title contains "[invalid"

    def test_clear_column_filter(self, source_model):
        """Test clearing a column filter."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        proxy.set_column_filter(2, "Dance")
        assert proxy.rowCount() == 2

        proxy.set_column_filter(2, "")  # Clear
        assert proxy.rowCount() == 4

    def test_clear_all_filters(self, source_model):
        """Test clearing all filters."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        proxy.set_column_filter(1, "One")
        proxy.set_column_filter(2, "Dance")
        assert proxy.rowCount() == 1

        proxy.clear_all_filters()
        assert proxy.rowCount() == 4

    def test_partial_match(self, source_model):
        """Test partial text matching."""
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(source_model)

        proxy.set_column_filter(1, "One")  # Matches "Artist One"
        assert proxy.rowCount() == 2

    def test_no_source_model(self, app):
        """Test filter with no source model returns True."""
        proxy = MultiColumnFilterProxyModel()
        proxy.set_column_filter(0, "test")
        # Should not crash
        assert proxy.rowCount() == 0

    def test_chained_with_sort_filter_proxy(self, source_model):
        """Test chaining with QSortFilterProxyModel (like in database panel)."""
        # Global search proxy
        global_proxy = QSortFilterProxyModel()
        global_proxy.setSourceModel(source_model)
        global_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        global_proxy.setFilterKeyColumn(-1)

        # Per-column filter proxy
        column_proxy = MultiColumnFilterProxyModel()
        column_proxy.setSourceModel(global_proxy)

        assert column_proxy.rowCount() == 4

        # Apply global filter
        global_proxy.setFilterFixedString("Artist One")
        assert column_proxy.rowCount() == 2

        # Apply column filter on top
        column_proxy.set_column_filter(2, "Techno")
        assert column_proxy.rowCount() == 1

        data = column_proxy.data(column_proxy.index(0, 0), Qt.ItemDataRole.DisplayRole)
        assert data == "Song C"
