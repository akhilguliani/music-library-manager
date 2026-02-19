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

    def createEditor(  # type: ignore[override]
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QLineEdit:
        return QLineEdit(parent)

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:  # type: ignore[override]
        value = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if isinstance(editor, QLineEdit):
            editor.setText(value)

    def setModelData(self, editor: QWidget, model: Any, index: QModelIndex) -> None:  # type: ignore[override]
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)


class BPMEditDelegate(QStyledItemDelegate):
    """Delegate for BPM editing with a spin box (0-999, 1 decimal)."""

    def createEditor(  # type: ignore[override]
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QDoubleSpinBox:
        editor = QDoubleSpinBox(parent)
        editor.setRange(0.0, 999.0)
        editor.setDecimals(1)
        editor.setSingleStep(0.1)
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:  # type: ignore[override]
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if isinstance(editor, QDoubleSpinBox):
            try:
                editor.setValue(float(text))
            except (ValueError, TypeError):
                editor.setValue(0.0)

    def setModelData(self, editor: QWidget, model: Any, index: QModelIndex) -> None:  # type: ignore[override]
        if isinstance(editor, QDoubleSpinBox):
            model.setData(index, str(editor.value()), Qt.ItemDataRole.EditRole)


class KeyEditDelegate(QStyledItemDelegate):
    """Delegate for musical key editing with an editable combo box."""

    def createEditor(  # type: ignore[override]
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QComboBox:
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.addItems(STANDARD_KEYS)
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:  # type: ignore[override]
        value = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if isinstance(editor, QComboBox):
            idx = editor.findText(value)
            if idx >= 0:
                editor.setCurrentIndex(idx)
            else:
                editor.setEditText(value)

    def setModelData(self, editor: QWidget, model: Any, index: QModelIndex) -> None:  # type: ignore[override]
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class EnergyEditDelegate(QStyledItemDelegate):
    """Delegate for energy editing with a spin box (1-10)."""

    def createEditor(  # type: ignore[override]
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QSpinBox:
        editor = QSpinBox(parent)
        editor.setRange(1, 10)
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:  # type: ignore[override]
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if isinstance(editor, QSpinBox):
            try:
                editor.setValue(int(text))
            except (ValueError, TypeError):
                editor.setValue(5)

    def setModelData(self, editor: QWidget, model: Any, index: QModelIndex) -> None:  # type: ignore[override]
        if isinstance(editor, QSpinBox):
            model.setData(index, str(editor.value()), Qt.ItemDataRole.EditRole)
