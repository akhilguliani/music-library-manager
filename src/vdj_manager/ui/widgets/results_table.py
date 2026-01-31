"""Results table widget for displaying processing results."""

from typing import Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor


class ResultsTable(QWidget):
    """Table widget for displaying normalization/analysis results.

    Displays results with columns for:
    - File name
    - Current LUFS
    - Gain needed (dB)
    - Status (success/fail)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the results table.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File", "LUFS", "Gain (dB)", "Status"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        # Set column resize modes
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # File name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # LUFS
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Gain
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Status

        layout.addWidget(self.table)

    def clear(self) -> None:
        """Clear all results."""
        self.table.setRowCount(0)

    @Slot(str, dict)
    def add_result(self, path: str, result: dict) -> None:
        """Add a result row to the table.

        Args:
            path: File path.
            result: Result dictionary with success, current_lufs, gain_db, error.
        """
        from pathlib import Path

        row = self.table.rowCount()
        self.table.insertRow(row)

        # File name
        filename = Path(path).name
        file_item = QTableWidgetItem(filename)
        file_item.setToolTip(path)
        self.table.setItem(row, 0, file_item)

        # LUFS
        lufs = result.get("current_lufs") or result.get("lufs")
        lufs_item = QTableWidgetItem(f"{lufs:.1f}" if lufs is not None else "-")
        lufs_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(row, 1, lufs_item)

        # Gain
        gain = result.get("gain_db")
        if gain is not None:
            gain_text = f"{gain:+.1f}"
            gain_item = QTableWidgetItem(gain_text)

            # Color code gain
            if gain > 3:
                gain_item.setForeground(QColor("red"))
            elif gain < -3:
                gain_item.setForeground(QColor("orange"))
            else:
                gain_item.setForeground(QColor("green"))
        else:
            gain_item = QTableWidgetItem("-")

        gain_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(row, 2, gain_item)

        # Status
        success = result.get("success", True)
        if success:
            status_item = QTableWidgetItem("OK")
            status_item.setForeground(QColor("green"))
        else:
            error = result.get("error", "Failed")
            status_item = QTableWidgetItem("FAIL")
            status_item.setForeground(QColor("red"))
            status_item.setToolTip(error)

        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 3, status_item)

        # Scroll to show latest
        self.table.scrollToBottom()

    def get_all_results(self) -> list[dict]:
        """Get all results as a list of dictionaries.

        Returns:
            List of result dictionaries.
        """
        results = []
        for row in range(self.table.rowCount()):
            result = {
                "file": self.table.item(row, 0).text(),
                "path": self.table.item(row, 0).toolTip(),
                "lufs": self.table.item(row, 1).text(),
                "gain": self.table.item(row, 2).text(),
                "status": self.table.item(row, 3).text(),
            }
            results.append(result)
        return results

    def row_count(self) -> int:
        """Get the number of result rows.

        Returns:
            Number of rows.
        """
        return self.table.rowCount()
