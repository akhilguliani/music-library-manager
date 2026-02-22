"""Keyboard shortcuts help dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.ui.theme import ThemeManager

# Shortcut definitions grouped by category
SHORTCUT_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Navigation",
        [
            ("Ctrl+K", "Open command palette"),
            ("Ctrl+1..7", "Switch to tab 1-7"),
        ],
    ),
    (
        "Track Browser",
        [
            ("Ctrl+F", "Toggle column filters"),
            ("Ctrl+B", "Toggle column browser"),
            ("Ctrl+L", "Focus search bar"),
            ("F2", "Edit selected cell"),
            ("Ctrl+Enter", "Play selected track"),
        ],
    ),
    (
        "Playback",
        [
            ("Space", "Play / Pause"),
            ("Ctrl+Right", "Next track"),
            ("Ctrl+Left", "Previous track"),
        ],
    ),
    (
        "General",
        [
            ("?", "Show this dialog"),
            ("Escape", "Close dialog / cancel"),
        ],
    ),
]


class ShortcutsDialog(QDialog):
    """Dialog displaying all keyboard shortcuts grouped by category."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(400, 300)
        self.setMaximumSize(600, 500)

        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)

        for category, shortcuts in SHORTCUT_GROUPS:
            # Category header
            header = QLabel(category)
            header.setStyleSheet(
                f"font-weight: bold; font-size: 13px; color: {ThemeManager().theme.accent};"
            )
            content_layout.addWidget(header)

            for key, description in shortcuts:
                row = QHBoxLayout()
                key_label = QLabel(key)
                key_label.setStyleSheet(
                    f"font-family: monospace; font-weight: bold; "
                    f"color: {ThemeManager().theme.text_primary}; "
                    f"background: {ThemeManager().theme.bg_surface}; "
                    f"padding: 2px 8px; border-radius: 3px;"
                )
                key_label.setFixedWidth(130)
                row.addWidget(key_label)

                desc_label = QLabel(description)
                desc_label.setStyleSheet(f"color: {ThemeManager().theme.text_secondary};")
                row.addWidget(desc_label)
                row.addStretch()

                content_layout.addLayout(row)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setDefault(True)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
