"""Empty state widgets for panels without data."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from vdj_manager.ui.theme import ThemeManager


class EmptyStateWidget(QWidget):
    """Centered icon + title + description for empty panels.

    Example usage:
        empty = EmptyStateWidget(
            icon="📁",
            title="No database loaded",
            description="Select a database and click Load to get started.",
        )
    """

    def __init__(
        self,
        icon: str = "",
        title: str = "",
        description: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title_label: QLabel | None = None

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(
                f"font-size: 48px; color: {ThemeManager().theme.text_disabled};"
            )
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)

        if title:
            self._title_label = QLabel(title)
            self._title_label.setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {ThemeManager().theme.text_secondary};"
            )
            self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet(f"font-size: 12px; color: {ThemeManager().theme.text_muted};")
            desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

    @property
    def title_text(self) -> str:
        """Get the title text (for testing)."""
        if self._title_label is not None:
            return self._title_label.text()
        return ""
