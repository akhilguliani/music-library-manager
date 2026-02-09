"""Main window for VDJ Manager Desktop Application."""

from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QAction, QKeySequence

from vdj_manager.player.bridge import PlaybackBridge
from vdj_manager.player.engine import TrackInfo
from vdj_manager.ui.widgets.analysis_panel import AnalysisPanel
from vdj_manager.ui.widgets.database_panel import DatabasePanel
from vdj_manager.ui.widgets.export_panel import ExportPanel
from vdj_manager.ui.widgets.files_panel import FilesPanel
from vdj_manager.ui.widgets.mini_player import MiniPlayer
from vdj_manager.ui.widgets.normalization_panel import NormalizationPanel
from vdj_manager.ui.widgets.player_panel import PlayerPanel


class MainWindow(QMainWindow):
    """Main application window with tabbed interface and mini player."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("VDJ Manager")
        self.setMinimumSize(1000, 700)

        self._database = None
        self._save_pending = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_save)

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_status_bar()

    def _setup_ui(self) -> None:
        """Set up the main UI layout with tabs and mini player."""
        # Create PlaybackBridge (shared across all panels)
        self._playback_bridge = PlaybackBridge(self)
        vlc_available = self._playback_bridge.initialize()

        # Central container: tabs + mini player at bottom
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setDocumentMode(True)
        central_layout.addWidget(self.tab_widget, stretch=1)

        # Mini player at bottom
        self.mini_player = MiniPlayer(self._playback_bridge)
        self.mini_player.expand_requested.connect(
            lambda: self.tab_widget.setCurrentIndex(5)
        )
        if not vlc_available:
            self.mini_player.set_vlc_unavailable()
        central_layout.addWidget(self.mini_player)

        self.setCentralWidget(central)

        # Create tabs: Database(0), Normalization(1), Files(2), Analysis(3), Export(4), Player(5)
        self._create_database_tab()
        self._create_normalization_tab()
        self._create_files_tab()
        self._create_analysis_tab()
        self._create_export_tab()
        self._create_player_tab()

    def _create_database_tab(self) -> None:
        """Create the database overview tab."""
        self.database_panel = DatabasePanel()
        self.database_panel.database_loaded.connect(self._on_database_loaded)
        self.database_panel.track_selected.connect(self._on_track_selected)
        self.database_panel.track_double_clicked.connect(self._on_track_play_requested)

        self.tab_widget.addTab(self.database_panel, "Database")

    def _create_normalization_tab(self) -> None:
        """Create the normalization control tab."""
        self.normalization_panel = NormalizationPanel()
        self.tab_widget.addTab(self.normalization_panel, "Normalization")

    def _create_files_tab(self) -> None:
        """Create the file management tab."""
        self.files_panel = FilesPanel()
        self.tab_widget.addTab(self.files_panel, "Files")

    def _create_analysis_tab(self) -> None:
        """Create the audio analysis tab."""
        self.analysis_panel = AnalysisPanel()
        self.tab_widget.addTab(self.analysis_panel, "Analysis")

    def _create_export_tab(self) -> None:
        """Create the export tab."""
        self.export_panel = ExportPanel()
        self.tab_widget.addTab(self.export_panel, "Export")

    def _create_player_tab(self) -> None:
        """Create the full player tab."""
        self.player_panel = PlayerPanel(self._playback_bridge)
        self.player_panel.rating_changed.connect(self._on_rating_changed)
        self._playback_bridge.track_finished.connect(self._on_track_playback_finished)
        self.tab_widget.addTab(self.player_panel, "Player")

    def _setup_menu_bar(self) -> None:
        """Set up the application menu bar."""
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        open_db_action = QAction("&Open Database...", self)
        open_db_action.setShortcut(QKeySequence.StandardKey.Open)
        open_db_action.triggered.connect(self._on_open_database)
        file_menu.addAction(open_db_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")

        tab_names = [
            ("&Database", "Ctrl+1", 0),
            ("&Normalization", "Ctrl+2", 1),
            ("&Files", "Ctrl+3", 2),
            ("&Analysis", "Ctrl+4", 3),
            ("&Export", "Ctrl+5", 4),
            ("&Player", "Ctrl+6", 5),
        ]
        for name, shortcut, idx in tab_names:
            action = QAction(name, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(lambda checked=False, i=idx: self.tab_widget.setCurrentIndex(i))
            view_menu.addAction(action)

        # Playback menu
        playback_menu = menu_bar.addMenu("&Playback")

        play_action = QAction("Play/Pause", self)
        play_action.setShortcut(QKeySequence("Space"))
        play_action.triggered.connect(self._playback_bridge.toggle_play_pause)
        playback_menu.addAction(play_action)

        next_action = QAction("Next Track", self)
        next_action.setShortcut(QKeySequence("Ctrl+Right"))
        next_action.triggered.connect(self._playback_bridge.next_track)
        playback_menu.addAction(next_action)

        prev_action = QAction("Previous Track", self)
        prev_action.setShortcut(QKeySequence("Ctrl+Left"))
        prev_action.triggered.connect(self._playback_bridge.previous_track)
        playback_menu.addAction(prev_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_status_bar(self) -> None:
        """Set up the status bar."""
        status_bar = self.statusBar()
        status_bar.showMessage("Ready")

    @Slot()
    def _on_open_database(self) -> None:
        """Handle opening a database file."""
        self.statusBar().showMessage("Open database not yet implemented")

    @Slot(object)
    def _on_database_loaded(self, database) -> None:
        """Handle database loaded event."""
        self._database = database
        tracks = list(database.iter_songs())
        track_count = len(tracks)
        self.statusBar().showMessage(f"Loaded database with {track_count} tracks")

        # Update all panels with database
        self.normalization_panel.set_database(database, tracks)
        for panel in (self.files_panel, self.analysis_panel, self.export_panel):
            if hasattr(panel, "set_database"):
                panel.set_database(database)

    @Slot(object)
    def _on_track_selected(self, track) -> None:
        """Handle track selection event."""
        self.statusBar().showMessage(f"Selected: {track.display_name}")

    @Slot(object)
    def _on_track_play_requested(self, song) -> None:
        """Handle double-click on track — start playing."""
        track_info = TrackInfo.from_song(song)
        self._playback_bridge.play_track(track_info)

    @Slot(object)
    def _on_track_playback_finished(self, track) -> None:
        """Increment play count and set last played on track completion."""
        if not self._database:
            return
        import time

        song = self._database.get_song(track.file_path)
        if song:
            current_count = (song.infos.play_count or 0) if song.infos else 0
            self._database.update_song_infos(
                track.file_path,
                PlayCount=current_count + 1,
                LastPlay=int(time.time()),
            )
            self._schedule_save()

    @Slot(str, int)
    def _on_rating_changed(self, file_path: str, rating: int) -> None:
        """Persist rating change to database."""
        if not self._database:
            return
        self._database.update_song_tags(file_path, Rating=rating)
        self._schedule_save()

    def _schedule_save(self) -> None:
        """Schedule a debounced save (5s delay to batch rapid changes)."""
        self._save_pending = True
        self._save_timer.start(5000)

    @Slot()
    def _flush_save(self) -> None:
        """Perform the actual save."""
        if self._save_pending and self._database:
            try:
                self._database.save()
                self._save_pending = False
            except Exception:
                pass  # Save will retry on next schedule or on close

    @Slot()
    def _on_about(self) -> None:
        """Show the about dialog."""
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "About VDJ Manager",
            "VDJ Manager Desktop\n\n"
            "A desktop application for managing your VirtualDJ library.\n\n"
            "Features:\n"
            "- Audio playback with VLC\n"
            "- Audio loudness normalization\n"
            "- Energy and mood analysis\n"
            "- Library organization\n\n"
            "Version 0.2.0",
        )

    def closeEvent(self, event) -> None:
        """Flush pending saves and clean up player resources on close."""
        self._save_timer.stop()
        self._flush_save()
        self._playback_bridge.shutdown()
        super().closeEvent(event)
