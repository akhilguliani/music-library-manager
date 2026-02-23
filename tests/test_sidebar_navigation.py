"""Tests for SidebarWidget and SidebarNavigationProvider."""

from __future__ import annotations

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget

from vdj_manager.ui.navigation import (
    NavigationItem,
    NavigationProvider,
    SidebarNavigationProvider,
    SidebarWidget,
)


@pytest.fixture(scope="module")
def qapp():
    """Module-scoped QApplication for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def sidebar(qapp):
    """Create a SidebarWidget."""
    return SidebarWidget()


@pytest.fixture()
def sidebar_setup(qapp):
    """Create a SidebarWidget + QStackedWidget with 3 panels registered."""
    sidebar = SidebarWidget()
    stack = QStackedWidget()
    provider = SidebarNavigationProvider(sidebar, stack)

    items = []
    for name, icon, shortcut in [
        ("Database", "\u25c9", "Ctrl+1"),
        ("Normalization", "\u224b", "Ctrl+2"),
        ("Files", "\u229e", "Ctrl+3"),
    ]:
        panel = QWidget()
        item = NavigationItem(name=name, icon=icon, shortcut=shortcut, panel=panel)
        provider.register_panel(item)
        items.append(item)

    return provider, sidebar, stack, items


def test_sidebar_widget_creation(sidebar):
    """SidebarWidget can be created without error."""
    assert sidebar is not None
    assert sidebar.objectName() == "SidebarWidget"


def test_add_item_creates_button(sidebar):
    """add_item creates a button in the sidebar."""
    panel = QWidget()
    item = NavigationItem("Test", "T", "Ctrl+1", panel)
    sidebar.add_item(item)

    assert "Test" in sidebar._buttons
    assert sidebar._buttons["Test"].nav_name == "Test"


def test_set_active_highlights_button(sidebar):
    """set_active sets the active property on the correct button."""
    for name in ("A", "B"):
        panel = QWidget()
        sidebar.add_item(NavigationItem(name, "", "", panel))

    sidebar.set_active("A")
    assert sidebar._buttons["A"].property("active") is True
    assert sidebar._buttons["B"].property("active") is False

    sidebar.set_active("B")
    assert sidebar._buttons["A"].property("active") is False
    assert sidebar._buttons["B"].property("active") is True


def test_panel_requested_signal(sidebar, qapp):
    """Clicking a sidebar button emits panel_requested."""
    panel = QWidget()
    sidebar.add_item(NavigationItem("Test", "T", "", panel))

    signals = []
    sidebar.panel_requested.connect(lambda name: signals.append(name))

    sidebar._buttons["Test"].click()
    qapp.processEvents()

    assert signals == ["Test"]


def test_set_sections_adds_headers(sidebar):
    """set_sections inserts section header labels."""
    for name in ("Database", "Files", "Player"):
        panel = QWidget()
        sidebar.add_item(NavigationItem(name, "", "", panel))

    sidebar.set_sections(
        [
            ("Library", ["Database"]),
            ("Tools", ["Files"]),
            ("Player", ["Player"]),
        ]
    )

    # Count QLabel section headers in the layout
    from PySide6.QtWidgets import QLabel

    headers = []
    for i in range(sidebar._layout.count()):
        widget = sidebar._layout.itemAt(i).widget()
        if isinstance(widget, QLabel) and widget.objectName() == "SidebarSectionHeader":
            headers.append(widget.text())

    assert len(headers) == 3
    assert headers == ["LIBRARY", "TOOLS", "PLAYER"]


def test_provider_implements_protocol(qapp):
    """SidebarNavigationProvider is a NavigationProvider."""
    sidebar = SidebarWidget()
    stack = QStackedWidget()
    provider = SidebarNavigationProvider(sidebar, stack)
    assert isinstance(provider, NavigationProvider)


def test_register_panel(sidebar_setup):
    """register_panel grows panel_names."""
    provider, sidebar, stack, items = sidebar_setup
    assert provider.panel_names() == ["Database", "Normalization", "Files"]
    assert stack.count() == 3


def test_navigate_to_changes_stack(sidebar_setup):
    """navigate_to changes the QStackedWidget index."""
    provider, sidebar, stack, items = sidebar_setup
    assert provider.navigate_to("Files") is True
    assert stack.currentIndex() == 2


def test_navigate_to_unknown_returns_false(sidebar_setup):
    """navigate_to unknown panel returns False."""
    provider, sidebar, stack, items = sidebar_setup
    assert provider.navigate_to("NonExistent") is False


def test_current_panel_name_after_navigate(sidebar_setup):
    """current_panel_name returns correct name after navigation."""
    provider, sidebar, stack, items = sidebar_setup

    provider.navigate_to("Normalization")
    assert provider.current_panel_name() == "Normalization"

    provider.navigate_to("Database")
    assert provider.current_panel_name() == "Database"
