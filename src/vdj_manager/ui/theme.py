"""Centralized theme system for VDJ Manager Desktop Application.

Provides color constants, status color helpers, and a complete QSS stylesheet
generator so that individual widgets no longer need inline setStyleSheet() calls.
"""

from __future__ import annotations

from dataclasses import dataclass


def _lighten(hex_color: str, factor: float = 0.2) -> str:
    """Lighten a hex color by blending it toward white.

    Args:
        hex_color: A hex color string (e.g. "#1a1a2e" or "#fff").
        factor: Blend factor toward white, 0.0 = unchanged, 1.0 = white.

    Returns:
        A 7-character hex color string (e.g. "#3a3a4e").
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color: str, factor: float = 0.2) -> str:
    """Darken a hex color by blending it toward black.

    Args:
        hex_color: A hex color string (e.g. "#5588cc" or "#fff").
        factor: Blend factor toward black, 0.0 = unchanged, 1.0 = black.

    Returns:
        A 7-character hex color string (e.g. "#446da3").
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = max(0, int(r * (1.0 - factor)))
    g = max(0, int(g * (1.0 - factor)))
    b = max(0, int(b * (1.0 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass(frozen=True)
class ThemeColors:
    """Complete color palette for a UI theme."""

    # Backgrounds
    bg_primary: str = "#1a1a2e"
    bg_secondary: str = "#16213e"
    bg_tertiary: str = "#0f3460"
    bg_input: str = "#222240"
    bg_surface: str = "#222"
    bg_surface_alt: str = "#333"
    bg_hover: str = "#2a2a4e"
    bg_pressed: str = "#3a3a5e"
    bg_selected: str = "#1a3a6e"

    # Text
    text_primary: str = "#e0e0e0"
    text_secondary: str = "#aaaaaa"
    text_tertiary: str = "#888888"
    text_muted: str = "#666666"
    text_disabled: str = "#555555"

    # Borders
    border: str = "#444444"
    border_light: str = "#555555"
    border_focus: str = "#5588cc"

    # Accent
    accent: str = "#5588cc"
    accent_hover: str = "#6699dd"
    accent_pressed: str = "#4477bb"

    # Status colors
    status_success: str = "#4caf50"
    status_error: str = "#f44336"
    status_warning: str = "#ff9800"
    status_info: str = "#2196f3"
    status_loading: str = "#2196f3"

    # Scrollbar
    scrollbar_bg: str = "#1a1a2e"
    scrollbar_handle: str = "#444444"
    scrollbar_handle_hover: str = "#555555"

    # Tab bar
    tab_bg: str = "#16213e"
    tab_selected: str = "#1a1a2e"
    tab_hover: str = "#1e2a4e"

    # Progress bar
    progress_bg: str = "#2a2a4e"
    progress_chunk: str = "#5588cc"

    # Player-specific
    player_bg: str = "#1a1a2e"
    player_button_bg: str = "#2a2a4e"
    player_button_hover: str = "#3a3a5e"

    # Waveform
    waveform_bg: str = "#0d1117"
    waveform_played_top: str = "#4fc3f7"
    waveform_played_bottom: str = "#0288d1"
    waveform_unplayed_top: str = "#1565c0"
    waveform_unplayed_bottom: str = "#0d47a1"
    waveform_playhead: str = "#ffffff"


DARK_THEME = ThemeColors()

LIGHT_THEME = ThemeColors(
    bg_primary="#f5f5f5",
    bg_secondary="#e8e8e8",
    bg_tertiary="#dcdcdc",
    bg_input="#ffffff",
    bg_surface="#ffffff",
    bg_surface_alt="#f0f0f0",
    bg_hover="#e0e0e0",
    bg_pressed="#d0d0d0",
    bg_selected="#cce0ff",
    text_primary="#1a1a1a",
    text_secondary="#555555",
    text_tertiary="#777777",
    text_muted="#999999",
    text_disabled="#bbbbbb",
    border="#cccccc",
    border_light="#dddddd",
    border_focus="#4488cc",
    accent="#2266bb",
    accent_hover="#3377cc",
    accent_pressed="#1155aa",
    status_success="#2e7d32",
    status_error="#c62828",
    status_warning="#ef6c00",
    status_info="#1565c0",
    status_loading="#1565c0",
    scrollbar_bg="#f0f0f0",
    scrollbar_handle="#cccccc",
    scrollbar_handle_hover="#bbbbbb",
    tab_bg="#e8e8e8",
    tab_selected="#f5f5f5",
    tab_hover="#e0e0e0",
    progress_bg="#e0e0e0",
    progress_chunk="#2266bb",
    player_bg="#f5f5f5",
    player_button_bg="#e0e0e0",
    player_button_hover="#d0d0d0",
    waveform_bg="#e8e8e8",
    waveform_played_top="#42a5f5",
    waveform_played_bottom="#1976d2",
    waveform_unplayed_top="#90caf9",
    waveform_unplayed_bottom="#bbdefb",
    waveform_playhead="#000000",
)


class ThemeManager:
    """Singleton that holds the active theme and provides color helpers."""

    _instance: ThemeManager | None = None
    _theme: ThemeColors = DARK_THEME

    def __new__(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def theme(self) -> ThemeColors:
        return self._theme

    @theme.setter
    def theme(self, value: ThemeColors) -> None:
        self._theme = value

    def status_color(self, status: str) -> str:
        """Return the appropriate color hex for a status keyword.

        Recognized statuses: success/ok/complete, error/fail, warning/paused,
        info/loading/running.
        """
        s = status.lower()
        t = self._theme
        if s in ("success", "ok", "complete", "completed", "done"):
            return t.status_success
        if s in ("error", "fail", "failed", "cancelled"):
            return t.status_error
        if s in ("warning", "paused", "partial"):
            return t.status_warning
        if s in ("info", "loading", "running", "active"):
            return t.status_info
        return t.text_secondary


def generate_stylesheet(theme: ThemeColors | None = None) -> str:
    """Generate a complete application QSS stylesheet from theme colors."""
    t = theme or DARK_THEME

    # Pre-compute derived colors using lighten/darken helpers
    btn_hover = _lighten(t.bg_hover, 0.15)
    btn_pressed = _darken(t.bg_hover, 0.15)
    accent_light = _lighten(t.accent, 0.15)
    accent_dark = _darken(t.accent, 0.2)
    input_hover_border = _lighten(t.border, 0.2)
    scrollbar_pressed = _lighten(t.scrollbar_handle_hover, 0.15)
    table_item_hover = _lighten(t.bg_secondary, 0.08)
    list_item_hover = _lighten(t.bg_secondary, 0.08)
    splitter_pressed = _lighten(t.border_light, 0.15)
    groupbox_border = _lighten(t.border, 0.08)
    danger_hover = _lighten(t.status_error, 0.15)
    danger_pressed = _darken(t.status_error, 0.2)
    slider_handle_pressed = _darken(t.accent, 0.15)
    tab_hover_border = _lighten(t.tab_hover, 0.1)

    return f"""
/* ---- Global ---- */
QMainWindow, QDialog {{
    background-color: {t.bg_primary};
    color: {t.text_primary};
}}
QWidget {{
    color: {t.text_primary};
}}

/* ---- Labels ---- */
QLabel {{
    color: {t.text_primary};
    background: transparent;
}}
QLabel[class="info"] {{
    color: {t.text_tertiary};
    font-size: 11px;
    padding: 2px 4px;
}}
QLabel[class="metadata"] {{
    color: {t.text_tertiary};
    font-size: 12px;
}}
QLabel[class="title"] {{
    font-size: 18px;
    font-weight: bold;
}}
QLabel[class="subtitle"] {{
    font-size: 14px;
    color: {t.text_secondary};
}}
QLabel[class="caption"] {{
    font-size: 11px;
    color: {t.text_muted};
    padding-left: 4px;
}}
QLabel[class="status-success"] {{
    font-weight: bold;
    color: {t.status_success};
}}
QLabel[class="status-error"] {{
    font-weight: bold;
    color: {t.status_error};
}}
QLabel[class="status-warning"] {{
    font-weight: bold;
    color: {t.status_warning};
}}
QLabel[class="status-info"] {{
    font-weight: bold;
    color: {t.status_info};
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {t.bg_hover};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {btn_hover};
    border-color: {t.border_light};
}}
QPushButton:pressed {{
    background-color: {btn_pressed};
    border-color: {t.accent};
}}
QPushButton:disabled {{
    background-color: {t.bg_secondary};
    color: {t.text_disabled};
    border-color: {t.bg_secondary};
}}
QPushButton[class="accent"] {{
    background-color: {t.accent};
    border-color: {t.accent};
    color: #ffffff;
}}
QPushButton[class="accent"]:hover {{
    background-color: {accent_light};
    border-color: {accent_light};
}}
QPushButton[class="accent"]:pressed {{
    background-color: {accent_dark};
    border-color: {accent_dark};
}}
QPushButton[class="accent"]:disabled {{
    background-color: {_darken(t.accent, 0.4)};
    border-color: {_darken(t.accent, 0.4)};
    color: {t.text_disabled};
}}
QPushButton[class="danger"] {{
    color: {t.status_error};
    font-weight: bold;
    border: none;
    background: transparent;
}}
QPushButton[class="danger"]:hover {{
    color: {danger_hover};
    background-color: {_lighten(t.bg_primary, 0.05)};
}}
QPushButton[class="danger"]:pressed {{
    color: {danger_pressed};
}}

/* ---- Inputs ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {t.bg_input};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {t.accent};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: {input_hover_border};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {t.border_focus};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background-color: {t.bg_secondary};
    color: {t.text_disabled};
    border-color: {t.bg_secondary};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {t.bg_secondary};
    color: {t.text_primary};
    border: 1px solid {t.border};
    selection-background-color: {t.bg_selected};
}}

/* ---- Tabs ---- */
QTabWidget::pane {{
    border: 1px solid {t.border};
    background-color: {t.bg_primary};
}}
QTabBar::tab {{
    background-color: {t.tab_bg};
    color: {t.text_secondary};
    border: 1px solid {t.border};
    border-bottom: none;
    padding: 6px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background-color: {t.tab_selected};
    color: {t.text_primary};
    border-bottom: 2px solid {t.accent};
}}
QTabBar::tab:hover:!selected {{
    background-color: {t.tab_hover};
    color: {t.text_primary};
    border-color: {tab_hover_border};
}}
QTabBar::tab:disabled {{
    color: {t.text_disabled};
    background-color: {t.bg_secondary};
}}

/* ---- Tables & Lists ---- */
QTableView, QTreeView, QListView, QListWidget {{
    background-color: {t.bg_secondary};
    color: {t.text_primary};
    border: 1px solid {t.border};
    gridline-color: {t.border};
    selection-background-color: {t.bg_selected};
    selection-color: {t.text_primary};
    alternate-background-color: {t.bg_primary};
}}
QTableView::item:hover {{
    background-color: {table_item_hover};
}}
QTableView::item:selected {{
    background-color: {t.bg_selected};
    color: {t.text_primary};
}}
QListWidget::item {{
    padding: 3px 6px;
    border-radius: 2px;
}}
QListWidget::item:hover {{
    background-color: {list_item_hover};
}}
QListWidget::item:selected {{
    background-color: {t.bg_selected};
    color: {t.text_primary};
}}
QHeaderView::section {{
    background-color: {t.bg_tertiary};
    color: {t.text_primary};
    padding: 4px 8px;
    border: none;
    border-right: 1px solid {t.border};
    border-bottom: 1px solid {t.border};
}}
QHeaderView::section:hover {{
    background-color: {t.bg_hover};
}}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{
    background-color: {t.scrollbar_bg};
    width: 10px;
    margin: 0;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background-color: {t.scrollbar_handle};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {t.scrollbar_handle_hover};
}}
QScrollBar::handle:vertical:pressed {{
    background-color: {scrollbar_pressed};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background-color: {t.scrollbar_bg};
    height: 10px;
    margin: 0;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background-color: {t.scrollbar_handle};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {t.scrollbar_handle_hover};
}}
QScrollBar::handle:horizontal:pressed {{
    background-color: {scrollbar_pressed};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ---- Progress bar ---- */
QProgressBar {{
    background-color: {t.progress_bg};
    border: 1px solid {t.border};
    border-radius: 4px;
    text-align: center;
    color: {t.text_primary};
    height: 18px;
}}
QProgressBar::chunk {{
    background-color: {t.progress_chunk};
    border-radius: 3px;
}}

/* ---- Group boxes ---- */
QGroupBox {{
    border: 1px solid {groupbox_border};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    color: {t.text_primary};
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    padding: 0 6px;
    color: {t.accent};
    font-weight: bold;
}}

/* ---- Checkboxes & Radios ---- */
QCheckBox, QRadioButton {{
    color: {t.text_primary};
    spacing: 6px;
}}
QCheckBox:hover, QRadioButton:hover {{
    color: {_lighten(t.text_primary, 0.1)};
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {t.text_disabled};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
}}

/* ---- Sliders ---- */
QSlider::groove:horizontal {{
    background-color: {t.progress_bg};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background-color: {t.accent};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background-color: {t.accent_hover};
}}
QSlider::handle:horizontal:pressed {{
    background-color: {slider_handle_pressed};
}}

/* ---- Splitter ---- */
QSplitter::handle {{
    background-color: {t.border};
    border-radius: 1px;
}}
QSplitter::handle:horizontal {{
    width: 3px;
    margin: 4px 0;
}}
QSplitter::handle:vertical {{
    height: 3px;
    margin: 0 4px;
}}
QSplitter::handle:hover {{
    background-color: {t.accent};
}}
QSplitter::handle:pressed {{
    background-color: {splitter_pressed};
}}

/* ---- Scroll Areas & Frames ---- */
QScrollArea {{
    background-color: {t.bg_primary};
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: {t.bg_primary};
}}

/* ---- Tooltips ---- */
QToolTip {{
    background-color: {t.bg_surface_alt};
    color: {t.text_primary};
    border: 1px solid {t.border};
    padding: 4px 8px;
    border-radius: 3px;
}}

/* ---- Menu ---- */
QMenuBar {{
    background-color: {t.bg_secondary};
    color: {t.text_primary};
    border-bottom: 1px solid {t.border};
}}
QMenuBar::item:selected {{
    background-color: {t.bg_hover};
}}
QMenu {{
    background-color: {t.bg_secondary};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 4px;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 5px 24px 5px 12px;
}}
QMenu::item:selected {{
    background-color: {t.bg_selected};
}}
QMenu::item:disabled {{
    color: {t.text_disabled};
}}
QMenu::separator {{
    height: 1px;
    background-color: {t.border};
    margin: 4px 8px;
}}

/* ---- Status bar ---- */
QStatusBar {{
    background-color: {t.bg_secondary};
    color: {t.text_secondary};
    border-top: 1px solid {t.border};
}}

/* ---- MiniPlayer ---- */
MiniPlayer {{
    background-color: {t.player_bg};
}}
MiniPlayer QLabel {{
    color: {t.text_primary};
}}
MiniPlayer QPushButton {{
    color: {t.text_primary};
    background-color: {t.player_button_bg};
    border: 1px solid {t.border};
    border-radius: 4px;
    padding: 2px 6px;
}}
MiniPlayer QPushButton:hover {{
    background-color: {t.player_button_hover};
}}
MiniPlayer QPushButton:pressed {{
    background-color: {_darken(t.player_button_hover, 0.15)};
}}

/* ---- Message boxes ---- */
QMessageBox {{
    background-color: {t.bg_primary};
}}
QMessageBox QLabel {{
    color: {t.text_primary};
}}

/* ---- Sidebar Navigation ---- */
SidebarWidget {{
    background-color: {t.bg_secondary};
    border-right: 1px solid {t.border};
}}
SidebarItemButton {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 8px 12px;
    text-align: left;
    color: {t.text_secondary};
    font-size: 13px;
}}
SidebarItemButton:hover {{
    background-color: {t.bg_hover};
    color: {t.text_primary};
}}
SidebarItemButton:pressed {{
    background-color: {t.bg_pressed};
}}
SidebarItemButton[active="true"] {{
    border-left: 3px solid {t.accent};
    color: {t.text_primary};
    background-color: {t.bg_selected};
    font-weight: bold;
}}
"""
