"""Database status panel with track list and statistics."""

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QGroupBox,
    QFormLayout,
    QComboBox,
    QHeaderView,
    QAbstractItemView,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QSplitter,
)
from PySide6.QtCore import Qt, Signal, Slot, QSortFilterProxyModel

from vdj_manager.config import LOCAL_VDJ_DB, MYNVME_VDJ_DB
from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song, DatabaseStats
from vdj_manager.ui.models.track_model import TrackTableModel
from vdj_manager.ui.workers.database_worker import DatabaseLoadWorker, DatabaseLoadResult


class DatabasePanel(QWidget):
    """Panel for viewing database status and browsing tracks.

    This panel provides:
    - Database selection (Local, MyNVMe, or custom)
    - Database statistics display
    - Track table with virtual scrolling
    - Search/filter functionality

    Signals:
        database_loaded: Emitted when a database is loaded (VDJDatabase)
        track_selected: Emitted when a track is selected (Song)
    """

    database_loaded = Signal(object)  # VDJDatabase
    track_selected = Signal(object)  # Song

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the database panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._database: VDJDatabase | None = None
        self._tracks: list[Song] = []
        self._load_worker: DatabaseLoadWorker | None = None

        self._setup_ui()

    @property
    def database(self) -> VDJDatabase | None:
        """Get the currently loaded database."""
        return self._database

    @property
    def tracks(self) -> list[Song]:
        """Get the currently loaded tracks."""
        return self._tracks

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)

        # Database selection
        selection_group = self._create_selection_group()
        layout.addWidget(selection_group)

        # Create splitter for stats and track table
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Statistics group
        stats_group = self._create_stats_group()
        splitter.addWidget(stats_group)

        # Track table group
        tracks_group = self._create_tracks_group()
        splitter.addWidget(tracks_group)

        # Set stretch factors (give more space to tracks)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter)

    def _create_selection_group(self) -> QGroupBox:
        """Create the database selection group box."""
        group = QGroupBox("Database")
        layout = QHBoxLayout(group)

        # Database dropdown
        layout.addWidget(QLabel("Source:"))
        self.db_combo = QComboBox()
        self.db_combo.addItem("Local", LOCAL_VDJ_DB)
        self.db_combo.addItem("MyNVMe", MYNVME_VDJ_DB)
        self.db_combo.addItem("Custom...", None)
        self.db_combo.currentIndexChanged.connect(self._on_db_selection_changed)
        layout.addWidget(self.db_combo)

        # Load button
        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self._on_load_clicked)
        layout.addWidget(self.load_btn)

        # Status label
        self.status_label = QLabel("Not loaded")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        return group

    def _create_stats_group(self) -> QGroupBox:
        """Create the statistics display group box."""
        group = QGroupBox("Statistics")
        layout = QFormLayout(group)

        # Create stat labels
        self.stats_labels = {}
        stat_items = [
            ("total", "Total Tracks:"),
            ("audio", "Audio Files:"),
            ("with_energy", "With Energy:"),
            ("with_cues", "With Cue Points:"),
            ("windows", "Windows Paths:"),
            ("netsearch", "Streaming:"),
        ]

        for key, label in stat_items:
            value_label = QLabel("-")
            self.stats_labels[key] = value_label
            layout.addRow(label, value_label)

        return group

    def _create_tracks_group(self) -> QGroupBox:
        """Create the track table group box."""
        group = QGroupBox("Tracks")
        layout = QVBoxLayout(group)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter tracks...")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input)

        self.result_count_label = QLabel("")
        search_layout.addWidget(self.result_count_label)

        layout.addLayout(search_layout)

        # Track table
        self.track_model = TrackTableModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.track_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)  # Search all columns

        self.track_table = QTableView()
        self.track_table.setModel(self.proxy_model)
        self.track_table.setAlternatingRowColors(True)
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.track_table.setSortingEnabled(True)
        self.track_table.verticalHeader().setVisible(False)

        # Set column resize modes
        header = self.track_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Title
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Artist
        header.setDefaultSectionSize(100)

        # Connect selection
        self.track_table.selectionModel().currentRowChanged.connect(
            self._on_track_selected
        )

        layout.addWidget(self.track_table)

        return group

    def _on_db_selection_changed(self, index: int) -> None:
        """Handle database selection change."""
        if self.db_combo.currentData() is None:
            # Custom selection - show file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select VDJ Database",
                str(Path.home()),
                "XML Files (*.xml);;All Files (*)",
            )

            if file_path:
                # Add custom path to combo
                path = Path(file_path)
                self.db_combo.insertItem(
                    self.db_combo.count() - 1,
                    path.name,
                    path,
                )
                self.db_combo.setCurrentIndex(self.db_combo.count() - 2)
            else:
                # Cancelled - revert to first item
                self.db_combo.setCurrentIndex(0)

    def _on_load_clicked(self) -> None:
        """Handle load button click."""
        db_path = self.db_combo.currentData()
        if db_path is None:
            return

        self.load_database(db_path)

    def load_database(self, path: Path) -> None:
        """Load a database from the given path.

        Args:
            path: Path to database.xml file.
        """
        if self._load_worker is not None and self._load_worker.isRunning():
            QMessageBox.warning(
                self,
                "Load in Progress",
                "A database is already being loaded. Please wait.",
            )
            return

        # Update UI
        self.load_btn.setEnabled(False)
        self.status_label.setText("Loading...")
        self.status_label.setStyleSheet("color: blue;")

        # Start worker
        self._load_worker = DatabaseLoadWorker(path)
        self._load_worker.progress.connect(self._on_load_progress)
        self._load_worker.finished_work.connect(self._on_load_finished)
        self._load_worker.error.connect(self._on_load_error)
        self._load_worker.start()

    @Slot(str)
    def _on_load_progress(self, message: str) -> None:
        """Handle loading progress update."""
        self.status_label.setText(message)

    @Slot(object)
    def _on_load_finished(self, result: DatabaseLoadResult) -> None:
        """Handle loading completion."""
        self.load_btn.setEnabled(True)

        if result.success:
            self._database = result.database
            self._tracks = result.tracks

            # Update stats
            self._update_stats(result.stats)

            # Update track table
            self.track_model.set_tracks(result.tracks)
            self._update_result_count()

            self.status_label.setText(f"Loaded {len(result.tracks)} tracks")
            self.status_label.setStyleSheet("color: green;")

            # Emit signal
            self.database_loaded.emit(self._database)
        else:
            self.status_label.setText(f"Error: {result.error}")
            self.status_label.setStyleSheet("color: red;")

    @Slot(str)
    def _on_load_error(self, error: str) -> None:
        """Handle loading error."""
        self.load_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error}")
        self.status_label.setStyleSheet("color: red;")

    def _update_stats(self, stats: DatabaseStats | None) -> None:
        """Update the statistics display.

        Args:
            stats: Database statistics.
        """
        if stats is None:
            for label in self.stats_labels.values():
                label.setText("-")
            return

        self.stats_labels["total"].setText(str(stats.total_songs))
        self.stats_labels["audio"].setText(str(stats.audio_files))
        self.stats_labels["with_energy"].setText(str(stats.with_energy))
        self.stats_labels["with_cues"].setText(str(stats.with_cue_points))
        self.stats_labels["windows"].setText(str(stats.windows_paths))
        self.stats_labels["netsearch"].setText(str(stats.netsearch))

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        """Handle search input change."""
        self.proxy_model.setFilterFixedString(text)
        self._update_result_count()

    def _update_result_count(self) -> None:
        """Update the result count label."""
        filtered = self.proxy_model.rowCount()
        total = self.track_model.rowCount()

        if filtered == total:
            self.result_count_label.setText(f"{total} tracks")
        else:
            self.result_count_label.setText(f"{filtered} / {total} tracks")

    @Slot()
    def _on_track_selected(self) -> None:
        """Handle track selection."""
        indexes = self.track_table.selectionModel().selectedRows()
        if not indexes:
            return

        # Get the source index from the proxy model
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)

        track = self.track_model.get_track(source_index.row())
        if track:
            self.track_selected.emit(track)

    def get_selected_track(self) -> Song | None:
        """Get the currently selected track.

        Returns:
            Selected Song or None.
        """
        indexes = self.track_table.selectionModel().selectedRows()
        if not indexes:
            return None

        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        return self.track_model.get_track(source_index.row())

    def get_filtered_tracks(self) -> list[Song]:
        """Get all tracks that match the current filter.

        Returns:
            List of filtered Song objects.
        """
        tracks = []
        for row in range(self.proxy_model.rowCount()):
            source_index = self.proxy_model.mapToSource(
                self.proxy_model.index(row, 0)
            )
            track = self.track_model.get_track(source_index.row())
            if track:
                tracks.append(track)
        return tracks
