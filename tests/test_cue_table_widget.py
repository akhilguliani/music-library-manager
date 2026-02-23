"""Tests for CueTableWidget — editable cue point list."""

import pytest
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.widgets.cue_table_widget import CueTableWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestCueTableWidget:
    """Tests for CueTableWidget."""

    def test_populate_table(self, qapp):
        """set_cue_points populates the correct number of rows."""
        widget = CueTableWidget()
        cues = [
            {"pos": 10.5, "name": "Intro", "num": 1},
            {"pos": 62.0, "name": "Drop", "num": 2},
        ]
        widget.set_cue_points(cues)
        assert widget.table.rowCount() == 2

    def test_cell_values(self, qapp):
        """Table cells show correct cue number, name, and formatted position."""
        widget = CueTableWidget()
        cues = [{"pos": 10.5, "name": "Intro", "num": 1}]
        widget.set_cue_points(cues)

        assert widget.table.item(0, 0).text() == "1"
        assert widget.table.item(0, 1).text() == "Intro"
        assert widget.table.item(0, 2).text() == "0:10.500"

    def test_edit_name_emits_signal(self, qapp):
        """Editing the name cell emits cues_changed with updated name."""
        widget = CueTableWidget()
        cues = [{"pos": 5.0, "name": "Old", "num": 1}]
        widget.set_cue_points(cues)

        received = []
        widget.cues_changed.connect(lambda c: received.append(c))

        widget.table.item(0, 1).setText("New")
        QApplication.processEvents()

        assert len(received) == 1
        assert received[0][0]["name"] == "New"

    def test_edit_position_emits_signal(self, qapp):
        """Editing position cell emits cues_changed with updated pos."""
        widget = CueTableWidget()
        cues = [{"pos": 5.0, "name": "Cue 1", "num": 1}]
        widget.set_cue_points(cues)

        received = []
        widget.cues_changed.connect(lambda c: received.append(c))

        widget.table.item(0, 2).setText("1:30.000")
        QApplication.processEvents()

        assert len(received) == 1
        assert received[0][0]["pos"] == 90.0

    def test_delete_row_emits_signal(self, qapp):
        """Deleting a row emits cues_changed without the deleted cue."""
        widget = CueTableWidget()
        cues = [
            {"pos": 5.0, "name": "A", "num": 1},
            {"pos": 10.0, "name": "B", "num": 2},
        ]
        widget.set_cue_points(cues)

        received = []
        widget.cues_changed.connect(lambda c: received.append(c))

        widget._on_delete_by_num(1)  # delete cue with num=1 ("A")
        QApplication.processEvents()

        assert len(received) == 1
        assert len(received[0]) == 1
        assert received[0][0]["name"] == "B"

    def test_add_cue_emits_signal(self, qapp):
        """Adding a cue emits cues_changed with the new cue appended."""
        widget = CueTableWidget()
        widget.set_cue_points([])

        received = []
        widget.cues_changed.connect(lambda c: received.append(c))

        widget._on_add_clicked()
        QApplication.processEvents()

        assert len(received) == 1
        assert len(received[0]) == 1
        assert received[0][0]["num"] == 1
        assert received[0][0]["pos"] == 0.0

    def test_max_8_enforcement(self, qapp):
        """Add button should be disabled when 8 cues are present."""
        widget = CueTableWidget()
        cues = [{"pos": float(i), "name": f"Cue {i}", "num": i} for i in range(1, 9)]
        widget.set_cue_points(cues)

        assert not widget.add_btn.isEnabled()
        assert widget.table.rowCount() == 8

    def test_position_format(self, qapp):
        """Position formatting converts seconds to M:SS.mmm correctly."""
        assert CueTableWidget._format_position(0.0) == "0:00.000"
        assert CueTableWidget._format_position(10.5) == "0:10.500"
        assert CueTableWidget._format_position(62.123) == "1:02.123"
        assert CueTableWidget._format_position(125.0) == "2:05.000"

    def test_position_parse(self, qapp):
        """Position parsing handles M:SS.mmm and plain seconds."""
        assert CueTableWidget._parse_position("1:30.000") == 90.0
        assert CueTableWidget._parse_position("0:10.500") == 10.5
        assert CueTableWidget._parse_position("42.5") == 42.5
        assert CueTableWidget._parse_position("invalid") is None
        assert CueTableWidget._parse_position("-5.0") is None
        assert CueTableWidget._parse_position("-1:30.000") is None
        assert CueTableWidget._parse_position("1:-30.000") is None  # negative seconds component
