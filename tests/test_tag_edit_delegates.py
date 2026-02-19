"""Tests for tag edit delegates."""

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QWidget

from vdj_manager.ui.delegates.tag_edit_delegates import (
    STANDARD_KEYS,
    BPMEditDelegate,
    EnergyEditDelegate,
    KeyEditDelegate,
    TextEditDelegate,
)


@pytest.fixture(scope="module")
def app():
    """Create a QApplication for testing."""
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        app = QApplication(["test"])
        yield app


@pytest.fixture
def model_with_data(app):
    """Create a model with sample data."""
    model = QStandardItemModel(1, 6)
    model.setItem(0, 0, QStandardItem("Track One"))
    model.setItem(0, 1, QStandardItem("Artist One"))
    model.setItem(0, 2, QStandardItem("120.0"))
    model.setItem(0, 3, QStandardItem("Am"))
    model.setItem(0, 4, QStandardItem("7"))
    model.setItem(0, 5, QStandardItem("Dance"))
    return model


@pytest.fixture
def parent_widget(app):
    """Create a parent widget for editor creation."""
    return QWidget()


class TestTextEditDelegate:
    """Tests for TextEditDelegate."""

    def test_create_editor(self, parent_widget, model_with_data):
        """Test editor creation returns QLineEdit."""
        delegate = TextEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 0)
        editor = delegate.createEditor(parent_widget, option, index)
        assert editor is not None
        assert hasattr(editor, "text")

    def test_set_editor_data(self, parent_widget, model_with_data):
        """Test editor is populated with model data."""
        delegate = TextEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 0)
        editor = delegate.createEditor(parent_widget, option, index)
        delegate.setEditorData(editor, index)
        assert editor.text() == "Track One"

    def test_set_model_data(self, parent_widget, model_with_data):
        """Test editor data is committed to model."""
        delegate = TextEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 0)
        editor = delegate.createEditor(parent_widget, option, index)
        editor.setText("New Title")
        delegate.setModelData(editor, model_with_data, index)
        assert model_with_data.data(index) == "New Title"


class TestBPMEditDelegate:
    """Tests for BPMEditDelegate."""

    def test_create_editor(self, parent_widget, model_with_data):
        """Test editor creation returns QDoubleSpinBox."""
        delegate = BPMEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 2)
        editor = delegate.createEditor(parent_widget, option, index)
        assert editor is not None
        assert hasattr(editor, "value")

    def test_set_editor_data(self, parent_widget, model_with_data):
        """Test editor is populated with BPM value."""
        delegate = BPMEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 2)
        editor = delegate.createEditor(parent_widget, option, index)
        delegate.setEditorData(editor, index)
        assert editor.value() == 120.0

    def test_set_editor_data_empty(self, parent_widget, app):
        """Test editor handles empty BPM."""
        model = QStandardItemModel(1, 1)
        model.setItem(0, 0, QStandardItem(""))
        delegate = BPMEditDelegate()
        option = QStyleOptionViewItem()
        index = model.index(0, 0)
        editor = delegate.createEditor(parent_widget, option, index)
        delegate.setEditorData(editor, index)
        assert editor.value() == 0.0

    def test_set_model_data(self, parent_widget, model_with_data):
        """Test BPM editor commits value to model."""
        delegate = BPMEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 2)
        editor = delegate.createEditor(parent_widget, option, index)
        editor.setValue(128.5)
        delegate.setModelData(editor, model_with_data, index)
        assert model_with_data.data(index) == "128.5"

    def test_range_limits(self, parent_widget, model_with_data):
        """Test BPM editor has correct range."""
        delegate = BPMEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 2)
        editor = delegate.createEditor(parent_widget, option, index)
        assert editor.minimum() == 0.0
        assert editor.maximum() == 999.0


class TestKeyEditDelegate:
    """Tests for KeyEditDelegate."""

    def test_create_editor(self, parent_widget, model_with_data):
        """Test editor creation returns editable QComboBox."""
        delegate = KeyEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 3)
        editor = delegate.createEditor(parent_widget, option, index)
        assert editor is not None
        assert editor.isEditable()

    def test_standard_keys_populated(self, parent_widget, model_with_data):
        """Test combo box contains standard keys."""
        delegate = KeyEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 3)
        editor = delegate.createEditor(parent_widget, option, index)
        assert editor.count() == len(STANDARD_KEYS)

    def test_set_editor_data_known_key(self, parent_widget, model_with_data):
        """Test editor selects known key."""
        delegate = KeyEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 3)
        editor = delegate.createEditor(parent_widget, option, index)
        delegate.setEditorData(editor, index)
        assert editor.currentText() == "Am"

    def test_set_editor_data_custom_key(self, parent_widget, app):
        """Test editor handles custom key."""
        model = QStandardItemModel(1, 1)
        model.setItem(0, 0, QStandardItem("4A"))
        delegate = KeyEditDelegate()
        option = QStyleOptionViewItem()
        index = model.index(0, 0)
        editor = delegate.createEditor(parent_widget, option, index)
        delegate.setEditorData(editor, index)
        assert editor.currentText() == "4A"

    def test_set_model_data(self, parent_widget, model_with_data):
        """Test key editor commits value to model."""
        delegate = KeyEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 3)
        editor = delegate.createEditor(parent_widget, option, index)
        editor.setCurrentText("Cm")
        delegate.setModelData(editor, model_with_data, index)
        assert model_with_data.data(index) == "Cm"


class TestEnergyEditDelegate:
    """Tests for EnergyEditDelegate."""

    def test_create_editor(self, parent_widget, model_with_data):
        """Test editor creation returns QSpinBox."""
        delegate = EnergyEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 4)
        editor = delegate.createEditor(parent_widget, option, index)
        assert editor is not None
        assert hasattr(editor, "value")

    def test_set_editor_data(self, parent_widget, model_with_data):
        """Test editor is populated with energy value."""
        delegate = EnergyEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 4)
        editor = delegate.createEditor(parent_widget, option, index)
        delegate.setEditorData(editor, index)
        assert editor.value() == 7

    def test_set_editor_data_empty(self, parent_widget, app):
        """Test editor defaults to 5 for empty value."""
        model = QStandardItemModel(1, 1)
        model.setItem(0, 0, QStandardItem(""))
        delegate = EnergyEditDelegate()
        option = QStyleOptionViewItem()
        index = model.index(0, 0)
        editor = delegate.createEditor(parent_widget, option, index)
        delegate.setEditorData(editor, index)
        assert editor.value() == 5

    def test_set_model_data(self, parent_widget, model_with_data):
        """Test energy editor commits value to model."""
        delegate = EnergyEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 4)
        editor = delegate.createEditor(parent_widget, option, index)
        editor.setValue(9)
        delegate.setModelData(editor, model_with_data, index)
        assert model_with_data.data(index) == "9"

    def test_range_limits(self, parent_widget, model_with_data):
        """Test energy editor has correct range."""
        delegate = EnergyEditDelegate()
        option = QStyleOptionViewItem()
        index = model_with_data.index(0, 4)
        editor = delegate.createEditor(parent_widget, option, index)
        assert editor.minimum() == 1
        assert editor.maximum() == 10
