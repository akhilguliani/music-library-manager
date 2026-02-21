"""Command palette for quick access to commands (Cmd+K)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class CommandItem(NamedTuple):
    name: str
    shortcut: str
    category: str
    callback: Callable[[], Any]


class CommandPalette(QDialog):
    """Floating search dialog for instant command access."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedWidth(500)
        self.setMaximumHeight(400)

        self._commands: list[CommandItem] = []
        self._item_commands: dict[int, CommandItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Type a command...")
        self._search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search)

        self._results = QListWidget()
        self._results.itemActivated.connect(self._execute_item)
        layout.addWidget(self._results)

        # Install event filter for keyboard navigation
        self._search.installEventFilter(self)

    def register_commands(self, commands: list[CommandItem]) -> None:
        """Register available commands."""
        self._commands = list(commands)

    def show_palette(self) -> None:
        """Show the palette centered near top of parent window."""
        self._search.clear()
        self._populate_results("")

        parent_widget = self.parentWidget()
        if parent_widget:
            global_pos = parent_widget.mapToGlobal(parent_widget.rect().topLeft())
            x = global_pos.x() + (parent_widget.width() - self.width()) // 2
            y = global_pos.y() + 80
            self.move(x, y)

        self.show()
        self._search.setFocus()

    def eventFilter(self, obj, event):
        """Handle keyboard navigation in search field."""
        if obj == self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                row = self._results.currentRow()
                if row < self._results.count() - 1:
                    self._results.setCurrentRow(row + 1)
                return True
            elif key == Qt.Key.Key_Up:
                row = self._results.currentRow()
                if row > 0:
                    self._results.setCurrentRow(row - 1)
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._execute_current()
                return True
            elif key == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def _on_search_changed(self, text: str) -> None:
        self._populate_results(text)

    def _populate_results(self, query: str) -> None:
        self._results.clear()
        self._item_commands.clear()
        query_lower = query.lower()

        matched = []
        for cmd in self._commands:
            if (
                not query_lower
                or query_lower in cmd.name.lower()
                or query_lower in cmd.category.lower()
            ):
                matched.append(cmd)

        for idx, cmd in enumerate(matched[:10]):
            display = f"{cmd.name}"
            if cmd.shortcut:
                display = f"{cmd.name}    {cmd.shortcut}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self._item_commands[idx] = cmd
            self._results.addItem(item)

        if self._results.count() > 0:
            self._results.setCurrentRow(0)

    def _execute_item(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.ItemDataRole.UserRole)
        cmd = self._item_commands.get(idx)
        if cmd:
            self.close()
            cmd.callback()

    def _execute_current(self) -> None:
        item = self._results.currentItem()
        if item:
            self._execute_item(item)
