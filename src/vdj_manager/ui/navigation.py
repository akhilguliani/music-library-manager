"""Navigation abstraction for panel switching."""

from __future__ import annotations

from typing import NamedTuple, Protocol, runtime_checkable

from PySide6.QtWidgets import QTabWidget, QWidget


class NavigationItem(NamedTuple):
    """A navigable panel registration."""

    name: str
    icon: str
    shortcut: str
    panel: QWidget


@runtime_checkable
class NavigationProvider(Protocol):
    """Protocol for navigation implementations (tab widget, sidebar, etc.)."""

    def navigate_to(self, name: str) -> bool:
        """Navigate to a panel by name. Returns True if successful."""
        ...

    def current_panel_name(self) -> str:
        """Get the name of the currently visible panel."""
        ...

    def register_panel(self, item: NavigationItem) -> None:
        """Register a panel for navigation."""
        ...

    def panel_names(self) -> list[str]:
        """Get all registered panel names."""
        ...


class TabNavigationProvider:
    """NavigationProvider backed by a QTabWidget."""

    def __init__(self, tab_widget: QTabWidget) -> None:
        self._tab_widget = tab_widget
        self._panels: dict[str, int] = {}  # name -> tab index

    def navigate_to(self, name: str) -> bool:
        index = self._panels.get(name)
        if index is not None:
            self._tab_widget.setCurrentIndex(index)
            return True
        return False

    def current_panel_name(self) -> str:
        current = self._tab_widget.currentIndex()
        for name, idx in self._panels.items():
            if idx == current:
                return name
        return ""

    def register_panel(self, item: NavigationItem) -> None:
        # Find the tab index for this panel
        for i in range(self._tab_widget.count()):
            if self._tab_widget.widget(i) is item.panel:
                self._panels[item.name] = i
                return
        # If panel not found in tabs, add it
        idx = self._tab_widget.addTab(item.panel, item.name)
        self._panels[item.name] = idx

    def panel_names(self) -> list[str]:
        return list(self._panels.keys())
