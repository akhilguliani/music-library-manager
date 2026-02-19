"""Export panel for Serato format conversion."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Playlist, Song
from vdj_manager.ui.widgets.results_table import ConfigurableResultsTable
from vdj_manager.ui.workers.export_workers import CrateExportWorker, SeratoExportWorker


class ExportPanel(QWidget):
    """Panel for exporting library to Serato format.

    Provides:
    - Export all tracks or selected playlist
    - Cues-only option
    - Playlist/crate browser
    - Export results display

    Signals:
        export_completed: Emitted when export finishes.
    """

    export_completed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._database: VDJDatabase | None = None
        self._tracks: list[Song] = []
        self._playlists: list[Playlist] = []
        self._export_worker: SeratoExportWorker | None = None
        self._crate_worker: CrateExportWorker | None = None

        self._setup_ui()

    def set_database(self, database: VDJDatabase | None, tracks: list[Song] | None = None) -> None:
        """Set the database for export.

        Args:
            database: VDJDatabase instance.
            tracks: Optional list of tracks.
        """
        self._database = database
        if tracks is not None:
            self._tracks = tracks
        elif database is not None:
            self._tracks = list(database.iter_songs())
        else:
            self._tracks = []

        if database is not None:
            self._playlists = database.playlists
        else:
            self._playlists = []

        has_db = database is not None and len(self._tracks) > 0
        self.export_all_btn.setEnabled(has_db)
        self.export_playlist_btn.setEnabled(False)

        self._update_info()
        self._populate_playlist_list()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)

        # Create splitter for options and results
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Options section
        options_widget = QWidget()
        options_layout = QVBoxLayout(options_widget)

        # Info
        info_group = QGroupBox("Serato Export")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(
            QLabel(
                "Export your VirtualDJ library to Serato format.\n"
                "Writes BPM, key, and cue points to audio file tags.\n"
                "Requires: mutagen"
            )
        )
        self.info_label = QLabel("No database loaded")
        info_layout.addWidget(self.info_label)
        options_layout.addWidget(info_group)

        # Options
        options_row = QHBoxLayout()

        self.cues_only_check = QCheckBox("Cues only")
        self.cues_only_check.setToolTip("Only export cue points and beatgrid, skip metadata")
        options_row.addWidget(self.cues_only_check)

        options_row.addStretch()
        options_layout.addLayout(options_row)

        # Controls
        controls_layout = QHBoxLayout()

        self.export_all_btn = QPushButton("Export All Tracks")
        self.export_all_btn.setEnabled(False)
        self.export_all_btn.setToolTip("Export all audio tracks to Serato format")
        self.export_all_btn.clicked.connect(self._on_export_all_clicked)
        controls_layout.addWidget(self.export_all_btn)

        self.export_playlist_btn = QPushButton("Export Selected Playlist")
        self.export_playlist_btn.setEnabled(False)
        self.export_playlist_btn.setToolTip("Export selected playlist as Serato crate")
        self.export_playlist_btn.clicked.connect(self._on_export_playlist_clicked)
        controls_layout.addWidget(self.export_playlist_btn)

        controls_layout.addStretch()

        self.export_status = QLabel("")
        controls_layout.addWidget(self.export_status)

        options_layout.addLayout(controls_layout)

        # Playlist browser
        playlist_group = QGroupBox("Playlists")
        playlist_layout = QVBoxLayout(playlist_group)
        self.playlist_list = QListWidget()
        self.playlist_list.currentItemChanged.connect(self._on_playlist_selected)
        playlist_layout.addWidget(self.playlist_list)
        options_layout.addWidget(playlist_group)

        splitter.addWidget(options_widget)

        # Results section
        results_group = QGroupBox("Export Results")
        results_layout = QVBoxLayout(results_group)
        self.export_results = ConfigurableResultsTable(
            [
                {"name": "Track", "key": "file_path", "width": 400},
                {"name": "Status", "key": "status", "width": 150},
            ]
        )
        results_layout.addWidget(self.export_results)
        splitter.addWidget(results_group)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def _update_info(self) -> None:
        """Update info label."""
        if not self._tracks:
            self.info_label.setText("No database loaded")
            return

        audio_count = sum(
            1
            for t in self._tracks
            if not t.is_netsearch
            and not t.is_windows_path
            and t.extension
            in {".mp3", ".m4a", ".aac", ".flac", ".wav", ".aiff", ".aif", ".ogg", ".opus"}
        )
        playlist_count = len(self._playlists)
        self.info_label.setText(f"{audio_count} audio tracks, {playlist_count} playlists")

    def _populate_playlist_list(self) -> None:
        """Populate the playlist browser."""
        self.playlist_list.clear()
        for pl in self._playlists:
            item = QListWidgetItem(f"{pl.name} ({len(pl.file_paths)} tracks)")
            item.setData(Qt.ItemDataRole.UserRole, pl)
            self.playlist_list.addItem(item)

    def _on_playlist_selected(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        """Handle playlist selection."""
        self.export_playlist_btn.setEnabled(current is not None and self._database is not None)

    def _get_exportable_tracks(self) -> list[Song]:
        """Get tracks that can be exported."""
        audio_extensions = {
            ".mp3",
            ".m4a",
            ".aac",
            ".flac",
            ".wav",
            ".aiff",
            ".aif",
            ".ogg",
            ".opus",
        }
        return [
            t
            for t in self._tracks
            if not t.is_netsearch
            and not t.is_windows_path
            and t.extension in audio_extensions
            and Path(t.file_path).exists()
        ]

    def is_running(self) -> bool:
        """Check if an export is currently running."""
        for worker in (self._export_worker, self._crate_worker):
            if worker is not None and worker.isRunning():
                return True
        return False

    def _on_export_all_clicked(self) -> None:
        """Handle export all button click."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An export is already in progress.")
            return

        tracks = self._get_exportable_tracks()
        if not tracks:
            QMessageBox.information(self, "No Tracks", "No exportable tracks found.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Export",
            f"Export {len(tracks)} tracks to Serato format?\n" "This will modify audio file tags.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.export_all_btn.setEnabled(False)
        self.export_playlist_btn.setEnabled(False)
        self.export_status.setText("Exporting...")
        self.export_results.clear()

        self._export_worker = SeratoExportWorker(tracks, cues_only=self.cues_only_check.isChecked())
        self._export_worker.finished_work.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

    def _on_export_playlist_clicked(self) -> None:
        """Handle export playlist button click."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An export is already in progress.")
            return

        current = self.playlist_list.currentItem()
        if current is None:
            return

        playlist = current.data(Qt.ItemDataRole.UserRole)
        if not playlist or not playlist.file_paths:
            QMessageBox.information(self, "Empty Playlist", "Selected playlist has no tracks.")
            return

        self.export_all_btn.setEnabled(False)
        self.export_playlist_btn.setEnabled(False)
        self.export_status.setText(f"Creating crate '{playlist.name}'...")

        self._crate_worker = CrateExportWorker(playlist.name, playlist.file_paths)
        self._crate_worker.finished_work.connect(self._on_crate_finished)
        self._crate_worker.error.connect(self._on_export_error)
        self._crate_worker.start()

    @Slot(object)
    def _on_export_finished(self, result: dict) -> None:
        """Handle export completion."""
        self.export_all_btn.setEnabled(True)
        self.export_playlist_btn.setEnabled(self.playlist_list.currentItem() is not None)

        exported = result["exported"]
        failed = result["failed"]
        self.export_status.setText(f"Done: {exported} exported, {failed} failed")

        for r in result["results"]:
            self.export_results.add_result(r)

        self.export_completed.emit()

    @Slot(object)
    def _on_crate_finished(self, result: dict) -> None:
        """Handle crate export completion."""
        self.export_all_btn.setEnabled(True)
        self.export_playlist_btn.setEnabled(self.playlist_list.currentItem() is not None)

        self.export_status.setText(
            f"Created crate '{result['crate_name']}' with {result['track_count']} tracks"
        )
        self.export_results.add_result(
            {
                "file_path": result["crate_path"],
                "status": f"crate created ({result['track_count']} tracks)",
            }
        )
        self.export_completed.emit()

    @Slot(str)
    def _on_export_error(self, error: str) -> None:
        """Handle export error."""
        self.export_all_btn.setEnabled(True)
        self.export_playlist_btn.setEnabled(self.playlist_list.currentItem() is not None)
        self.export_status.setText(f"Error: {error}")
