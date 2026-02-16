"""Editable cue point table widget for the Player tab."""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal


MAX_CUES = 8


class CueTableWidget(QWidget):
    """Table-based cue point editor.

    Displays cue points as editable rows with columns for
    cue number, name, position (M:SS.ms), and a delete button.

    Signals:
        cues_changed(list): Emitted when any cue is added, edited, or deleted.
            Payload is a list of dicts: [{"pos": float, "name": str, "num": int}, ...]
    """

    cues_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cues: list[dict] = []
        self._updating = False  # guard against signal loops
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Name", "Position", ""])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 30)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 30)

        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("+ Add Cue")
        self.add_btn.clicked.connect(self._on_add_clicked)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def set_cue_points(self, cues: list[dict]) -> None:
        """Populate the table from a list of cue dicts."""
        self._cues = [dict(c) for c in cues]
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Rebuild table rows from self._cues."""
        self._updating = True
        self.table.setRowCount(0)

        for cue in self._cues:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Column 0: cue number (read-only)
            num_item = QTableWidgetItem(str(cue.get("num", row + 1)))
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, num_item)

            # Column 1: name (editable)
            self.table.setItem(row, 1, QTableWidgetItem(cue.get("name", "")))

            # Column 2: position (editable, displayed as M:SS.mmm)
            pos_item = QTableWidgetItem(self._format_position(cue.get("pos", 0.0)))
            self.table.setItem(row, 2, pos_item)

            # Column 3: delete button
            del_btn = QPushButton("\u00d7")
            del_btn.setFixedSize(24, 24)
            del_btn.setStyleSheet("font-weight: bold; color: red; border: none;")
            del_btn.clicked.connect(lambda checked=False, r=row: self._on_delete_clicked(r))
            self.table.setCellWidget(row, 3, del_btn)

        self.add_btn.setEnabled(len(self._cues) < MAX_CUES)
        self._updating = False

    def _on_cell_changed(self, row: int, col: int) -> None:
        """Handle inline edits to name or position cells."""
        if self._updating or row >= len(self._cues):
            return

        if col == 1:  # Name
            item = self.table.item(row, 1)
            if item:
                self._cues[row]["name"] = item.text()
                self._emit_cues_changed()

        elif col == 2:  # Position
            item = self.table.item(row, 2)
            if item:
                parsed = self._parse_position(item.text())
                if parsed is not None:
                    self._cues[row]["pos"] = parsed
                    self._emit_cues_changed()
                else:
                    # Revert to previous value on invalid input
                    self._updating = True
                    item.setText(self._format_position(self._cues[row]["pos"]))
                    self._updating = False

    def _on_delete_clicked(self, row: int) -> None:
        """Remove a cue point row."""
        if row < len(self._cues):
            del self._cues[row]
            self._refresh_table()
            self._emit_cues_changed()

    def _on_add_clicked(self) -> None:
        """Add a new cue point with next available number."""
        if len(self._cues) >= MAX_CUES:
            return
        num = self._next_cue_number()
        self._cues.append({"pos": 0.0, "name": f"Cue {num}", "num": num})
        self._refresh_table()
        self._emit_cues_changed()

    def _next_cue_number(self) -> int:
        """Find the lowest available cue number (1-8)."""
        used = {c.get("num") for c in self._cues if c.get("num") is not None}
        for n in range(1, 9):
            if n not in used:
                return n
        return len(self._cues) + 1

    def _emit_cues_changed(self) -> None:
        """Emit cues_changed with a copy of the current cue list."""
        self.cues_changed.emit([dict(c) for c in self._cues])

    @staticmethod
    def _format_position(seconds: float) -> str:
        """Format seconds as M:SS.mmm."""
        total_ms = int(round(seconds * 1000))
        minutes = total_ms // 60000
        remainder_ms = total_ms % 60000
        secs = remainder_ms // 1000
        ms = remainder_ms % 1000
        return f"{minutes}:{secs:02d}.{ms:03d}"

    @staticmethod
    def _parse_position(text: str) -> float | None:
        """Parse M:SS.mmm or plain seconds into float seconds. Returns None if invalid or negative."""
        text = text.strip()
        try:
            if ":" in text:
                parts = text.split(":", 1)
                minutes = int(parts[0])
                sec_part = float(parts[1])
                result = minutes * 60.0 + sec_part
            else:
                result = float(text)
            return result if result >= 0.0 else None
        except (ValueError, IndexError):
            return None
