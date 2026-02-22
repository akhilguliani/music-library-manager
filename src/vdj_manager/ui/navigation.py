"""Navigation abstraction for panel switching."""

from __future__ import annotations

from typing import NamedTuple, Protocol, runtime_checkable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.ui.theme import ThemeManager


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


class SidebarItemButton(QPushButton):
    """A single navigation item in the sidebar."""

    def __init__(self, name: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.nav_name = name
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setFixedWidth(20)
            icon_label.setStyleSheet("font-size: 16px; background: transparent; border: none;")
            layout.addWidget(icon_label)

        name_label = QLabel(name)
        name_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(name_label)
        layout.addStretch()

    def set_active(self, active: bool) -> None:
        """Set the active state for QSS styling."""
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)


class SidebarWidget(QWidget):
    """Persistent left sidebar with section-grouped navigation items."""

    panel_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setObjectName("SidebarWidget")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(0)

        self._buttons: dict[str, SidebarItemButton] = {}
        self._layout.addStretch()

    def add_item(self, item: NavigationItem) -> None:
        """Add a navigation item button to the sidebar."""
        btn = SidebarItemButton(item.name, item.icon)
        btn.clicked.connect(lambda: self.panel_requested.emit(item.name))
        self._buttons[item.name] = btn
        # Insert before the stretch at the end
        self._layout.insertWidget(self._layout.count() - 1, btn)

    def set_sections(self, sections: list[tuple[str, list[str]]]) -> None:
        """Rebuild layout with section headers between groups.

        Args:
            sections: List of (section_name, [panel_names]) tuples.
        """
        # Remove all items from layout (keep button references in _buttons)
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget and widget not in self._buttons.values():
                widget.deleteLater()
            elif not widget:
                # Spacer items: delete the layout item to free memory
                del item

        # Re-add with section headers
        for section_name, panel_names in sections:
            header = QLabel(section_name.upper())
            header.setObjectName("SidebarSectionHeader")
            t = ThemeManager().theme
            header.setStyleSheet(
                f"font-size: 11px; font-weight: bold; color: {t.text_tertiary};"
                " padding: 12px 12px 4px 12px; background: transparent;"
            )
            self._layout.addWidget(header)
            for name in panel_names:
                btn = self._buttons.get(name)
                if btn is not None:
                    self._layout.addWidget(btn)

        self._layout.addStretch()

    def set_active(self, name: str) -> None:
        """Highlight the active panel button and deactivate others."""
        for btn_name, btn in self._buttons.items():
            btn.set_active(btn_name == name)


class SidebarNavigationProvider:
    """NavigationProvider backed by a SidebarWidget + QStackedWidget."""

    def __init__(self, sidebar: SidebarWidget, stack: QStackedWidget) -> None:
        self._sidebar = sidebar
        self._stack = stack
        self._panels: dict[str, int] = {}
        self._order: list[str] = []
        self._current: str = ""
        sidebar.panel_requested.connect(self.navigate_to)

    def navigate_to(self, name: str) -> bool:
        """Navigate to a panel by name."""
        index = self._panels.get(name)
        if index is None:
            return False
        self._stack.setCurrentIndex(index)
        self._sidebar.set_active(name)
        self._current = name
        return True

    def current_panel_name(self) -> str:
        """Get the name of the currently visible panel."""
        return self._current

    def register_panel(self, item: NavigationItem) -> None:
        """Register a panel — adds to stack and sidebar."""
        idx = self._stack.addWidget(item.panel)
        self._panels[item.name] = idx
        self._order.append(item.name)
        self._sidebar.add_item(item)
        # Auto-activate first panel so sidebar always shows an active state
        if len(self._panels) == 1:
            self._current = item.name
            self._sidebar.set_active(item.name)

    def panel_names(self) -> list[str]:
        """Get all registered panel names in registration order."""
        return list(self._order)
