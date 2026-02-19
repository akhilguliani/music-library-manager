"""Database status panel with track list and statistics."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.config import LOCAL_VDJ_DB, MYNVME_VDJ_DB
from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import DatabaseStats, Song
from vdj_manager.ui.models.track_model import TrackTableModel
from vdj_manager.ui.theme import DARK_THEME, ThemeManager
from vdj_manager.ui.workers.database_worker import (
    BackupWorker,
    CleanWorker,
    DatabaseLoadResult,
    DatabaseLoadWorker,
    ValidateWorker,
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
        self.stats_summary_label.setStyleSheet(
            f"color: {DARK_THEME.text_tertiary}; font-size: 11px; padding: 2px 4px;"
        )
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
        self.status_label.setStyleSheet(f"color: {DARK_THEME.text_tertiary};")
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
        self.track_table.selectionModel().currentRowChanged.connect(self._on_track_selected)
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
        self._set_status_color("loading")

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
            self._set_status_color("success")
            self._log_operation(f"Loaded database with {len(result.tracks)} tracks")

            # Enable action buttons
            self.backup_btn.setEnabled(True)
            self.validate_btn.setEnabled(True)
            self.clean_btn.setEnabled(True)

            # Emit signal
            self.database_loaded.emit(self._database)
        else:
            self.status_label.setText(f"Error: {result.error}")
            self._set_status_color("error")

    @Slot(str)
    def _on_load_error(self, error: str) -> None:
        """Handle loading error."""
        self.load_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error}")
        self._set_status_color("error")

    def _update_stats(self, stats: DatabaseStats | None) -> None:
        """Update the statistics display.

        Args:
            stats: Database statistics.
        """
        if stats is None:
            self.stats_summary_label.setText("No database loaded")
            self.stats_summary_label.setStyleSheet(
                f"color: {DARK_THEME.text_tertiary}; font-size: 11px; padding: 2px 4px;"
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
            f"color: {DARK_THEME.text_muted}; font-size: 11px; padding: 2px 4px;"
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
            source_index = self.proxy_model.mapToSource(self.proxy_model.index(row, 0))
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

        play_next_action = menu.addAction(f"Play Next ({count} track{'s' if count > 1 else ''})")
        add_queue_action = menu.addAction(f"Add to Queue ({count} track{'s' if count > 1 else ''})")

        action = menu.exec(self.track_table.viewport().mapToGlobal(position))
        if action is None:
            return

        if action == play_now_action:
            self.track_double_clicked.emit(selected[0])
        elif action == play_next_action:
            self.play_next_requested.emit(selected)
        elif action == add_queue_action:
            self.add_to_queue_requested.emit(selected)

    # Standard musical keys for combo box
    _STANDARD_KEYS = [
        "",
        "C",
        "Cm",
        "C#",
        "C#m",
        "Db",
        "Dbm",
        "D",
        "Dm",
        "D#",
        "D#m",
        "Eb",
        "Ebm",
        "E",
        "Em",
        "F",
        "Fm",
        "F#",
        "F#m",
        "Gb",
        "Gbm",
        "G",
        "Gm",
        "G#",
        "G#m",
        "Ab",
        "Abm",
        "A",
        "Am",
        "A#",
        "A#m",
        "Bb",
        "Bbm",
        "B",
        "Bm",
        # Camelot notation
        "1A",
        "1B",
        "2A",
        "2B",
        "3A",
        "3B",
        "4A",
        "4B",
        "5A",
        "5B",
        "6A",
        "6B",
        "7A",
        "7B",
        "8A",
        "8B",
        "9A",
        "9B",
        "10A",
        "10B",
        "11A",
        "11B",
        "12A",
        "12B",
    ]

    # Common DJ genres for combo box
    _COMMON_GENRES = [
        "",
        "House",
        "Deep House",
        "Tech House",
        "Progressive House",
        "Techno",
        "Minimal Techno",
        "Hard Techno",
        "Trance",
        "Progressive Trance",
        "Psytrance",
        "Drum & Bass",
        "Dubstep",
        "Bass Music",
        "EDM",
        "Electro",
        "Breakbeat",
        "Disco",
        "Nu-Disco",
        "Funk",
        "Hip-Hop",
        "R&B",
        "Pop",
        "Rock",
        "Ambient",
        "Downtempo",
        "Chillout",
        "Afro House",
        "Melodic House",
        "Organic House",
        "Garage",
        "UK Garage",
        "Jersey Club",
        "Latin",
        "Reggaeton",
        "Dancehall",
    ]

    def _create_tag_edit_group(self) -> QGroupBox:
        """Create the tag editing group box with Common, Extended, and File Tags tabs."""
        group = QGroupBox("Edit Tags")
        layout = QVBoxLayout(group)

        self.tag_track_label = QLabel("No track selected")
        layout.addWidget(self.tag_track_label)

        self.tag_tabs = QTabWidget()

        # --- Common tab ---
        common_widget = QWidget()
        common_form = QFormLayout(common_widget)

        self.tag_title_input = QLineEdit()
        self.tag_title_input.setPlaceholderText("Track title")
        common_form.addRow("Title:", self.tag_title_input)

        self.tag_artist_input = QLineEdit()
        self.tag_artist_input.setPlaceholderText("Artist name")
        common_form.addRow("Artist:", self.tag_artist_input)

        self.tag_album_input = QLineEdit()
        self.tag_album_input.setPlaceholderText("Album name")
        common_form.addRow("Album:", self.tag_album_input)

        self.tag_genre_combo = QComboBox()
        self.tag_genre_combo.setEditable(True)
        self.tag_genre_combo.addItems(self._COMMON_GENRES)
        common_form.addRow("Genre:", self.tag_genre_combo)

        self.tag_year_spin = QSpinBox()
        self.tag_year_spin.setRange(0, 2100)
        self.tag_year_spin.setSpecialValueText("None")
        common_form.addRow("Year:", self.tag_year_spin)

        self.tag_bpm_spin = QDoubleSpinBox()
        self.tag_bpm_spin.setRange(0.0, 999.0)
        self.tag_bpm_spin.setDecimals(1)
        self.tag_bpm_spin.setSpecialValueText("None")
        common_form.addRow("BPM:", self.tag_bpm_spin)

        self.tag_key_combo = QComboBox()
        self.tag_key_combo.setEditable(True)
        self.tag_key_combo.addItems(self._STANDARD_KEYS)
        # Keep backward compat: expose as tag_key_input for tests
        self.tag_key_input = self.tag_key_combo
        common_form.addRow("Key:", self.tag_key_combo)

        self.tag_energy_spin = QSpinBox()
        self.tag_energy_spin.setRange(0, 10)
        self.tag_energy_spin.setSpecialValueText("None")
        self.tag_energy_spin.setToolTip("Energy level (1-10, 0 = clear)")
        common_form.addRow("Energy:", self.tag_energy_spin)

        self.tag_rating_spin = QSpinBox()
        self.tag_rating_spin.setRange(0, 5)
        self.tag_rating_spin.setSpecialValueText("None")
        common_form.addRow("Rating:", self.tag_rating_spin)

        self.tag_comment_input = QLineEdit()
        self.tag_comment_input.setPlaceholderText("Comment")
        common_form.addRow("Comment:", self.tag_comment_input)

        self.tag_tabs.addTab(common_widget, "Common")

        # --- Extended tab ---
        extended_widget = QWidget()
        extended_form = QFormLayout(extended_widget)

        self.tag_mood_input = QLineEdit()
        self.tag_mood_input.setPlaceholderText("#happy #uplifting #summer")
        self.tag_mood_input.setToolTip("Mood/style hashtags (User2 field)")
        extended_form.addRow("Mood:", self.tag_mood_input)

        self.tag_composer_input = QLineEdit()
        extended_form.addRow("Composer:", self.tag_composer_input)

        self.tag_remix_input = QLineEdit()
        extended_form.addRow("Remix:", self.tag_remix_input)

        self.tag_label_input = QLineEdit()
        extended_form.addRow("Label:", self.tag_label_input)

        self.tag_track_number_spin = QSpinBox()
        self.tag_track_number_spin.setRange(0, 999)
        self.tag_track_number_spin.setSpecialValueText("None")
        extended_form.addRow("Track #:", self.tag_track_number_spin)

        self.tag_color_input = QLineEdit()
        self.tag_color_input.setPlaceholderText("VDJ color value")
        extended_form.addRow("Color:", self.tag_color_input)

        self.tag_flag_spin = QSpinBox()
        self.tag_flag_spin.setRange(0, 1)
        self.tag_flag_spin.setSpecialValueText("None")
        extended_form.addRow("Flag:", self.tag_flag_spin)

        self.tag_tabs.addTab(extended_widget, "Extended")

        # --- File Tags tab (populated in commit 3) ---
        self._file_tags_widget = QWidget()
        self._file_tags_form = QFormLayout(self._file_tags_widget)

        self.file_tag_title = QLineEdit()
        self._file_tags_form.addRow("Title:", self.file_tag_title)
        self.file_tag_artist = QLineEdit()
        self._file_tags_form.addRow("Artist:", self.file_tag_artist)
        self.file_tag_album = QLineEdit()
        self._file_tags_form.addRow("Album:", self.file_tag_album)
        self.file_tag_genre = QLineEdit()
        self._file_tags_form.addRow("Genre:", self.file_tag_genre)
        self.file_tag_year = QLineEdit()
        self._file_tags_form.addRow("Year:", self.file_tag_year)
        self.file_tag_track_number = QLineEdit()
        self._file_tags_form.addRow("Track #:", self.file_tag_track_number)
        self.file_tag_bpm = QLineEdit()
        self._file_tags_form.addRow("BPM:", self.file_tag_bpm)
        self.file_tag_key = QLineEdit()
        self._file_tags_form.addRow("Key:", self.file_tag_key)
        self.file_tag_composer = QLineEdit()
        self._file_tags_form.addRow("Composer:", self.file_tag_composer)
        self.file_tag_comment = QLineEdit()
        self._file_tags_form.addRow("Comment:", self.file_tag_comment)

        file_tag_btn_layout = QHBoxLayout()
        self.file_tag_read_btn = QPushButton("Read from File")
        self.file_tag_read_btn.clicked.connect(self._on_file_tag_read)
        file_tag_btn_layout.addWidget(self.file_tag_read_btn)

        self.file_tag_save_btn = QPushButton("Save to File")
        self.file_tag_save_btn.clicked.connect(self._on_file_tag_save)
        file_tag_btn_layout.addWidget(self.file_tag_save_btn)

        self.file_tag_sync_vdj_btn = QPushButton("VDJ \u2192 File")
        self.file_tag_sync_vdj_btn.setToolTip("Write VDJ database tags to file")
        self.file_tag_sync_vdj_btn.clicked.connect(self._on_sync_vdj_to_file)
        file_tag_btn_layout.addWidget(self.file_tag_sync_vdj_btn)

        self.file_tag_import_btn = QPushButton("File \u2192 VDJ")
        self.file_tag_import_btn.setToolTip("Import file tags into VDJ database")
        self.file_tag_import_btn.clicked.connect(self._on_sync_file_to_vdj)
        file_tag_btn_layout.addWidget(self.file_tag_import_btn)

        file_tag_btn_layout.addStretch()
        self._file_tags_form.addRow(file_tag_btn_layout)

        self.tag_tabs.addTab(self._file_tags_widget, "File Tags")

        # Auto-read file tags when switching to File Tags tab
        self.tag_tabs.currentChanged.connect(self._on_tag_tab_changed)

        layout.addWidget(self.tag_tabs)

        # Save / Revert buttons
        btn_layout = QHBoxLayout()
        self.tag_save_btn = QPushButton("Save Tags")
        self.tag_save_btn.setEnabled(False)
        self.tag_save_btn.setToolTip("Save tag changes to VDJ database")
        self.tag_save_btn.clicked.connect(self._on_tag_save_clicked)
        btn_layout.addWidget(self.tag_save_btn)

        self.tag_revert_btn = QPushButton("Revert")
        self.tag_revert_btn.setEnabled(False)
        self.tag_revert_btn.setToolTip("Revert to saved values")
        self.tag_revert_btn.clicked.connect(self._on_tag_revert_clicked)
        btn_layout.addWidget(self.tag_revert_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return group

    def _populate_tag_fields(self, track: Song) -> None:
        """Populate tag editing fields from a track."""
        self._tag_group.setVisible(True)
        self.tag_track_label.setText(track.display_name)
        self.tag_save_btn.setEnabled(True)
        self.tag_revert_btn.setEnabled(True)
        self._editing_track = track

        tags = track.tags

        # Common tab
        self.tag_title_input.setText(tags.title or "" if tags else "")
        self.tag_artist_input.setText(tags.author or "" if tags else "")
        self.tag_album_input.setText(tags.album or "" if tags else "")

        genre = tags.genre or "" if tags else ""
        idx = self.tag_genre_combo.findText(genre)
        if idx >= 0:
            self.tag_genre_combo.setCurrentIndex(idx)
        else:
            self.tag_genre_combo.setCurrentText(genre)

        self.tag_year_spin.setValue(tags.year or 0 if tags else 0)

        bpm = tags.bpm if tags else None
        self.tag_bpm_spin.setValue(bpm if bpm is not None else 0.0)

        key = tags.key or "" if tags else ""
        idx = self.tag_key_combo.findText(key)
        if idx >= 0:
            self.tag_key_combo.setCurrentIndex(idx)
        else:
            self.tag_key_combo.setCurrentText(key)

        energy = track.energy if track.energy is not None else 0
        self.tag_energy_spin.setValue(energy)

        self.tag_rating_spin.setValue(tags.rating or 0 if tags else 0)
        self.tag_comment_input.setText(tags.comment or "" if tags else "")

        # Extended tab
        self.tag_mood_input.setText(tags.user2 or "" if tags else "")
        self.tag_composer_input.setText(tags.composer or "" if tags else "")
        self.tag_remix_input.setText(tags.remix or "" if tags else "")
        self.tag_label_input.setText(tags.label or "" if tags else "")
        self.tag_track_number_spin.setValue(tags.track_number or 0 if tags else 0)
        self.tag_color_input.setText(tags.color or "" if tags else "")
        self.tag_flag_spin.setValue(tags.flag or 0 if tags else 0)

        # Enable/disable file tag buttons based on file accessibility
        is_accessible = not track.is_windows_path and Path(track.file_path).exists()
        self.file_tag_read_btn.setEnabled(is_accessible)
        self.file_tag_save_btn.setEnabled(is_accessible)
        self.file_tag_sync_vdj_btn.setEnabled(is_accessible)
        self.file_tag_import_btn.setEnabled(is_accessible)

    def _on_tag_revert_clicked(self) -> None:
        """Revert tag fields to the current track's saved values."""
        if self._editing_track is not None:
            self._populate_tag_fields(self._editing_track)

    def _on_tag_save_clicked(self) -> None:
        """Handle tag save button click — saves Common + Extended tabs to VDJ database."""
        if self._database is None or self._editing_track is None:
            return

        track = self._editing_track
        tags = track.tags
        updates: dict[str, str | int | float | None] = {}

        # --- Helper to compare and build update ---
        def _text_update(alias: str, widget_val: str, old_val: str | None) -> None:
            val = widget_val.strip()
            if val:
                if val != (old_val or ""):
                    updates[alias] = val
            elif old_val:
                updates[alias] = None

        def _int_update(alias: str, widget_val: int, old_val: int | None) -> None:
            if widget_val > 0:
                if widget_val != (old_val or 0):
                    updates[alias] = str(widget_val)
            elif old_val is not None and old_val > 0:
                updates[alias] = None

        # Common tab
        _text_update("Title", self.tag_title_input.text(), tags.title if tags else None)
        _text_update("Author", self.tag_artist_input.text(), tags.author if tags else None)
        _text_update("Album", self.tag_album_input.text(), tags.album if tags else None)
        _text_update("Genre", self.tag_genre_combo.currentText(), tags.genre if tags else None)
        _int_update("Year", self.tag_year_spin.value(), tags.year if tags else None)

        bpm_val = self.tag_bpm_spin.value()
        old_bpm = tags.bpm if tags else None
        if bpm_val > 0.0:
            if old_bpm is None or abs(bpm_val - old_bpm) > 0.05:
                updates["Bpm"] = str(bpm_val)
        elif old_bpm is not None and old_bpm > 0:
            updates["Bpm"] = None

        _text_update("Key", self.tag_key_combo.currentText(), tags.key if tags else None)

        energy_val = self.tag_energy_spin.value()
        if energy_val > 0:
            if energy_val != (track.energy or 0):
                updates["Grouping"] = str(energy_val)
        elif track.energy is not None:
            updates["Grouping"] = None

        _int_update("Rating", self.tag_rating_spin.value(), tags.rating if tags else None)
        _text_update("Comment", self.tag_comment_input.text(), tags.comment if tags else None)

        # Extended tab
        _text_update("User2", self.tag_mood_input.text(), tags.user2 if tags else None)
        _text_update("Composer", self.tag_composer_input.text(), tags.composer if tags else None)
        _text_update("Remix", self.tag_remix_input.text(), tags.remix if tags else None)
        _text_update("Label", self.tag_label_input.text(), tags.label if tags else None)
        _int_update(
            "TrackNumber", self.tag_track_number_spin.value(), tags.track_number if tags else None
        )
        _text_update("Color", self.tag_color_input.text(), tags.color if tags else None)
        _int_update("Flag", self.tag_flag_spin.value(), tags.flag if tags else None)

        if not updates:
            return

        self._database.update_song_tags(track.file_path, **updates)
        self._database.save()

        self.status_label.setText(f"Tags saved for {track.display_name}")
        self._set_status_color("success")
        self._log_operation(f"Tags saved for {track.display_name}")

        # Refresh track list
        self._tracks = list(self._database.iter_songs())
        self.track_model.set_tracks(self._tracks)

    # --- File Tags tab handlers ---

    def _on_tag_tab_changed(self, index: int) -> None:
        """Auto-read file tags when switching to File Tags tab."""
        if index == 2 and self._editing_track is not None:
            self._on_file_tag_read()

    def _on_file_tag_read(self) -> None:
        """Read embedded tags from the audio file."""
        if self._editing_track is None:
            return

        track = self._editing_track
        if track.is_windows_path:
            QMessageBox.information(
                self, "Not Available", "Cannot read file tags for Windows-path tracks."
            )
            return

        file_path = track.file_path
        if not Path(file_path).exists():
            QMessageBox.warning(self, "File Not Found", f"File not found:\n{file_path}")
            return

        try:
            from vdj_manager.files.id3_editor import FileTagEditor

            editor = FileTagEditor()
            file_tags = editor.read_tags(file_path)
        except Exception as e:
            QMessageBox.warning(self, "Read Error", f"Failed to read file tags:\n{e}")
            return

        self.file_tag_title.setText(file_tags.get("title") or "")
        self.file_tag_artist.setText(file_tags.get("artist") or "")
        self.file_tag_album.setText(file_tags.get("album") or "")
        self.file_tag_genre.setText(file_tags.get("genre") or "")
        self.file_tag_year.setText(file_tags.get("year") or "")
        self.file_tag_track_number.setText(file_tags.get("track_number") or "")
        self.file_tag_bpm.setText(file_tags.get("bpm") or "")
        self.file_tag_key.setText(file_tags.get("key") or "")
        self.file_tag_composer.setText(file_tags.get("composer") or "")
        self.file_tag_comment.setText(file_tags.get("comment") or "")

    def _on_file_tag_save(self) -> None:
        """Write file tag fields to the audio file."""
        if self._editing_track is None:
            return

        file_path = self._editing_track.file_path
        if self._editing_track.is_windows_path or not Path(file_path).exists():
            return

        file_tags = {
            "title": self.file_tag_title.text().strip() or None,
            "artist": self.file_tag_artist.text().strip() or None,
            "album": self.file_tag_album.text().strip() or None,
            "genre": self.file_tag_genre.text().strip() or None,
            "year": self.file_tag_year.text().strip() or None,
            "track_number": self.file_tag_track_number.text().strip() or None,
            "bpm": self.file_tag_bpm.text().strip() or None,
            "key": self.file_tag_key.text().strip() or None,
            "composer": self.file_tag_composer.text().strip() or None,
            "comment": self.file_tag_comment.text().strip() or None,
        }

        try:
            from vdj_manager.files.id3_editor import FileTagEditor

            editor = FileTagEditor()
            ok = editor.write_tags(file_path, file_tags)
            if ok:
                self.status_label.setText("File tags saved")
                self._set_status_color("success")
                self._log_operation(f"File tags saved for {self._editing_track.display_name}")
            else:
                self.status_label.setText("File tags save failed")
                self._set_status_color("error")
        except Exception as e:
            QMessageBox.warning(self, "Write Error", f"Failed to write file tags:\n{e}")

    def _on_sync_vdj_to_file(self) -> None:
        """Sync VDJ database tags to the audio file."""
        if self._editing_track is None or self._editing_track.is_windows_path:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Sync",
            "Overwrite file tags with VDJ database values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from vdj_manager.files.id3_editor import FileTagEditor, vdj_tags_to_file_tags

            file_tags = vdj_tags_to_file_tags(self._editing_track)
            editor = FileTagEditor()
            ok = editor.write_tags(self._editing_track.file_path, file_tags)
            if ok:
                self.status_label.setText("VDJ tags synced to file")
                self._set_status_color("success")
                self._log_operation(f"VDJ \u2192 File sync for {self._editing_track.display_name}")
                # Re-read to show updated values
                self._on_file_tag_read()
            else:
                self.status_label.setText("Sync failed")
                self._set_status_color("error")
        except Exception as e:
            QMessageBox.warning(self, "Sync Error", f"Failed to sync:\n{e}")

    def _on_sync_file_to_vdj(self) -> None:
        """Import file tags into VDJ database."""
        if self._editing_track is None or self._database is None:
            return
        if self._editing_track.is_windows_path:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Import",
            "Overwrite VDJ database tags with values from the audio file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from vdj_manager.files.id3_editor import FileTagEditor, file_tags_to_vdj_kwargs

            editor = FileTagEditor()
            file_tags = editor.read_tags(self._editing_track.file_path)
            vdj_kwargs = file_tags_to_vdj_kwargs(file_tags)
            if vdj_kwargs:
                self._database.update_song_tags(self._editing_track.file_path, **vdj_kwargs)
                self._database.save()
                self._tracks = list(self._database.iter_songs())
                self.track_model.set_tracks(self._tracks)
                self.status_label.setText("File tags imported to VDJ")
                self._set_status_color("success")
                self._log_operation(
                    f"File \u2192 VDJ import for {self._editing_track.display_name}"
                )
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to import:\n{e}")

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

    def _set_status_color(self, status: str) -> None:
        """Update the status label color based on status keyword."""
        self.status_label.setStyleSheet(f"color: {ThemeManager().status_color(status)}")

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
        self._set_status_color("loading")

        self._backup_worker = BackupWorker(db_path)
        self._backup_worker.finished_work.connect(self._on_backup_finished)
        self._backup_worker.error.connect(self._on_backup_error)
        self._backup_worker.start()

    @Slot(object)
    def _on_backup_finished(self, backup_path) -> None:
        """Handle backup completion."""
        self.backup_btn.setEnabled(True)
        self.status_label.setText(f"Backup created: {Path(backup_path).name}")
        self._set_status_color("success")
        self._log_operation(f"Backup created: {Path(backup_path).name}")

    @Slot(str)
    def _on_backup_error(self, error: str) -> None:
        """Handle backup error."""
        self.backup_btn.setEnabled(True)
        self.status_label.setText(f"Backup failed: {error}")
        self._set_status_color("error")

    def _on_validate_clicked(self) -> None:
        """Handle validate button click."""
        if not self._tracks:
            return
        if self._validate_worker is not None and self._validate_worker.isRunning():
            QMessageBox.warning(self, "Validation In Progress", "Validation is already running.")
            return

        self.validate_btn.setEnabled(False)
        self.status_label.setText("Validating...")
        self._set_status_color("loading")

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
        self._set_status_color("success" if missing == 0 else "warning")

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

        QMessageBox.information(self, "Validation Results", "\n".join(detail_lines))
        self._log_operation(summary)

    @Slot(str)
    def _on_validate_error(self, error: str) -> None:
        """Handle validation error."""
        self.validate_btn.setEnabled(True)
        self.status_label.setText(f"Validation failed: {error}")
        self._set_status_color("error")

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
                self, "Nothing to Clean", "No invalid entries found in the database."
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
            self,
            "Confirm Clean",
            msg,
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
        self._set_status_color("loading")

        self._clean_worker = CleanWorker(self._database, to_remove)
        self._clean_worker.finished_work.connect(self._on_clean_finished)
        self._clean_worker.error.connect(self._on_clean_error)
        self._clean_worker.start()

    @Slot(object)
    def _on_clean_finished(self, removed_count: int) -> None:
        """Handle clean completion."""
        self.clean_btn.setEnabled(True)
        self.status_label.setText(f"Cleaned {removed_count} entries")
        self._set_status_color("success")
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
        self._set_status_color("error")
