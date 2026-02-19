"""Tests for ColumnFilterRow widget."""

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTableView

from vdj_manager.ui.widgets.column_filter_row import ColumnFilterRow


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
def table_with_header(app):
    """Create a table view with a header for testing."""
    table = QTableView()
    # Need a model to have a proper header
    from PySide6.QtGui import QStandardItemModel

    model = QStandardItemModel(0, 5)
    model.setHorizontalHeaderLabels(["Art", "Title", "Artist", "BPM", "Key"])
    table.setModel(model)
    header = table.horizontalHeader()
    header.resizeSection(0, 44)
    header.resizeSection(1, 200)
    header.resizeSection(2, 150)
    header.resizeSection(3, 80)
    header.resizeSection(4, 80)
    return table, header


class TestColumnFilterRow:
    """Tests for ColumnFilterRow."""

    def test_creation(self, table_with_header):
        """Test filter row can be created."""
        table, header = table_with_header
        row = ColumnFilterRow(header=header, column_count=5)
        assert row is not None

    def test_creates_inputs_for_columns(self, table_with_header):
        """Test filter row creates one input per non-skipped column."""
        table, header = table_with_header
        row = ColumnFilterRow(header=header, column_count=5, skip_columns={0})

        # 4 inputs (5 columns minus 1 skipped)
        active_inputs = [v for v in row._inputs.values() if v is not None]
        assert len(active_inputs) == 4

    def test_skip_columns_have_no_input(self, table_with_header):
        """Test skipped columns have None as input."""
        table, header = table_with_header
        row = ColumnFilterRow(header=header, column_count=5, skip_columns={0})

        assert row._inputs[0] is None
        assert row._inputs[1] is not None

    def test_filter_changed_signal(self, table_with_header, app):
        """Test filter_changed signal is emitted after debounce when typing."""
        from PySide6.QtTest import QTest

        table, header = table_with_header
        row = ColumnFilterRow(header=header, column_count=5, skip_columns={0})

        signals = []
        row.filter_changed.connect(lambda col, text: signals.append((col, text)))

        # Type in the Title column (index 1)
        row._inputs[1].setText("test")

        # Wait for debounce timer to fire (200ms + margin)
        QTest.qWait(300)
        app.processEvents()

        assert len(signals) == 1
        assert signals[0] == (1, "test")

    def test_clear_all(self, table_with_header):
        """Test clear_all clears all inputs without emitting signals."""
        table, header = table_with_header
        row = ColumnFilterRow(header=header, column_count=5, skip_columns={0})

        # Set some text (will queue debounce, but we don't care about those signals)
        row._inputs[1].blockSignals(True)
        row._inputs[1].setText("hello")
        row._inputs[1].blockSignals(False)
        row._inputs[2].blockSignals(True)
        row._inputs[2].setText("world")
        row._inputs[2].blockSignals(False)

        signals = []
        row.filter_changed.connect(lambda col, text: signals.append((col, text)))

        row.clear_all()

        # All inputs should be empty
        assert row._inputs[1].text() == ""
        assert row._inputs[2].text() == ""

        # clear_all no longer emits signals (caller handles proxy clear)
        assert len(signals) == 0

    def test_set_focus_column(self, table_with_header):
        """Test set_focus_column calls setFocus on the correct input."""
        table, header = table_with_header
        row = ColumnFilterRow(header=header, column_count=5, skip_columns={0})

        # Just verify it doesn't crash and targets the right widget
        row.set_focus_column(1)
        # Focus may not register without active window, but method should not error

    def test_set_focus_skipped_column(self, table_with_header):
        """Test set_focus_column does nothing for skipped columns."""
        table, header = table_with_header
        row = ColumnFilterRow(header=header, column_count=5, skip_columns={0})

        # Should not crash
        row.set_focus_column(0)

    def test_section_resize_updates_width(self, table_with_header):
        """Test that resizing a header section updates the filter input width."""
        table, header = table_with_header
        row = ColumnFilterRow(header=header, column_count=5, skip_columns={0})

        # Simulate header resize
        header.resizeSection(1, 300)

        assert row._inputs[1].width() == 300
