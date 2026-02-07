"""Tests for ConfigurableResultsTable and ResultsTable.export_to_csv."""

import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from vdj_manager.ui.widgets.results_table import ConfigurableResultsTable, ResultsTable


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for the test module."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestConfigurableResultsTable:
    """Tests for ConfigurableResultsTable."""

    def test_creation_with_columns(self, qapp):
        columns = [
            {"name": "File", "key": "file"},
            {"name": "Status", "key": "status"},
        ]
        table = ConfigurableResultsTable(columns)
        assert table.table.columnCount() == 2
        assert table.table.horizontalHeaderItem(0).text() == "File"
        assert table.table.horizontalHeaderItem(1).text() == "Status"

    def test_add_result(self, qapp):
        columns = [
            {"name": "File", "key": "file"},
            {"name": "Size", "key": "size"},
        ]
        table = ConfigurableResultsTable(columns)
        table.add_result({"file": "song.mp3", "size": "1024"})

        assert table.row_count() == 1
        assert table.table.item(0, 0).text() == "song.mp3"
        assert table.table.item(0, 1).text() == "1024"

    def test_add_result_missing_key(self, qapp):
        columns = [
            {"name": "File", "key": "file"},
            {"name": "Extra", "key": "extra"},
        ]
        table = ConfigurableResultsTable(columns)
        table.add_result({"file": "song.mp3"})

        assert table.row_count() == 1
        assert table.table.item(0, 0).text() == "song.mp3"
        assert table.table.item(0, 1).text() == "-"

    def test_color_function(self, qapp):
        def status_color(value):
            if value == "OK":
                return QColor("green")
            elif value == "FAIL":
                return QColor("red")
            return None

        columns = [
            {"name": "File", "key": "file"},
            {"name": "Status", "key": "status", "color_fn": status_color},
        ]
        table = ConfigurableResultsTable(columns)
        table.add_result({"file": "good.mp3", "status": "OK"})
        table.add_result({"file": "bad.mp3", "status": "FAIL"})

        assert table.table.item(0, 1).foreground().color() == QColor("green")
        assert table.table.item(1, 1).foreground().color() == QColor("red")

    def test_tooltip_key(self, qapp):
        columns = [
            {"name": "File", "key": "file", "tooltip_key": "full_path"},
        ]
        table = ConfigurableResultsTable(columns)
        table.add_result({"file": "song.mp3", "full_path": "/music/song.mp3"})

        assert table.table.item(0, 0).toolTip() == "/music/song.mp3"

    def test_clear(self, qapp):
        columns = [{"name": "File", "key": "file"}]
        table = ConfigurableResultsTable(columns)
        table.add_result({"file": "a.mp3"})
        table.add_result({"file": "b.mp3"})
        assert table.row_count() == 2

        table.clear()
        assert table.row_count() == 0

    def test_get_all_results(self, qapp):
        columns = [
            {"name": "File", "key": "file"},
            {"name": "Status", "key": "status"},
        ]
        table = ConfigurableResultsTable(columns)
        table.add_result({"file": "a.mp3", "status": "OK"})
        table.add_result({"file": "b.mp3", "status": "FAIL"})

        results = table.get_all_results()
        assert len(results) == 2
        assert results[0] == {"file": "a.mp3", "status": "OK"}
        assert results[1] == {"file": "b.mp3", "status": "FAIL"}

    def test_export_to_csv(self, qapp):
        columns = [
            {"name": "File", "key": "file"},
            {"name": "Status", "key": "status"},
        ]
        table = ConfigurableResultsTable(columns)
        table.add_result({"file": "a.mp3", "status": "OK"})
        table.add_result({"file": "b.mp3", "status": "FAIL"})

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            csv_path = f.name

        count = table.export_to_csv(csv_path)
        assert count == 2

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["file"] == "a.mp3"
        assert rows[1]["status"] == "FAIL"
        Path(csv_path).unlink()

    def test_export_to_csv_empty(self, qapp):
        columns = [{"name": "File", "key": "file"}]
        table = ConfigurableResultsTable(columns)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            csv_path = f.name

        count = table.export_to_csv(csv_path)
        assert count == 0
        Path(csv_path).unlink()

    def test_fixed_width_column(self, qapp):
        columns = [
            {"name": "File", "key": "file"},
            {"name": "Size", "key": "size", "width": 100},
        ]
        table = ConfigurableResultsTable(columns)
        assert table.table.columnWidth(1) == 100


class TestResultsTableExportCsv:
    """Tests for ResultsTable.export_to_csv."""

    def test_export_csv(self, qapp):
        table = ResultsTable()
        table.add_result("/music/song.mp3", {
            "success": True,
            "current_lufs": -14.0,
            "gain_db": 0.5,
        })

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            csv_path = f.name

        count = table.export_to_csv(csv_path)
        assert count == 1

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["file"] == "song.mp3"
        assert rows[0]["status"] == "OK"
        Path(csv_path).unlink()

    def test_export_csv_empty(self, qapp):
        table = ResultsTable()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            csv_path = f.name

        count = table.export_to_csv(csv_path)
        assert count == 0
        Path(csv_path).unlink()
