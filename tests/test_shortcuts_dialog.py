"""Tests for keyboard shortcuts dialog."""

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from vdj_manager.ui.widgets.shortcuts_dialog import SHORTCUT_GROUPS, ShortcutsDialog


@pytest.fixture(scope="module")
def app():
    """Create a QApplication for testing."""
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        app = QApplication(["test"])
        yield app


class TestShortcutsDialog:
    """Tests for ShortcutsDialog."""

    def test_creation(self, app):
        """Test dialog can be created."""
        dialog = ShortcutsDialog()
        assert dialog is not None
        assert dialog.windowTitle() == "Keyboard Shortcuts"

    def test_has_shortcut_groups(self, app):
        """Test SHORTCUT_GROUPS is non-empty."""
        assert len(SHORTCUT_GROUPS) > 0

    def test_all_groups_have_shortcuts(self, app):
        """Test each group has at least one shortcut."""
        for category, shortcuts in SHORTCUT_GROUPS:
            assert len(shortcuts) > 0, f"Category '{category}' has no shortcuts"

    def test_all_shortcuts_have_key_and_description(self, app):
        """Test each shortcut has both a key and description."""
        for category, shortcuts in SHORTCUT_GROUPS:
            for key, desc in shortcuts:
                assert key, f"Empty key in '{category}'"
                assert desc, f"Empty description for '{key}' in '{category}'"

    def test_dialog_has_close_button(self, app):
        """Test dialog has a close button."""
        from PySide6.QtWidgets import QPushButton

        dialog = ShortcutsDialog()
        buttons = dialog.findChildren(QPushButton)
        assert any(b.text() == "Close" for b in buttons)

    def test_dialog_minimum_size(self, app):
        """Test dialog has reasonable minimum size."""
        dialog = ShortcutsDialog()
        assert dialog.minimumWidth() >= 400
        assert dialog.minimumHeight() >= 300
