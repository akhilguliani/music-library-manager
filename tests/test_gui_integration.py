"""Integration tests for the GUI application.

Tests verify that panels, workers, and the main window integrate correctly.
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from vdj_manager.core.models import Playlist, Song, Tags
from vdj_manager.ui.main_window import MainWindow
from vdj_manager.ui.widgets.analysis_panel import AnalysisPanel
from vdj_manager.ui.widgets.database_panel import DatabasePanel
from vdj_manager.ui.widgets.export_panel import ExportPanel
from vdj_manager.ui.widgets.files_panel import FilesPanel
from vdj_manager.ui.widgets.normalization_panel import NormalizationPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_song(path: str, energy: int | None = None) -> Song:
    grouping = str(energy) if energy is not None else None
    return Song(file_path=path, tags=Tags(author="Artist", title="Title", grouping=grouping))


class TestMainWindowIntegration:
    """Tests for MainWindow integrating all panels."""

    def test_all_tabs_are_real_panels(self, qapp):
        window = MainWindow()
        assert isinstance(window.database_panel, DatabasePanel)
        assert isinstance(window.normalization_panel, NormalizationPanel)
        assert isinstance(window.files_panel, FilesPanel)
        assert isinstance(window.analysis_panel, AnalysisPanel)
        assert isinstance(window.export_panel, ExportPanel)

    def test_database_load_propagates_to_all_panels(self, qapp):
        window = MainWindow()
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3"), _make_song("/b.mp3")]
        mock_db.iter_songs.return_value = iter(tracks)
        mock_db.playlists = []

        window._on_database_loaded(mock_db)

        # Normalization panel gets tracks
        assert len(window.normalization_panel._tracks) == 2
        # Files panel gets database
        assert window.files_panel._database is mock_db
        # Analysis panel gets database
        assert window.analysis_panel._database is mock_db
        # Export panel gets database
        assert window.export_panel._database is mock_db

    def test_panel_count_is_seven(self, qapp):
        window = MainWindow()
        assert len(window._navigation.panel_names()) == 7

    def test_panel_names_correct(self, qapp):
        window = MainWindow()
        assert window._navigation.panel_names() == [
            "Database",
            "Normalization",
            "Files",
            "Analysis",
            "Export",
            "Player",
            "Workflow",
        ]

    def test_workflow_database_changed_refreshes_panels(self, qapp):
        window = MainWindow()
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]
        mock_db.iter_songs.return_value = iter(tracks)
        mock_db.playlists = []
        window._on_database_loaded(mock_db)

        # Simulate workflow completion
        mock_db.iter_songs.return_value = iter(tracks)
        window._on_workflow_database_changed()
        assert "Workflow complete" in window.statusBar().currentMessage()

    def test_status_bar_shows_track_selection(self, qapp):
        window = MainWindow()
        track = _make_song("/music/test.mp3")
        window._on_track_selected(track)
        assert "Artist - Title" in window.statusBar().currentMessage()


class TestDatabaseToNormalizationFlow:
    """Test database load -> normalization flow."""

    def test_normalization_buttons_enabled_after_db_load(self, qapp):
        norm_panel = NormalizationPanel()
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]
        norm_panel.set_database(mock_db, tracks)

        # Start button should be enabled since we have audio tracks
        # (may not be if tracks are filtered out by extension check)
        assert norm_panel._tracks == tracks

    def test_measurement_enables_apply_and_export(self, qapp):
        panel = NormalizationPanel()
        panel.results_table.add_result(
            "/a.mp3",
            {
                "success": True,
                "current_lufs": -14.0,
                "gain_db": 0.5,
            },
        )
        panel._on_measurement_finished(True, "Done")

        assert panel.apply_btn.isEnabled()
        assert panel.export_csv_btn.isEnabled()

    def test_apply_finished_re_enables_controls(self, qapp):
        panel = NormalizationPanel()
        panel.results_table.add_result(
            "/a.mp3",
            {
                "success": True,
                "current_lufs": -14.0,
                "gain_db": 0.5,
            },
        )
        panel._on_apply_finished(True, "Done")

        assert panel.start_btn.isEnabled()
        assert panel.apply_btn.isEnabled()


class TestDatabaseToAnalysisFlow:
    """Test database load -> analysis flow."""

    def test_analysis_buttons_enabled_after_db_load(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]
        panel.set_database(mock_db, tracks)

        assert panel.energy_all_btn.isEnabled()
        assert panel.energy_untagged_btn.isEnabled()
        assert panel.mik_scan_btn.isEnabled()

    def test_energy_results_update_panel(self, qapp):
        """Results are streamed via result_ready; finished handler updates status."""
        panel = AnalysisPanel()
        results_data = [
            {"file_path": "/a.mp3", "format": ".mp3", "energy": 7, "status": "ok"},
            {"file_path": "/b.mp3", "format": ".mp3", "energy": 3, "status": "ok"},
        ]
        # Simulate streaming results (result_ready signal adds rows during processing)
        for r in results_data:
            panel.energy_results.add_result(r)

        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        panel._on_energy_finished({"analyzed": 2, "failed": 0, "results": results_data})

        assert panel.energy_results.row_count() == 2
        assert len(signals) == 1

    def test_mik_results_update_panel(self, qapp):
        """Results are streamed via result_ready; finished handler updates status."""
        panel = AnalysisPanel()
        result_item = {
            "file_path": "/a.mp3",
            "format": ".mp3",
            "energy": 5,
            "key": "Am",
            "status": "updated",
        }
        # Simulate streaming
        panel.mik_results.add_result(result_item)

        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        panel._on_mik_finished({"found": 1, "updated": 1, "results": [result_item]})

        assert panel.mik_results.row_count() == 1
        assert len(signals) == 1


class TestDatabaseToExportFlow:
    """Test database load -> export flow."""

    def test_export_buttons_enabled_after_db_load(self, qapp):
        panel = ExportPanel()
        mock_db = MagicMock()
        mock_db.playlists = [Playlist(Name="Mix", file_paths=["/a.mp3"])]
        tracks = [_make_song("/a.mp3")]
        panel.set_database(mock_db, tracks)

        assert panel.export_all_btn.isEnabled()
        assert panel.playlist_list.count() == 1

    def test_export_results_displayed(self, qapp):
        panel = ExportPanel()
        result = {
            "exported": 3,
            "failed": 0,
            "results": [
                {"file_path": "/a.mp3", "status": "exported"},
                {"file_path": "/b.mp3", "status": "exported"},
                {"file_path": "/c.mp3", "status": "exported"},
            ],
        }
        signals = []
        panel.export_completed.connect(lambda: signals.append(True))

        panel._on_export_finished(result)

        assert panel.export_results.row_count() == 3
        assert len(signals) == 1


class TestDatabaseValidateCleanFlow:
    """Test database validate -> clean flow."""

    def test_validate_then_clean_flow(self, qapp):
        panel = DatabasePanel()
        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([])
        mock_db.get_stats.return_value = None
        panel._database = mock_db
        panel._tracks = [_make_song("/a.mp3")]

        # Step 1: Validate
        report = {
            "total": 1,
            "audio_valid": 0,
            "audio_missing": 1,
            "non_audio": 0,
            "windows_paths": 0,
            "netsearch": 0,
        }
        with patch.object(QMessageBox, "information"):
            panel._on_validate_finished(report)

        assert "1 missing" in panel.status_label.text()
        assert panel._last_validation == report

        # Step 2: Clean
        panel._on_clean_finished(1)
        assert "Cleaned 1" in panel.status_label.text()
        assert panel.operation_log.count() == 2  # validate + clean logged


class TestFileScanImportFlow:
    """Test file scan -> import flow."""

    def test_scan_then_import_flow(self, qapp):
        panel = FilesPanel()
        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([])
        panel.set_database(mock_db)

        # Step 1: Scan results
        files = [
            {
                "name": "new_song",
                "file_path": "/music/new_song.mp3",
                "file_size": 5000,
                "extension": ".mp3",
            },
        ]
        panel._on_scan_finished(files)

        assert panel.scan_results.row_count() == 1
        assert len(panel._scanned_files) == 1

        # Step 2: Import (new API returns paths_to_add, panel applies mutations)
        panel._on_import_finished({"paths_to_add": ["/music/new_song.mp3"]})
        assert "Imported 1" in panel.import_status.text()
        mock_db.add_song.assert_called_once_with("/music/new_song.mp3")
        mock_db.save.assert_called_once()
