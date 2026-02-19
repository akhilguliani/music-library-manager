"""Multi-column filter proxy model for per-column filtering."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt


class MultiColumnFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that filters rows based on per-column regex patterns.

    Each column can have an independent filter pattern. A row is accepted
    only if it matches ALL active column filters (AND logic).
    """

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._column_filters: dict[int, re.Pattern[str]] = {}

    def set_column_filter(self, column: int, pattern: str) -> None:
        """Set a filter pattern for a specific column.

        Args:
            column: Column index to filter.
            pattern: Regex pattern string. Empty string clears the filter.
        """
        if pattern:
            try:
                self._column_filters[column] = re.compile(pattern, re.IGNORECASE)
            except re.error:
                # Invalid regex — treat as literal substring
                self._column_filters[column] = re.compile(
                    re.escape(pattern), re.IGNORECASE
                )
        else:
            self._column_filters.pop(column, None)
        self.invalidate()

    def clear_all_filters(self) -> None:
        """Clear all column filters."""
        self._column_filters.clear()
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # type: ignore[override]
        """Accept a row only if it matches all active column filters."""
        if not self._column_filters:
            return True

        model = self.sourceModel()
        if model is None:
            return True

        for col, pattern in self._column_filters.items():
            index = model.index(source_row, col, source_parent)
            data = model.data(index, Qt.ItemDataRole.DisplayRole)
            text = str(data) if data is not None else ""
            if not pattern.search(text):
                return False

        return True
