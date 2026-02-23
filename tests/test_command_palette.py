"""Tests for the command palette widget."""

from __future__ import annotations

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.widgets.command_palette import CommandItem, CommandPalette


@pytest.fixture(scope="module")
def qapp():
    """Provide a QApplication instance for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_commands(n: int = 5) -> list[CommandItem]:
    """Create n dummy commands for testing."""
    return [
        CommandItem(
            name=f"Command {i}",
            shortcut=f"Ctrl+{i}" if i % 2 == 0 else "",
            category=f"Category {i % 3}",
            callback=lambda: None,
        )
        for i in range(n)
    ]


class TestCommandPalette:
    def test_creation(self, qapp):
        """Command palette creates without error."""
        palette = CommandPalette()
        assert palette is not None
        assert palette._search is not None
        assert palette._results is not None
        palette.close()

    def test_register_commands(self, qapp):
        """Registering commands updates the internal list."""
        palette = CommandPalette()
        commands = _make_commands(3)
        palette.register_commands(commands)
        assert len(palette._commands) == 3
        assert palette._commands[0].name == "Command 0"
        assert palette._commands[2].name == "Command 2"
        palette.close()

    def test_search_filters_results(self, qapp):
        """Typing text filters to only matching commands."""
        palette = CommandPalette()
        commands = [
            CommandItem("Open Database", "", "File", lambda: None),
            CommandItem("Save Database", "", "File", lambda: None),
            CommandItem("Analyze Energy", "", "Analysis", lambda: None),
        ]
        palette.register_commands(commands)
        palette._populate_results("Save")
        assert palette._results.count() == 1
        assert "Save Database" in palette._results.item(0).text()
        palette.close()

    def test_empty_search_shows_all(self, qapp):
        """Empty search shows all commands (up to max)."""
        palette = CommandPalette()
        commands = _make_commands(5)
        palette.register_commands(commands)
        palette._populate_results("")
        assert palette._results.count() == 5
        palette.close()

    def test_max_results_limit(self, qapp):
        """More than 10 commands shows only 10 results."""
        palette = CommandPalette()
        commands = _make_commands(15)
        palette.register_commands(commands)
        palette._populate_results("")
        assert palette._results.count() == 10
        palette.close()

    def test_execute_calls_callback(self, qapp):
        """Activating an item calls its callback."""
        calls: list[int] = []
        cmd = CommandItem("Test", "", "cat", lambda: calls.append(1))
        palette = CommandPalette()
        palette.register_commands([cmd])
        palette._populate_results("")
        assert palette._results.count() == 1
        item = palette._results.item(0)
        palette._execute_item(item)
        assert len(calls) == 1

    def test_escape_closes(self, qapp):
        """Pressing Escape closes the dialog."""
        palette = CommandPalette()
        palette.register_commands(_make_commands(3))
        palette.show_palette()
        QApplication.processEvents()

        QTest.keyClick(palette._search, Qt.Key.Key_Escape)
        QApplication.processEvents()

        assert not palette.isVisible()

    def test_case_insensitive_search(self, qapp):
        """Uppercase search matches lowercase command names."""
        palette = CommandPalette()
        commands = [
            CommandItem("open database", "", "file", lambda: None),
            CommandItem("save database", "", "file", lambda: None),
            CommandItem("analyze energy", "", "analysis", lambda: None),
        ]
        palette.register_commands(commands)
        palette._populate_results("OPEN")
        assert palette._results.count() == 1
        assert "open database" in palette._results.item(0).text()
        palette.close()
