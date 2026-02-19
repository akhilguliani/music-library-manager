"""Qt table model for displaying tracks with virtual scrolling support."""

import json
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QMimeData, QModelIndex, Qt, Signal

from vdj_manager.core.models import Song

TRACK_MIME_TYPE = "application/x-vdj-tracks"

# Custom role for album art delegate: returns file_path for art lookup
ALBUM_ART_ROLE = Qt.ItemDataRole.UserRole + 1


class TrackTableModel(QAbstractTableModel):
    """Table model for displaying track data with efficient virtual scrolling.

    This model provides a view into a list of Song objects, displaying
    key metadata in columns. It supports large track lists (18k+) through
    Qt's built-in virtual scrolling.

    Columns:
        0: Art (album art thumbnail)
        1: Title (or display name)
        2: Artist
        3: BPM
        4: Key
        5: Energy
        6: Duration
        7: Genre
    """

    # Signal emitted when a tag edit is committed: (file_path, field_name, new_value)
    tag_edit_requested = Signal(str, str, str)

    COLUMNS = [
        ("", "art"),
        ("Title", "title"),
        ("Artist", "artist"),
        ("BPM", "bpm"),
        ("Key", "key"),
        ("Energy", "energy"),
        ("Duration", "duration"),
        ("Genre", "genre"),
        ("Mood", "mood"),
    ]

    # Columns that support inline editing (by index)
    EDITABLE_COLUMNS = {1, 2, 3, 4, 5, 7, 8}  # Title, Artist, BPM, Key, Energy, Genre, Mood

    def __init__(self, parent: Any = None) -> None:
        """Initialize the track model.

        Args:
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._tracks: list[Song] = []

    @property
    def tracks(self) -> list[Song]:
        """Get the current list of tracks."""
        return self._tracks

    def set_tracks(self, tracks: list[Song]) -> None:
        """Set the track list, updating the model.

        Args:
            tracks: List of Song objects to display.
        """
        self.beginResetModel()
        self._tracks = list(tracks)
        self.endResetModel()

    def clear(self) -> None:
        """Clear all tracks from the model."""
        self.beginResetModel()
        self._tracks = []
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        """Return the number of rows (tracks).

        Args:
            parent: Parent index (unused for table models).

        Returns:
            Number of tracks.
        """
        if parent.isValid():
            return 0
        return len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        """Return the number of columns.

        Args:
            parent: Parent index (unused for table models).

        Returns:
            Number of columns.
        """
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        """Return data for a given index and role.

        Args:
            index: Model index.
            role: Data role.

        Returns:
            Data for the cell, or None.
        """
        if not index.isValid():
            return None

        if index.row() >= len(self._tracks):
            return None

        track = self._tracks[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:  # Art column has no text
                return None
            return self._get_display_value(track, col)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            # Right-align numeric columns
            if col in (3, 5, 6):  # BPM, Energy, Duration
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        elif role == Qt.ItemDataRole.ToolTipRole:
            return track.file_path
        elif role == Qt.ItemDataRole.UserRole:
            # Return the Song object itself
            return track
        elif role == ALBUM_ART_ROLE:
            # Return file_path for album art delegate
            return track.file_path

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # type: ignore[override]
        """Return item flags, adding Editable and DragEnabled for supported columns."""
        base_flags = super().flags(index)
        if index.isValid():
            base_flags |= Qt.ItemFlag.ItemIsDragEnabled
            if index.column() in self.EDITABLE_COLUMNS:
                base_flags |= Qt.ItemFlag.ItemIsEditable
        return base_flags

    def mimeTypes(self) -> list[str]:
        """Return supported MIME types for drag operations."""
        return [TRACK_MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:  # type: ignore[override]
        """Encode dragged rows as JSON list of file paths."""
        rows = sorted({idx.row() for idx in indexes if idx.isValid()})
        paths = [self._tracks[r].file_path for r in rows if r < len(self._tracks)]
        data = QMimeData()
        data.setData(TRACK_MIME_TYPE, json.dumps(paths).encode())
        return data

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:  # type: ignore[override]
        """Handle edit commits by emitting tag_edit_requested signal."""
        if role != Qt.ItemDataRole.EditRole:
            return False
        if not index.isValid() or index.column() not in self.EDITABLE_COLUMNS:
            return False

        track = self._tracks[index.row()]
        field_name = self.COLUMNS[index.column()][1]
        self.tag_edit_requested.emit(track.file_path, field_name, str(value))
        return True

    def _get_display_value(self, track: Song, column: int) -> str:
        """Get the display string for a track column.

        Args:
            track: Song object.
            column: Column index.

        Returns:
            Display string for the cell.
        """
        if column == 1:  # Title
            if track.tags and track.tags.title:
                return track.tags.title
            return track.display_name
        elif column == 2:  # Artist
            if track.tags and track.tags.author:
                return track.tags.author
            return ""
        elif column == 3:  # BPM
            # Prefer Tags.bpm (user-set, actual BPM), fall back to Scan.actual_bpm
            if track.tags and track.tags.bpm is not None:
                return f"{track.tags.bpm:.1f}"
            bpm = track.actual_bpm
            if bpm is not None:
                return f"{bpm:.1f}"
            return ""
        elif column == 4:  # Key
            # Prefer Tags.key (user-set), fall back to Scan.key
            if track.tags and track.tags.key:
                return track.tags.key
            if track.scan and track.scan.key:
                return track.scan.key
            return ""
        elif column == 5:  # Energy
            energy = track.energy
            if energy is not None:
                return str(energy)
            return ""
        elif column == 6:  # Duration
            if track.infos and track.infos.song_length:
                return self._format_duration(track.infos.song_length)
            return ""
        elif column == 7:  # Genre
            if track.tags and track.tags.genre:
                return track.tags.genre
            return ""
        elif column == 8:  # Mood
            if track.tags and track.tags.user2:
                return track.tags.user2
            return ""

        return ""

    def _format_duration(self, seconds: float) -> str:
        """Format seconds as MM:SS.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted duration string.
        """
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return header data.

        Args:
            section: Row or column number.
            orientation: Horizontal or vertical.
            role: Data role.

        Returns:
            Header data.
        """
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        else:
            return str(section + 1)

        return None

    def get_track(self, row: int) -> Song | None:
        """Get a track by row index.

        Args:
            row: Row index.

        Returns:
            Song object or None if out of range.
        """
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None

    def get_track_at_index(self, index: QModelIndex) -> Song | None:
        """Get a track from a model index.

        Args:
            index: Model index.

        Returns:
            Song object or None if invalid.
        """
        if not index.isValid():
            return None
        return self.get_track(index.row())

    def find_track_row(self, file_path: str) -> int:
        """Find the row index of a track by file path.

        Args:
            file_path: File path to search for.

        Returns:
            Row index, or -1 if not found.
        """
        for i, track in enumerate(self._tracks):
            if track.file_path == file_path:
                return i
        return -1

    def notify_art_changed(self, file_path: str) -> None:
        """Notify that album art for a track has been loaded.

        Emits dataChanged for the art column of the matching row.
        """
        row = self.find_track_row(file_path)
        if row >= 0:
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [ALBUM_ART_ROLE])
