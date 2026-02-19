"""Row of per-column filter inputs that sync with table header widths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QLineEdit, QWidget

if TYPE_CHECKING:
    pass


class ColumnFilterRow(QWidget):
    """A row of QLineEdits, one per visible table column, synced to header widths.

    Signals:
        filter_changed(int, str): Emitted when a column filter changes (column, text).
    """

    filter_changed = Signal(int, str)  # column index, filter text

    def __init__(
        self,
        header: QHeaderView,
        column_count: int,
        skip_columns: set[int] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the filter row.

        Args:
            header: The table's horizontal header to sync widths with.
            column_count: Number of columns in the table.
            skip_columns: Column indices to skip (e.g., art column).
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._header = header
        self._skip_columns = skip_columns or set()
        self._inputs: dict[int, QLineEdit] = {}
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._emit_pending_filters)
        self._pending_changes: dict[int, str] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for col in range(column_count):
            if col in self._skip_columns:
                # Placeholder spacer for skipped columns (e.g., art)
                spacer = QWidget()
                spacer.setFixedWidth(header.sectionSize(col))
                layout.addWidget(spacer)
                self._inputs[col] = None  # type: ignore[assignment]
            else:
                line_edit = QLineEdit()
                line_edit.setPlaceholderText("Filter...")
                line_edit.setClearButtonEnabled(True)
                line_edit.setFixedHeight(24)
                line_edit.setFixedWidth(header.sectionSize(col))
                line_edit.textChanged.connect(lambda text, c=col: self._on_input_changed(c, text))
                layout.addWidget(line_edit)
                self._inputs[col] = line_edit

        # Sync widths when header sections resize
        header.sectionResized.connect(self._on_section_resized)

    def _on_input_changed(self, column: int, text: str) -> None:
        """Queue a filter change and restart the debounce timer."""
        self._pending_changes[column] = text
        self._debounce_timer.start()

    def _emit_pending_filters(self) -> None:
        """Emit accumulated filter changes after debounce delay."""
        for col, text in self._pending_changes.items():
            self.filter_changed.emit(col, text)
        self._pending_changes.clear()

    def _on_section_resized(self, index: int, old_size: int, new_size: int) -> None:
        """Update the corresponding filter input width when a header section resizes."""
        widget = self._inputs.get(index)
        if widget is not None:
            widget.setFixedWidth(new_size)
        elif index in self._skip_columns:
            # Update the spacer width
            layout = self.layout()
            if layout is not None:
                item = layout.itemAt(index)
                spacer_widget = item.widget() if item else None
                if spacer_widget is not None:
                    spacer_widget.setFixedWidth(new_size)

    def clear_all(self) -> None:
        """Clear all filter input text without emitting per-column signals.

        The caller is responsible for clearing the proxy model separately
        (avoids N redundant invalidation cycles).
        """
        for widget in self._inputs.values():
            if widget is not None:
                widget.blockSignals(True)
                widget.clear()
                widget.blockSignals(False)

    def set_focus_column(self, column: int) -> None:
        """Set focus to a specific column's filter input."""
        widget = self._inputs.get(column)
        if widget is not None:
            widget.setFocus()
