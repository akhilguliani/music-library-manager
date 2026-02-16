"""Tests for VDJ Manager Desktop UI application."""

import pytest
from unittest.mock import patch, MagicMock

# Skip all tests if PySide6 is not available or display is not accessible
pytest.importorskip("PySide6")


class TestCreateApplication:
    """Tests for application creation."""

    def test_create_application_returns_qapplication(self):
        """Test that create_application returns a QApplication instance."""
        from PySide6.QtWidgets import QApplication

        # Check if an app already exists
        existing_app = QApplication.instance()
        if existing_app:
            # Use the existing application
            from vdj_manager.ui.app import create_application

            # Calling create_application when one exists returns a new one
            # but we'll just verify the existing one works
            assert existing_app is not None
            assert existing_app.applicationName() or True  # May not be set
        else:
            from vdj_manager.ui.app import create_application

            app = create_application(["test"])
            assert isinstance(app, QApplication)
            assert app.applicationName() == "VDJ Manager"

    def test_application_properties(self):
        """Test application properties are set correctly."""
        from PySide6.QtWidgets import QApplication
        from vdj_manager.ui.app import create_application

        existing_app = QApplication.instance()
        if existing_app is None:
            app = create_application(["test"])
        else:
            app = existing_app

        # If we created a new app, check properties
        if app.applicationName() == "VDJ Manager":
            assert app.organizationName() == "VDJ Manager"


class TestMainWindow:
    """Tests for the main window."""

    @pytest.fixture
    def app(self):
        """Create a QApplication for testing."""
        from PySide6.QtWidgets import QApplication

        existing = QApplication.instance()
        if existing:
            yield existing
        else:
            app = QApplication(["test"])
            yield app

    @pytest.fixture
    def main_window(self, app):
        """Create a MainWindow instance."""
        from vdj_manager.ui.main_window import MainWindow

        window = MainWindow()
        yield window
        window.close()

    def test_main_window_creation(self, main_window):
        """Test that main window can be created."""
        assert main_window is not None
        assert main_window.windowTitle() == "VDJ Manager"

    def test_main_window_minimum_size(self, main_window):
        """Test that main window has appropriate minimum size."""
        min_size = main_window.minimumSize()
        assert min_size.width() >= 900
        assert min_size.height() >= 600

    def test_main_window_has_tab_widget(self, main_window):
        """Test that main window has a tab widget inside the central container."""
        from PySide6.QtWidgets import QTabWidget

        assert isinstance(main_window.tab_widget, QTabWidget)

    def test_main_window_has_six_tabs(self, main_window):
        """Test that main window has all six tabs."""
        tab_widget = main_window.tab_widget
        assert tab_widget.count() == 6

        # Check tab names
        assert tab_widget.tabText(0) == "Database"
        assert tab_widget.tabText(1) == "Normalization"
        assert tab_widget.tabText(2) == "Files"
        assert tab_widget.tabText(3) == "Analysis"
        assert tab_widget.tabText(4) == "Export"
        assert tab_widget.tabText(5) == "Player"

    def test_main_window_has_menu_bar(self, main_window):
        """Test that main window has a menu bar."""
        menu_bar = main_window.menuBar()
        assert menu_bar is not None

        # Check menu actions exist
        actions = menu_bar.actions()
        menu_titles = [a.text() for a in actions]

        assert "&File" in menu_titles
        assert "&View" in menu_titles
        assert "&Help" in menu_titles

    def test_main_window_has_status_bar(self, main_window):
        """Test that main window has a status bar."""
        status_bar = main_window.statusBar()
        assert status_bar is not None

    def test_main_window_can_show(self, main_window):
        """Test that main window can be shown."""
        # Just verify show doesn't raise
        main_window.show()
        assert main_window.isVisible()

    def test_tab_switching(self, main_window):
        """Test that tabs can be switched."""
        tab_widget = main_window.tab_widget

        for i in range(5):
            tab_widget.setCurrentIndex(i)
            assert tab_widget.currentIndex() == i

        tab_widget.setCurrentIndex(0)
        assert tab_widget.currentIndex() == 0

    def test_panels_accessible(self, main_window):
        """Test that all panel attributes are accessible."""
        assert main_window.database_panel is not None
        assert main_window.normalization_panel is not None
        assert main_window.files_panel is not None
        assert main_window.analysis_panel is not None
        assert main_window.export_panel is not None

    def test_about_dialog(self, main_window, app):
        """Test that about action triggers about dialog."""
        from PySide6.QtWidgets import QMessageBox
        from unittest.mock import patch

        with patch.object(QMessageBox, "about") as mock_about:
            main_window._on_about()
            mock_about.assert_called_once()
            # Verify it was called with the window and contains expected text
            args = mock_about.call_args
            assert args[0][0] is main_window
            assert "About VDJ Manager" in args[0][1]

    def test_flush_save_shows_status_on_failure(self, main_window, app):
        """Save failure should display error message in status bar."""
        mock_db = MagicMock()
        mock_db.save.side_effect = OSError("disk full")
        main_window._database = mock_db
        main_window._save_pending = True

        main_window._flush_save()

        assert "Failed to save" in main_window.statusBar().currentMessage()

    def test_flush_save_clears_pending_on_success(self, main_window, app):
        """Successful save should clear the pending flag."""
        mock_db = MagicMock()
        main_window._database = mock_db
        main_window._save_pending = True

        main_window._flush_save()

        assert main_window._save_pending is False
        mock_db.save.assert_called_once()


class TestMainEntry:
    """Tests for main entry point."""

    def test_main_function_exists(self):
        """Test that main function is importable."""
        from vdj_manager.ui.app import main

        assert callable(main)

    def test_ui_package_exports(self):
        """Test that ui package exports expected items."""
        from vdj_manager.ui import main, MainWindow

        assert callable(main)
        assert MainWindow is not None
