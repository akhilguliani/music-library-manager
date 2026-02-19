"""Delegates for inline tag editing in the track table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
    QStyledItemDelegate,
    QWidget,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStyleOptionViewItem

# Standard musical keys in Camelot / Open Key notation order
STANDARD_KEYS = [
    "",
    "Am",
    "Em",
    "Bm",
    "F#m",
    "C#m",
    "G#m",
    "D#m",
    "A#m",
    "Fm",
    "Cm",
    "Gm",
    "Dm",
    "C",
    "G",
    "D",
    "A",
    "E",
    "B",
    "F#",
    "C#",
    "G#",
    "D#",
    "A#",
    "F",
]


class TextEditDelegate(QStyledItemDelegate):
    """Delegate for text fields (Title, Artist, Genre)."""

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        editor = QLineEdit(parent)
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        value = index.data(Qt.ItemDataRole.DisplayRole) or ""
        editor.setText(value)  # type: ignore[union-attr]

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex
    ) -> None:
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)  # type: ignore[union-attr]


class BPMEditDelegate(QStyledItemDelegate):
    """Delegate for BPM editing with a spin box (0-999, 1 decimal)."""

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        editor = QDoubleSpinBox(parent)
        editor.setRange(0.0, 999.0)
        editor.setDecimals(1)
        editor.setSingleStep(0.1)
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        try:
            editor.setValue(float(text))  # type: ignore[union-attr]
        except (ValueError, TypeError):
            editor.setValue(0.0)  # type: ignore[union-attr]

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex
    ) -> None:
        value = editor.value()  # type: ignore[union-attr]
        model.setData(index, str(value), Qt.ItemDataRole.EditRole)


class KeyEditDelegate(QStyledItemDelegate):
    """Delegate for musical key editing with an editable combo box."""

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.addItems(STANDARD_KEYS)
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        value = index.data(Qt.ItemDataRole.DisplayRole) or ""
        combo = editor  # type: ignore[union-attr]
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setEditText(value)

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex
    ) -> None:
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)  # type: ignore[union-attr]


class EnergyEditDelegate(QStyledItemDelegate):
    """Delegate for energy editing with a spin box (1-10)."""

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        editor = QSpinBox(parent)
        editor.setRange(1, 10)
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        try:
            editor.setValue(int(text))  # type: ignore[union-attr]
        except (ValueError, TypeError):
            editor.setValue(5)  # type: ignore[union-attr]

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex
    ) -> None:
        value = editor.value()  # type: ignore[union-attr]
        model.setData(index, str(value), Qt.ItemDataRole.EditRole)
