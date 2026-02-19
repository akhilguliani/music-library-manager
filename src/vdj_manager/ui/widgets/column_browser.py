"""Column browser for Genre > Artist > Album cascading filter."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QSplitter, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from vdj_manager.core.models import Song


class ColumnBrowser(QWidget):
    """Collapsible side panel with 3 stacked filter lists (Genre/Artist/Album).

    Each item shows count: "House (342)"
    "All (N)" as first item in each list.
    Cascade: selecting genre -> filters artists -> filters albums.

    Signals:
        filter_changed(list, list, list): Emitted when any filter changes.
            Args are (selected_genres, selected_artists, selected_albums).
    """

    filter_changed = Signal(list, list, list)  # genres, artists, albums

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tracks: list[Song] = []
        # Pre-built indexes: genre -> [tracks], (genre, artist) -> [tracks]
        self._genre_index: dict[str, list[Song]] = defaultdict(list)
        self._genre_artist_index: dict[tuple[str, str], list[Song]] = defaultdict(list)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self._genre_list = QListWidget()
        self._genre_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._genre_list.itemSelectionChanged.connect(self._on_genre_changed)
        splitter.addWidget(self._genre_list)

        self._artist_list = QListWidget()
        self._artist_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._artist_list.itemSelectionChanged.connect(self._on_artist_changed)
        splitter.addWidget(self._artist_list)

        self._album_list = QListWidget()
        self._album_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._album_list.itemSelectionChanged.connect(self._on_album_changed)
        splitter.addWidget(self._album_list)

        layout.addWidget(splitter)

    def set_tracks(self, tracks: list[Song]) -> None:
        """Set the track list and rebuild all browser lists."""
        self._tracks = list(tracks)
        self._build_indexes()
        self._rebuild_genres()

    def _build_indexes(self) -> None:
        """Pre-build genre and genre+artist indexes for O(1) lookups."""
        self._genre_index = defaultdict(list)
        self._genre_artist_index = defaultdict(list)
        for t in self._tracks:
            genre = t.tags.genre if t.tags and t.tags.genre else ""
            artist = t.tags.author if t.tags and t.tags.author else ""
            self._genre_index[genre].append(t)
            self._genre_artist_index[(genre, artist)].append(t)

    def _rebuild_genres(self) -> None:
        """Rebuild genre list from all tracks."""
        self._genre_list.blockSignals(True)
        self._genre_list.clear()

        total = len(self._tracks)
        all_item = QListWidgetItem(f"All ({total})")
        all_item.setData(Qt.ItemDataRole.UserRole, "__all__")
        self._genre_list.addItem(all_item)
        all_item.setSelected(True)

        for genre in sorted(self._genre_index.keys()):
            label = genre if genre else "(No Genre)"
            item = QListWidgetItem(f"{label} ({len(self._genre_index[genre])})")
            item.setData(Qt.ItemDataRole.UserRole, genre)
            self._genre_list.addItem(item)

        self._genre_list.blockSignals(False)
        self._rebuild_artists()

    def _get_selected_values(self, list_widget: QListWidget) -> list[str]:
        """Get selected values from a list widget, handling 'All' selection."""
        items = list_widget.selectedItems()
        if not items:
            return []
        values = [item.data(Qt.ItemDataRole.UserRole) for item in items]
        if "__all__" in values:
            return []  # Empty means "all"
        return values

    def _filtered_by_genre(self) -> list[Song]:
        """Get tracks filtered by selected genres using index."""
        genres = self._get_selected_values(self._genre_list)
        if not genres:
            return self._tracks
        result: list[Song] = []
        for g in genres:
            result.extend(self._genre_index.get(g, []))
        return result

    def _filtered_by_artist(self) -> list[Song]:
        """Get tracks filtered by genre AND artist using index."""
        genres = self._get_selected_values(self._genre_list)
        artists = self._get_selected_values(self._artist_list)

        if not genres and not artists:
            return self._tracks

        # Use the composite index for efficient filtering
        if genres and artists:
            result: list[Song] = []
            for g in genres:
                for a in artists:
                    result.extend(self._genre_artist_index.get((g, a), []))
            return result
        elif genres:
            # Only genre filter
            result = []
            for g in genres:
                result.extend(self._genre_index.get(g, []))
            return result
        else:
            # Only artist filter — iterate genre_artist_index
            result = []
            for (g, a), tracks in self._genre_artist_index.items():
                if a in artists:
                    result.extend(tracks)
            return result

    def _rebuild_artists(self) -> None:
        """Rebuild artist list based on selected genres."""
        self._artist_list.blockSignals(True)
        self._artist_list.clear()

        tracks = self._filtered_by_genre()
        artists: dict[str, int] = {}
        for t in tracks:
            a = t.tags.author if t.tags and t.tags.author else ""
            artists[a] = artists.get(a, 0) + 1

        all_item = QListWidgetItem(f"All ({len(tracks)})")
        all_item.setData(Qt.ItemDataRole.UserRole, "__all__")
        self._artist_list.addItem(all_item)
        all_item.setSelected(True)

        for artist in sorted(artists.keys()):
            label = artist if artist else "(No Artist)"
            item = QListWidgetItem(f"{label} ({artists[artist]})")
            item.setData(Qt.ItemDataRole.UserRole, artist)
            self._artist_list.addItem(item)

        self._artist_list.blockSignals(False)
        self._rebuild_albums()

    def _rebuild_albums(self) -> None:
        """Rebuild album list based on selected genres and artists."""
        self._album_list.blockSignals(True)
        self._album_list.clear()

        tracks = self._filtered_by_artist()
        albums: dict[str, int] = {}
        for t in tracks:
            a = t.tags.album if t.tags and t.tags.album else ""
            albums[a] = albums.get(a, 0) + 1

        all_item = QListWidgetItem(f"All ({len(tracks)})")
        all_item.setData(Qt.ItemDataRole.UserRole, "__all__")
        self._album_list.addItem(all_item)
        all_item.setSelected(True)

        for album in sorted(albums.keys()):
            label = album if album else "(No Album)"
            item = QListWidgetItem(f"{label} ({albums[album]})")
            item.setData(Qt.ItemDataRole.UserRole, album)
            self._album_list.addItem(item)

        self._album_list.blockSignals(False)
        self._emit_filter_changed()

    def _on_genre_changed(self) -> None:
        self._rebuild_artists()

    def _on_artist_changed(self) -> None:
        self._rebuild_albums()

    def _on_album_changed(self) -> None:
        self._emit_filter_changed()

    def _emit_filter_changed(self) -> None:
        genres = self._get_selected_values(self._genre_list)
        artists = self._get_selected_values(self._artist_list)
        albums = self._get_selected_values(self._album_list)
        self.filter_changed.emit(genres, artists, albums)
