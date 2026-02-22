"""Main window for VDJ Manager Desktop Application."""

import logging

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

from vdj_manager.player.bridge import PlaybackBridge
from vdj_manager.player.engine import TrackInfo
from vdj_manager.ui.navigation import (
    NavigationItem,
    SidebarNavigationProvider,
    SidebarWidget,
)
from vdj_manager.ui.widgets.analysis_panel import AnalysisPanel
from vdj_manager.ui.widgets.command_palette import CommandItem, CommandPalette
from vdj_manager.ui.widgets.database_panel import DatabasePanel
from vdj_manager.ui.widgets.export_panel import ExportPanel
from vdj_manager.ui.widgets.files_panel import FilesPanel
from vdj_manager.ui.widgets.mini_player import MiniPlayer
from vdj_manager.ui.widgets.normalization_panel import NormalizationPanel
from vdj_manager.ui.widgets.player_panel import PlayerPanel
from vdj_manager.ui.widgets.shortcuts_dialog import ShortcutsDialog
from vdj_manager.ui.widgets.workflow_panel import WorkflowPanel


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation and mini player."""

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
        self._setup_navigation()
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_command_palette()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        """Set up the main UI layout with sidebar, panel stack, and mini player."""
        # Create PlaybackBridge (shared across all panels)
        self._playback_bridge = PlaybackBridge(self)
        vlc_available = self._playback_bridge.initialize()

        # Central container: splitter + mini player at bottom
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Sidebar + panel stack in a horizontal splitter
        self._sidebar = SidebarWidget()
        self._panel_stack = QStackedWidget()
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(self._panel_stack)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setStretchFactor(0, 0)  # Sidebar: fixed
        self._splitter.setStretchFactor(1, 1)  # Panel stack: stretch
        central_layout.addWidget(self._splitter, stretch=1)

        # Mini player at bottom
        self.mini_player = MiniPlayer(self._playback_bridge)
        self.mini_player.expand_requested.connect(lambda: self._navigation.navigate_to("Player"))
        if not vlc_available:
            self.mini_player.set_vlc_unavailable()
        central_layout.addWidget(self.mini_player)

        self.setCentralWidget(central)

        # Create panels (no addTab — navigation registers them into the stack)
        self._create_database_tab()
        self._create_normalization_tab()
        self._create_files_tab()
        self._create_analysis_tab()
        self._create_export_tab()
        self._create_player_tab()
        self._create_workflow_tab()

    def _create_database_tab(self) -> None:
        """Create the database overview tab."""
        self.database_panel = DatabasePanel()
        self.database_panel.database_loaded.connect(self._on_database_loaded)
        self.database_panel.track_selected.connect(self._on_track_selected)
        self.database_panel.track_double_clicked.connect(self._on_track_play_requested)
        self.database_panel.play_next_requested.connect(self._on_play_next_requested)
        self.database_panel.add_to_queue_requested.connect(self._on_add_to_queue_requested)
        self.database_panel.save_requested.connect(self._schedule_save)

    def _create_normalization_tab(self) -> None:
        """Create the normalization control tab."""
        self.normalization_panel = NormalizationPanel()

    def _create_files_tab(self) -> None:
        """Create the file management tab."""
        self.files_panel = FilesPanel()

    def _create_analysis_tab(self) -> None:
        """Create the audio analysis tab."""
        self.analysis_panel = AnalysisPanel()

    def _create_export_tab(self) -> None:
        """Create the export tab."""
        self.export_panel = ExportPanel()

    def _create_player_tab(self) -> None:
        """Create the full player tab."""
        self.player_panel = PlayerPanel(self._playback_bridge)
        self.player_panel.rating_changed.connect(self._on_rating_changed)
        self.player_panel.cues_changed.connect(self._on_cues_changed)
        self.player_panel.tracks_dropped.connect(self._on_tracks_dropped)
        self._playback_bridge.track_finished.connect(self._on_track_playback_finished)

    def _create_workflow_tab(self) -> None:
        """Create the workflow dashboard tab."""
        self.workflow_panel = WorkflowPanel()
        self.workflow_panel.database_changed.connect(self._on_workflow_database_changed)

    def _setup_navigation(self) -> None:
        """Set up the SidebarNavigationProvider with section groupings."""
        self._navigation = SidebarNavigationProvider(self._sidebar, self._panel_stack)
        panels = [
            ("Database", "\u25c9", "Ctrl+1", self.database_panel),
            ("Normalization", "\u224b", "Ctrl+2", self.normalization_panel),
            ("Files", "\u229e", "Ctrl+3", self.files_panel),
            ("Analysis", "\u223f", "Ctrl+4", self.analysis_panel),
            ("Export", "\u2197", "Ctrl+5", self.export_panel),
            ("Player", "\u25b6", "Ctrl+6", self.player_panel),
            ("Workflow", "\u26a1", "Ctrl+7", self.workflow_panel),
        ]
        for name, icon, shortcut, panel in panels:
            self._navigation.register_panel(NavigationItem(name, icon, shortcut, panel))

        self._sidebar.set_sections(
            [
                ("Library", ["Database"]),
                ("Tools", ["Normalization", "Files", "Analysis", "Export"]),
                ("Player", ["Player", "Workflow"]),
            ]
        )
        self._navigation.navigate_to("Database")

    def _setup_command_palette(self) -> None:
        """Set up the command palette with all available commands."""
        self._command_palette = CommandPalette(self)

        commands = [
            # Navigation
            CommandItem(
                "Database", "Ctrl+1", "Navigation", lambda: self._navigation.navigate_to("Database")
            ),
            CommandItem(
                "Normalization",
                "Ctrl+2",
                "Navigation",
                lambda: self._navigation.navigate_to("Normalization"),
            ),
            CommandItem(
                "Files", "Ctrl+3", "Navigation", lambda: self._navigation.navigate_to("Files")
            ),
            CommandItem(
                "Analysis", "Ctrl+4", "Navigation", lambda: self._navigation.navigate_to("Analysis")
            ),
            CommandItem(
                "Export", "Ctrl+5", "Navigation", lambda: self._navigation.navigate_to("Export")
            ),
            CommandItem(
                "Player", "Ctrl+6", "Navigation", lambda: self._navigation.navigate_to("Player")
            ),
            CommandItem(
                "Workflow", "Ctrl+7", "Navigation", lambda: self._navigation.navigate_to("Workflow")
            ),
            # Database operations
            CommandItem(
                "Load Database", "", "Database", lambda: self.database_panel._on_load_clicked()
            ),
            CommandItem(
                "Backup Database", "", "Database", lambda: self.database_panel._on_backup_clicked()
            ),
            CommandItem(
                "Validate Database",
                "",
                "Database",
                lambda: self.database_panel._on_validate_clicked(),
            ),
            CommandItem(
                "Clean Database", "", "Database", lambda: self.database_panel._on_clean_clicked()
            ),
            # Track browser
            CommandItem("Focus Search", "Ctrl+L", "Browser", lambda: self._focus_search()),
            CommandItem(
                "Toggle Column Filters",
                "Ctrl+F",
                "Browser",
                lambda: self.database_panel.toggle_filter_row(),
            ),
            CommandItem(
                "Toggle Column Browser",
                "Ctrl+B",
                "Browser",
                lambda: self.database_panel.toggle_column_browser(),
            ),
            # Playback
            CommandItem(
                "Play / Pause", "Space", "Playback", self._playback_bridge.toggle_play_pause
            ),
            CommandItem("Next Track", "Ctrl+Right", "Playback", self._playback_bridge.next_track),
            CommandItem(
                "Previous Track", "Ctrl+Left", "Playback", self._playback_bridge.previous_track
            ),
            # Help
            CommandItem("Keyboard Shortcuts", "?", "Help", self._show_shortcuts_dialog),
        ]
        self._command_palette.register_commands(commands)

        # Cmd+K shortcut
        palette_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        palette_shortcut.activated.connect(self._command_palette.show_palette)

    def _setup_shortcuts(self) -> None:
        """Set up additional keyboard shortcuts."""
        # Ctrl+L: focus search bar in database panel
        search_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        search_shortcut.activated.connect(self._focus_search)

        # Ctrl+Enter: play selected track
        play_selected = QShortcut(QKeySequence("Ctrl+Return"), self)
        play_selected.activated.connect(self._play_selected_track)

    def _focus_search(self) -> None:
        """Focus the search bar in the database panel."""
        self._navigation.navigate_to("Database")
        self.database_panel.search_input.setFocus()

    def _play_selected_track(self) -> None:
        """Play the currently selected track in the database panel."""
        track = self.database_panel.get_selected_track()
        if track:
            self._on_track_play_requested(track)

    def _is_text_input_focused(self) -> bool:
        """Check if a text input widget currently has focus."""
        from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QSpinBox, QTextEdit

        widget = QApplication.focusWidget()
        return isinstance(widget, (QLineEdit, QTextEdit, QSpinBox, QComboBox))

    def _on_play_pause_shortcut(self) -> None:
        """Handle Space shortcut — only toggle play/pause when not typing."""
        if not self._is_text_input_focused():
            self._playback_bridge.toggle_play_pause()

    def _on_shortcuts_shortcut(self) -> None:
        """Handle ? shortcut — only open dialog when not typing."""
        if not self._is_text_input_focused():
            self._show_shortcuts_dialog()

    def _show_shortcuts_dialog(self) -> None:
        """Show the keyboard shortcuts help dialog."""
        dialog = ShortcutsDialog(self)
        dialog.exec()

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

        view_panels = [
            ("&Database", "Ctrl+1", "Database"),
            ("&Normalization", "Ctrl+2", "Normalization"),
            ("&Files", "Ctrl+3", "Files"),
            ("&Analysis", "Ctrl+4", "Analysis"),
            ("&Export", "Ctrl+5", "Export"),
            ("&Player", "Ctrl+6", "Player"),
            ("&Workflow", "Ctrl+7", "Workflow"),
        ]
        for label, shortcut, panel_name in view_panels:
            action = QAction(label, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(
                lambda checked=False, n=panel_name: self._navigation.navigate_to(n)
            )
            view_menu.addAction(action)

        # Playback menu
        playback_menu = menu_bar.addMenu("&Playback")

        play_action = QAction("Play/Pause", self)
        play_action.triggered.connect(self._playback_bridge.toggle_play_pause)
        playback_menu.addAction(play_action)
        # Space shortcut via QShortcut (not menu) — ApplicationShortcut but only
        # fires when no text input widget has focus (checked in _on_play_pause)
        self._play_shortcut = QShortcut(QKeySequence("Space"), self)
        self._play_shortcut.activated.connect(self._on_play_pause_shortcut)

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

        shortcuts_action = QAction("Keyboard &Shortcuts", self)
        shortcuts_action.triggered.connect(self._show_shortcuts_dialog)
        help_menu.addAction(shortcuts_action)
        # ? shortcut via QShortcut — only fires when no text input has focus
        self._shortcuts_shortcut = QShortcut(QKeySequence("?"), self)
        self._shortcuts_shortcut.activated.connect(self._on_shortcuts_shortcut)

        help_menu.addSeparator()

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
        # Reuse the track list already built by DatabasePanel (avoids double iter_songs)
        tracks = self.database_panel.tracks or list(database.iter_songs())
        track_count = len(tracks)
        self.statusBar().showMessage(f"Loaded database with {track_count} tracks")

        # Update all panels with database
        self.normalization_panel.set_database(database, tracks)
        for panel in (self.files_panel, self.analysis_panel, self.export_panel):
            if hasattr(panel, "set_database"):
                panel.set_database(database)
        self.workflow_panel.set_database(database, tracks)

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
    def _on_play_next_requested(self, songs) -> None:
        """Insert songs after current position in queue (reversed to preserve order)."""
        for song in reversed(songs):
            self._playback_bridge.insert_next(TrackInfo.from_song(song))

    @Slot(object)
    def _on_add_to_queue_requested(self, songs) -> None:
        """Append songs to end of queue."""
        for song in songs:
            self._playback_bridge.add_to_queue(TrackInfo.from_song(song))

    @Slot(list)
    def _on_tracks_dropped(self, file_paths: list) -> None:
        """Handle tracks dropped onto the player panel — add to queue."""
        if not self._database:
            return
        for fp in file_paths:
            song = self._database.get_song(fp)
            if song:
                self._playback_bridge.add_to_queue(TrackInfo.from_song(song))

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

    @Slot(str, list)
    def _on_cues_changed(self, file_path: str, cue_list: list) -> None:
        """Persist cue point changes to database."""
        if not self._database:
            return
        self._database.update_song_pois(file_path, cue_list)
        self._schedule_save()

    @Slot()
    def _on_workflow_database_changed(self) -> None:
        """Refresh panels after workflow operations modify the database."""
        if not self._database:
            return
        tracks = list(self._database.iter_songs())
        self.database_panel.refresh_tracks(tracks)
        self.normalization_panel.set_database(self._database, tracks)
        self.analysis_panel.set_database(self._database)
        self.statusBar().showMessage(f"Workflow complete — {len(tracks)} tracks")

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
                logger.error("Failed to save database", exc_info=True)
                self.statusBar().showMessage("Failed to save database!", 10000)

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
