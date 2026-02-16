"""Database status panel with track list and statistics."""

from datetime import datetime
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
    QListWidget,
    QMenu,
    QSpinBox,
    QSplitter,
)
from PySide6.QtCore import Qt, Signal, Slot, QSortFilterProxyModel

from vdj_manager.config import LOCAL_VDJ_DB, MYNVME_VDJ_DB
from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song, DatabaseStats
from vdj_manager.ui.models.track_model import TrackTableModel
from vdj_manager.ui.workers.database_worker import (
    DatabaseLoadWorker,
    DatabaseLoadResult,
    BackupWorker,
    ValidateWorker,
    CleanWorker,
)


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
        track_double_clicked: Emitted when a track is double-clicked (Song)
    """

    database_loaded = Signal(object)  # VDJDatabase
    track_selected = Signal(object)  # Song
    track_double_clicked = Signal(object)  # Song
    play_next_requested = Signal(object)  # list[Song]
    add_to_queue_requested = Signal(object)  # list[Song]

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the database panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._database: VDJDatabase | None = None
        self._tracks: list[Song] = []
        self._load_worker: DatabaseLoadWorker | None = None
        self._backup_worker: BackupWorker | None = None
        self._validate_worker: ValidateWorker | None = None
        self._clean_worker: CleanWorker | None = None
        self._editing_track: Song | None = None

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

        # Database selection + actions (merged header)
        selection_group = self._create_selection_group()
        layout.addWidget(selection_group)

        # Compact stats summary
        self.stats_summary_label = QLabel("No database loaded")
        self.stats_summary_label.setStyleSheet("color: gray; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(self.stats_summary_label)

        # Create splitter for track table, tag editor, and log
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Track table group
        tracks_group = self._create_tracks_group()
        splitter.addWidget(tracks_group)

        # Tag editing group (hidden until a track is selected)
        tag_group = self._create_tag_edit_group()
        self._tag_group = tag_group
        tag_group.setVisible(False)
        splitter.addWidget(tag_group)

        # Operation log
        log_group = QGroupBox("Operation Log")
        log_layout = QVBoxLayout(log_group)
        self.operation_log = QListWidget()
        self.operation_log.setMaximumHeight(150)
        log_layout.addWidget(self.operation_log)
        splitter.addWidget(log_group)

        # Set stretch factors (give most space to tracks)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)

        layout.addWidget(splitter)

    def _create_selection_group(self) -> QGroupBox:
        """Create the database selection and actions group box."""
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

        layout.addSpacing(16)

        # Action buttons
        self.backup_btn = QPushButton("Backup")
        self.backup_btn.setEnabled(False)
        self.backup_btn.setToolTip("Create a timestamped backup of the database")
        self.backup_btn.clicked.connect(self._on_backup_clicked)
        layout.addWidget(self.backup_btn)

        self.validate_btn = QPushButton("Validate")
        self.validate_btn.setEnabled(False)
        self.validate_btn.setToolTip("Check file existence and validate entries")
        self.validate_btn.clicked.connect(self._on_validate_clicked)
        layout.addWidget(self.validate_btn)

        self.clean_btn = QPushButton("Clean")
        self.clean_btn.setEnabled(False)
        self.clean_btn.setToolTip("Remove invalid entries from database")
        self.clean_btn.clicked.connect(self._on_clean_clicked)
        layout.addWidget(self.clean_btn)

        layout.addStretch()

        # Status label (right-aligned)
        self.status_label = QLabel("Not loaded")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

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
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.track_table.setSortingEnabled(True)
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_table.customContextMenuRequested.connect(self._on_track_context_menu)

        # Set column resize modes
        header = self.track_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Title
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Artist
        header.setDefaultSectionSize(100)

        # Connect selection
        self.track_table.selectionModel().currentRowChanged.connect(
            self._on_track_selected
        )
        self.track_table.doubleClicked.connect(self._on_track_double_clicked)

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
            self._log_operation(f"Loaded database with {len(result.tracks)} tracks")

            # Enable action buttons
            self.backup_btn.setEnabled(True)
            self.validate_btn.setEnabled(True)
            self.clean_btn.setEnabled(True)

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
            self.stats_summary_label.setText("No database loaded")
            self.stats_summary_label.setStyleSheet(
                "color: gray; font-size: 11px; padding: 2px 4px;"
            )
            return

        parts = [
            f"{stats.total_songs:,} tracks",
            f"{stats.audio_files:,} audio",
            f"{stats.with_energy:,} energy",
            f"{stats.with_cue_points:,} cues",
        ]
        if stats.windows_paths > 0:
            parts.append(f"{stats.windows_paths:,} Windows")
        if stats.netsearch > 0:
            parts.append(f"{stats.netsearch:,} streaming")

        self.stats_summary_label.setText("  |  ".join(parts))
        self.stats_summary_label.setStyleSheet(
            "color: #666; font-size: 11px; padding: 2px 4px;"
        )

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
            self._populate_tag_fields(track)
            self.track_selected.emit(track)

    @Slot()
    def _on_track_double_clicked(self, index) -> None:
        """Handle track double-click for playback."""
        source_index = self.proxy_model.mapToSource(index)
        track = self.track_model.get_track(source_index.row())
        if track:
            self.track_double_clicked.emit(track)

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

    def get_selected_tracks(self) -> list[Song]:
        """Get all currently selected tracks in visual (top-to-bottom) order.

        Returns:
            List of selected Song objects sorted by visual row position.
        """
        rows = sorted(self.track_table.selectionModel().selectedRows(), key=lambda idx: idx.row())
        tracks = []
        for proxy_index in rows:
            source_index = self.proxy_model.mapToSource(proxy_index)
            track = self.track_model.get_track(source_index.row())
            if track:
                tracks.append(track)
        return tracks

    @Slot()
    def _on_track_context_menu(self, position) -> None:
        """Show context menu for track table."""
        selected = self.get_selected_tracks()
        if not selected:
            return

        menu = QMenu(self)
        count = len(selected)

        if count == 1:
            play_now_action = menu.addAction("Play Now")
        else:
            play_now_action = None

        play_next_action = menu.addAction(
            f"Play Next ({count} track{'s' if count > 1 else ''})"
        )
        add_queue_action = menu.addAction(
            f"Add to Queue ({count} track{'s' if count > 1 else ''})"
        )

        action = menu.exec(self.track_table.viewport().mapToGlobal(position))
        if action is None:
            return

        if action == play_now_action:
            self.track_double_clicked.emit(selected[0])
        elif action == play_next_action:
            self.play_next_requested.emit(selected)
        elif action == add_queue_action:
            self.add_to_queue_requested.emit(selected)

    def _create_tag_edit_group(self) -> QGroupBox:
        """Create the tag editing group box."""
        group = QGroupBox("Edit Tags")
        layout = QVBoxLayout(group)

        form_layout = QFormLayout()

        self.tag_track_label = QLabel("No track selected")
        form_layout.addRow("Track:", self.tag_track_label)

        self.tag_energy_spin = QSpinBox()
        self.tag_energy_spin.setRange(0, 10)
        self.tag_energy_spin.setSpecialValueText("None")
        self.tag_energy_spin.setToolTip("Energy level (1-10, 0 = clear)")
        form_layout.addRow("Energy:", self.tag_energy_spin)

        self.tag_key_input = QLineEdit()
        self.tag_key_input.setPlaceholderText("e.g. Am, Cm, 8A")
        self.tag_key_input.setToolTip("Musical key")
        form_layout.addRow("Key:", self.tag_key_input)

        self.tag_comment_input = QLineEdit()
        self.tag_comment_input.setPlaceholderText("Comment / mood tag")
        self.tag_comment_input.setToolTip("Comment field (also used for mood)")
        form_layout.addRow("Comment:", self.tag_comment_input)

        layout.addLayout(form_layout)

        # Save button
        btn_layout = QHBoxLayout()
        self.tag_save_btn = QPushButton("Save Tags")
        self.tag_save_btn.setEnabled(False)
        self.tag_save_btn.setToolTip("Save tag changes to database")
        self.tag_save_btn.clicked.connect(self._on_tag_save_clicked)
        btn_layout.addWidget(self.tag_save_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return group

    def _populate_tag_fields(self, track: Song) -> None:
        """Populate tag editing fields from a track.

        Args:
            track: Song to populate from.
        """
        self._tag_group.setVisible(True)
        self.tag_track_label.setText(track.display_name)
        self.tag_save_btn.setEnabled(True)

        energy = track.energy if track.energy is not None else 0
        self.tag_energy_spin.setValue(energy)

        key = ""
        if track.tags and track.tags.key:
            key = track.tags.key
        self.tag_key_input.setText(key)

        comment = ""
        if track.tags and track.tags.comment:
            comment = track.tags.comment
        self.tag_comment_input.setText(comment)

        self._editing_track = track

    def _on_tag_save_clicked(self) -> None:
        """Handle tag save button click."""
        if self._database is None or self._editing_track is None:
            return

        track = self._editing_track
        updates = {}

        energy_val = self.tag_energy_spin.value()
        if energy_val > 0:
            updates["Grouping"] = str(energy_val)
        elif track.energy is not None:
            updates["Grouping"] = None

        key_val = self.tag_key_input.text().strip()
        if key_val:
            updates["Key"] = key_val
        elif track.tags and track.tags.key:
            updates["Key"] = None

        comment_val = self.tag_comment_input.text().strip()
        if comment_val:
            updates["Comment"] = comment_val
        elif track.tags and track.tags.comment:
            updates["Comment"] = None

        if not updates:
            return

        self._database.update_song_tags(track.file_path, **updates)
        self._database.save()

        self.status_label.setText(f"Tags saved for {track.display_name}")
        self.status_label.setStyleSheet("color: green;")
        self._log_operation(f"Tags saved for {track.display_name}")

        # Refresh track list
        self._tracks = list(self._database.iter_songs())
        self.track_model.set_tracks(self._tracks)

    def refresh_tracks(self, tracks: list | None = None) -> None:
        """Refresh the track table with updated data.

        Args:
            tracks: New track list.  If None, re-reads from the loaded database.
        """
        if tracks is not None:
            self._tracks = tracks
        elif self._database is not None:
            self._tracks = list(self._database.iter_songs())
        self.track_model.set_tracks(self._tracks)
        self._update_result_count()

    def _log_operation(self, message: str) -> None:
        """Add a timestamped entry to the operation log.

        Args:
            message: Operation description.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.operation_log.insertItem(0, f"[{timestamp}] {message}")
        # Keep only last 20 entries
        while self.operation_log.count() > 20:
            self.operation_log.takeItem(self.operation_log.count() - 1)

    def _on_backup_clicked(self) -> None:
        """Handle backup button click."""
        if self._database is None:
            return
        if self._backup_worker is not None and self._backup_worker.isRunning():
            QMessageBox.warning(self, "Backup In Progress", "A backup is already running.")
            return

        db_path = self._database.db_path
        self.backup_btn.setEnabled(False)
        self.status_label.setText("Creating backup...")
        self.status_label.setStyleSheet("color: blue;")

        self._backup_worker = BackupWorker(db_path)
        self._backup_worker.finished_work.connect(self._on_backup_finished)
        self._backup_worker.error.connect(self._on_backup_error)
        self._backup_worker.start()

    @Slot(object)
    def _on_backup_finished(self, backup_path) -> None:
        """Handle backup completion."""
        self.backup_btn.setEnabled(True)
        self.status_label.setText(f"Backup created: {Path(backup_path).name}")
        self.status_label.setStyleSheet("color: green;")
        self._log_operation(f"Backup created: {Path(backup_path).name}")

    @Slot(str)
    def _on_backup_error(self, error: str) -> None:
        """Handle backup error."""
        self.backup_btn.setEnabled(True)
        self.status_label.setText(f"Backup failed: {error}")
        self.status_label.setStyleSheet("color: red;")

    def _on_validate_clicked(self) -> None:
        """Handle validate button click."""
        if not self._tracks:
            return
        if self._validate_worker is not None and self._validate_worker.isRunning():
            QMessageBox.warning(self, "Validation In Progress", "Validation is already running.")
            return

        self.validate_btn.setEnabled(False)
        self.status_label.setText("Validating...")
        self.status_label.setStyleSheet("color: blue;")

        self._validate_worker = ValidateWorker(self._tracks)
        self._validate_worker.finished_work.connect(self._on_validate_finished)
        self._validate_worker.error.connect(self._on_validate_error)
        self._validate_worker.start()

    @Slot(object)
    def _on_validate_finished(self, report: dict) -> None:
        """Handle validation completion."""
        self.validate_btn.setEnabled(True)

        total = report.get("total", 0)
        valid = report.get("audio_valid", 0)
        missing = report.get("audio_missing", 0)
        non_audio = report.get("non_audio", 0)
        windows = report.get("windows_paths", 0)

        summary = (
            f"Validation: {valid} valid, {missing} missing, "
            f"{non_audio} non-audio, {windows} Windows paths"
        )
        self.status_label.setText(summary)
        self.status_label.setStyleSheet("color: green;" if missing == 0 else "color: orange;")

        # Store for potential clean operation
        self._last_validation = report

        # Show dialog with details
        detail_lines = [f"Total entries: {total}"]
        detail_lines.append(f"Valid audio files: {valid}")
        if missing > 0:
            detail_lines.append(f"Missing files: {missing}")
        if non_audio > 0:
            detail_lines.append(f"Non-audio entries: {non_audio}")
        if windows > 0:
            detail_lines.append(f"Windows paths: {windows}")
        netsearch = report.get("netsearch", 0)
        if netsearch > 0:
            detail_lines.append(f"Streaming entries: {netsearch}")

        QMessageBox.information(
            self, "Validation Results", "\n".join(detail_lines)
        )
        self._log_operation(summary)

    @Slot(str)
    def _on_validate_error(self, error: str) -> None:
        """Handle validation error."""
        self.validate_btn.setEnabled(True)
        self.status_label.setText(f"Validation failed: {error}")
        self.status_label.setStyleSheet("color: red;")

    def _on_clean_clicked(self) -> None:
        """Handle clean button click."""
        if self._database is None or not self._tracks:
            return
        if self._clean_worker is not None and self._clean_worker.isRunning():
            QMessageBox.warning(self, "Clean In Progress", "Clean is already running.")
            return

        # Determine what to clean
        from vdj_manager.files.validator import FileValidator
        validator = FileValidator()
        categories = validator.categorize_entries(iter(self._tracks))

        non_audio = categories.get("non_audio", [])
        missing = categories.get("audio_missing", [])
        to_remove = non_audio + missing

        if not to_remove:
            QMessageBox.information(
                self, "Nothing to Clean",
                "No invalid entries found in the database."
            )
            return

        # Confirm with user
        msg = (
            f"Found {len(to_remove)} entries to remove:\n"
            f"  - {len(non_audio)} non-audio entries\n"
            f"  - {len(missing)} missing files\n\n"
            f"A backup will be created first. Continue?"
        )
        reply = QMessageBox.question(
            self, "Confirm Clean", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Create backup first
        try:
            from vdj_manager.core.backup import BackupManager
            manager = BackupManager()
            manager.create_backup(self._database.db_path, label="pre_clean")
        except Exception as e:
            QMessageBox.warning(self, "Backup Failed", f"Could not create backup: {e}")
            return

        self.clean_btn.setEnabled(False)
        self.status_label.setText("Cleaning...")
        self.status_label.setStyleSheet("color: blue;")

        self._clean_worker = CleanWorker(self._database, to_remove)
        self._clean_worker.finished_work.connect(self._on_clean_finished)
        self._clean_worker.error.connect(self._on_clean_error)
        self._clean_worker.start()

    @Slot(object)
    def _on_clean_finished(self, removed_count: int) -> None:
        """Handle clean completion."""
        self.clean_btn.setEnabled(True)
        self.status_label.setText(f"Cleaned {removed_count} entries")
        self.status_label.setStyleSheet("color: green;")
        self._log_operation(f"Cleaned {removed_count} invalid entries")

        # Refresh tracks
        if self._database is not None:
            self._tracks = list(self._database.iter_songs())
            self.track_model.set_tracks(self._tracks)
            self._update_result_count()
            stats = self._database.get_stats()
            self._update_stats(stats)

    @Slot(str)
    def _on_clean_error(self, error: str) -> None:
        """Handle clean error."""
        self.clean_btn.setEnabled(True)
        self.status_label.setText(f"Clean failed: {error}")
        self.status_label.setStyleSheet("color: red;")
