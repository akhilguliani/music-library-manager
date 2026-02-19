"""Centralized theme system for VDJ Manager Desktop Application.

Provides color constants, status color helpers, and a complete QSS stylesheet
generator so that individual widgets no longer need inline setStyleSheet() calls.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    return f"""
/* ---- Global ---- */
QMainWindow, QDialog {{
    background-color: {t.bg_primary};
    color: {t.text_primary};
}}
QWidget {{
    color: {t.text_primary};
    font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
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
    background-color: {t.bg_pressed};
    border-color: {t.border_light};
}}
QPushButton:pressed {{
    background-color: {t.accent_pressed};
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
    background-color: {t.accent_hover};
    border-color: {t.accent_hover};
}}
QPushButton[class="danger"] {{
    color: {t.status_error};
    font-weight: bold;
    border: none;
    background: transparent;
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
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {t.border_focus};
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
}}
QScrollBar::handle:vertical {{
    background-color: {t.scrollbar_handle};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {t.scrollbar_handle_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background-color: {t.scrollbar_bg};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {t.scrollbar_handle};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {t.scrollbar_handle_hover};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
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
    border: 1px solid {t.border};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    color: {t.text_primary};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    padding: 0 6px;
    color: {t.text_secondary};
}}

/* ---- Checkboxes & Radios ---- */
QCheckBox, QRadioButton {{
    color: {t.text_primary};
    spacing: 6px;
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

/* ---- Splitter ---- */
QSplitter::handle {{
    background-color: {t.border};
}}
QSplitter::handle:hover {{
    background-color: {t.border_light};
}}

/* ---- Tooltips ---- */
QToolTip {{
    background-color: {t.bg_surface_alt};
    color: {t.text_primary};
    border: 1px solid {t.border};
    padding: 4px 8px;
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
}}
QMenu::item:selected {{
    background-color: {t.bg_selected};
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

/* ---- Message boxes ---- */
QMessageBox {{
    background-color: {t.bg_primary};
}}
QMessageBox QLabel {{
    color: {t.text_primary};
}}
"""
