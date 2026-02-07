"""Main window for VDJ Manager Desktop Application."""

from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QLabel,
    QStatusBar,
    QMenuBar,
    QMenu,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence

from vdj_manager.ui.widgets.database_panel import DatabasePanel
from vdj_manager.ui.widgets.files_panel import FilesPanel
from vdj_manager.ui.widgets.normalization_panel import NormalizationPanel


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the main window.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self.setWindowTitle("VDJ Manager")
        self.setMinimumSize(900, 600)

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_status_bar()

    def _setup_ui(self) -> None:
        """Set up the main UI layout with tabs."""
        # Create the central tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setDocumentMode(True)
        self.setCentralWidget(self.tab_widget)

        # Create tabs: Database(0), Normalization(1), Files(2), Analysis(3), Export(4)
        self._create_database_tab()
        self._create_normalization_tab()
        self._create_files_tab()
        self._create_analysis_tab()
        self._create_export_tab()

    def _create_database_tab(self) -> None:
        """Create the database overview tab."""
        self.database_panel = DatabasePanel()
        self.database_panel.database_loaded.connect(self._on_database_loaded)
        self.database_panel.track_selected.connect(self._on_track_selected)

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
        # Placeholder - will be replaced with AnalysisPanel
        self.analysis_panel = QWidget()
        layout = QVBoxLayout(self.analysis_panel)

        label = QLabel("Analysis")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        info_label = QLabel(
            "Analyze audio features and import external tags.\n\n"
            "Features:\n"
            "- Energy level analysis (1-10)\n"
            "- Mood classification\n"
            "- Import Mixed In Key tags"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        layout.addStretch()

        self.tab_widget.addTab(self.analysis_panel, "Analysis")

    def _create_export_tab(self) -> None:
        """Create the export tab."""
        # Placeholder - will be replaced with ExportPanel
        self.export_panel = QWidget()
        layout = QVBoxLayout(self.export_panel)

        label = QLabel("Export")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        info_label = QLabel(
            "Export your library to other DJ software.\n\n"
            "Features:\n"
            "- Export to Serato format\n"
            "- Crate/playlist management"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        layout.addStretch()

        self.tab_widget.addTab(self.export_panel, "Export")

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

        database_tab_action = QAction("&Database", self)
        database_tab_action.setShortcut(QKeySequence("Ctrl+1"))
        database_tab_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(0))
        view_menu.addAction(database_tab_action)

        normalize_tab_action = QAction("&Normalization", self)
        normalize_tab_action.setShortcut(QKeySequence("Ctrl+2"))
        normalize_tab_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(1))
        view_menu.addAction(normalize_tab_action)

        files_tab_action = QAction("&Files", self)
        files_tab_action.setShortcut(QKeySequence("Ctrl+3"))
        files_tab_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(2))
        view_menu.addAction(files_tab_action)

        analysis_tab_action = QAction("&Analysis", self)
        analysis_tab_action.setShortcut(QKeySequence("Ctrl+4"))
        analysis_tab_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(3))
        view_menu.addAction(analysis_tab_action)

        export_tab_action = QAction("&Export", self)
        export_tab_action.setShortcut(QKeySequence("Ctrl+5"))
        export_tab_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(4))
        view_menu.addAction(export_tab_action)

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
        # Will be implemented with file dialog
        self.statusBar().showMessage("Open database not yet implemented")

    @Slot(object)
    def _on_database_loaded(self, database) -> None:
        """Handle database loaded event."""
        tracks = list(database.iter_songs())
        track_count = len(tracks)
        self.statusBar().showMessage(f"Loaded database with {track_count} tracks")

        # Update all panels with database
        self.normalization_panel.set_database(database, tracks)
        # Files, Analysis, Export panels will get set_database when they're real panels
        for panel in (self.files_panel, self.analysis_panel, self.export_panel):
            if hasattr(panel, "set_database"):
                panel.set_database(database)

    @Slot(object)
    def _on_track_selected(self, track) -> None:
        """Handle track selection event."""
        self.statusBar().showMessage(f"Selected: {track.display_name}")

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
            "- Audio loudness normalization\n"
            "- Energy and mood analysis\n"
            "- Library organization\n\n"
            "Version 0.1.0",
        )
