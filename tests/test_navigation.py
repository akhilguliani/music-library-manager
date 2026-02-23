"""Tests for NavigationProvider protocol and TabNavigationProvider."""

from __future__ import annotations

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from vdj_manager.ui.navigation import (
    NavigationItem,
    NavigationProvider,
    TabNavigationProvider,
)


@pytest.fixture(scope="module")
def qapp():
    """Module-scoped QApplication for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def tab_setup(qapp):
    """Create a QTabWidget with 3 panels registered as NavigationItems."""
    tab_widget = QTabWidget()
    panels = []
    items = []
    for i, (name, icon, shortcut) in enumerate(
        [
            ("Database", "database", "Ctrl+1"),
            ("Normalization", "normalize", "Ctrl+2"),
            ("Files", "files", "Ctrl+3"),
        ]
    ):
        panel = QWidget()
        tab_widget.addTab(panel, name)
        panels.append(panel)
        items.append(NavigationItem(name=name, icon=icon, shortcut=shortcut, panel=panel))

    provider = TabNavigationProvider(tab_widget)
    for item in items:
        provider.register_panel(item)

    return provider, tab_widget, panels, items


def test_tab_navigation_provider_creation(qapp):
    """TabNavigationProvider can be created without error."""
    tab_widget = QTabWidget()
    provider = TabNavigationProvider(tab_widget)
    assert provider is not None


def test_register_panel(tab_setup):
    """Registered panels appear in panel_names."""
    provider, _tab_widget, _panels, _items = tab_setup
    names = provider.panel_names()
    assert names == ["Database", "Normalization", "Files"]


def test_navigate_to(tab_setup):
    """navigate_to registered panel changes tab and returns True."""
    provider, tab_widget, _panels, _items = tab_setup
    result = provider.navigate_to("Files")
    assert result is True
    assert tab_widget.currentIndex() == 2


def test_navigate_to_unknown(tab_setup):
    """navigate_to unknown panel returns False."""
    provider, _tab_widget, _panels, _items = tab_setup
    result = provider.navigate_to("NonExistent")
    assert result is False


def test_current_panel_name(tab_setup):
    """current_panel_name returns correct name after navigation."""
    provider, _tab_widget, _panels, _items = tab_setup
    provider.navigate_to("Normalization")
    assert provider.current_panel_name() == "Normalization"

    provider.navigate_to("Database")
    assert provider.current_panel_name() == "Database"


def test_implements_protocol(qapp):
    """TabNavigationProvider is an instance of NavigationProvider protocol."""
    tab_widget = QTabWidget()
    provider = TabNavigationProvider(tab_widget)
    assert isinstance(provider, NavigationProvider)
