"""Tests for normalization panel."""

import pytest
from unittest.mock import MagicMock, patch

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.widgets.normalization_panel import NormalizationPanel
from vdj_manager.ui.widgets.results_table import ResultsTable


@pytest.fixture(scope="module")
def app():
    """Create a QApplication for testing."""
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        app = QApplication(["test"])
        yield app


@pytest.fixture
def sample_tracks():
    """Create sample tracks for testing."""
    return [
        Song(
            file_path="/path/to/track1.mp3",
            tags=Tags(title="Track 1"),
        ),
        Song(
            file_path="/path/to/track2.m4a",
            tags=Tags(title="Track 2"),
        ),
        Song(
            file_path="netsearch://spotify/track",
            tags=Tags(title="Streaming Track"),
        ),
        Song(
            file_path="D:/Windows/track.mp3",  # Windows path
            tags=Tags(title="Windows Track"),
        ),
    ]


class TestResultsTable:
    """Tests for ResultsTable widget."""

    def test_table_creation(self, app):
        """Test table can be created."""
        table = ResultsTable()
        assert table is not None
        assert table.row_count() == 0

    def test_add_successful_result(self, app):
        """Test adding a successful result."""
        table = ResultsTable()

        table.add_result(
            "/path/to/track.mp3",
            {"success": True, "current_lufs": -12.5, "gain_db": -1.5},
        )

        assert table.row_count() == 1

        results = table.get_all_results()
        assert len(results) == 1
        assert results[0]["file"] == "track.mp3"
        assert "-12.5" in results[0]["lufs"]
        assert results[0]["status"] == "OK"

    def test_add_failed_result(self, app):
        """Test adding a failed result."""
        table = ResultsTable()

        table.add_result(
            "/path/to/failed.mp3",
            {"success": False, "error": "File not found"},
        )

        assert table.row_count() == 1

        results = table.get_all_results()
        assert results[0]["status"] == "FAIL"

    def test_clear(self, app):
        """Test clearing results."""
        table = ResultsTable()

        table.add_result("/path/to/track1.mp3", {"success": True, "lufs": -14.0})
        table.add_result("/path/to/track2.mp3", {"success": True, "lufs": -13.0})

        assert table.row_count() == 2

        table.clear()
        assert table.row_count() == 0

    def test_multiple_results(self, app):
        """Test adding multiple results."""
        table = ResultsTable()

        for i in range(5):
            table.add_result(
                f"/path/to/track{i}.mp3",
                {"success": True, "current_lufs": -14.0 + i, "gain_db": float(i)},
            )

        assert table.row_count() == 5


class TestNormalizationPanel:
    """Tests for NormalizationPanel widget."""

    def test_panel_creation(self, app):
        """Test panel can be created."""
        panel = NormalizationPanel()
        assert panel is not None
        assert panel.progress_widget is not None
        assert panel.results_table is not None

    def test_initial_state(self, app):
        """Test panel initial state."""
        panel = NormalizationPanel()

        assert panel.database is None
        assert not panel.start_btn.isEnabled()
        assert "No database" in panel.track_count_label.text()

    def test_set_database_with_tracks(self, app, sample_tracks):
        """Test setting database with tracks."""
        panel = NormalizationPanel()

        mock_db = MagicMock()
        panel.set_database(mock_db, sample_tracks)

        assert panel.database is mock_db
        # Count includes audio files (not streaming), Windows paths counted
        assert "audio files" in panel.track_count_label.text()
        assert panel.start_btn.isEnabled()

    def test_set_database_no_tracks(self, app):
        """Test setting database with no tracks."""
        panel = NormalizationPanel()

        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([])

        panel.set_database(mock_db)

        assert not panel.start_btn.isEnabled()

    def test_lufs_spinner(self, app):
        """Test LUFS spinner configuration."""
        panel = NormalizationPanel()

        assert panel.lufs_spin.value() == -14.0
        assert panel.lufs_spin.minimum() == -30.0
        assert panel.lufs_spin.maximum() == 0.0

        panel.lufs_spin.setValue(-16.0)
        assert panel.lufs_spin.value() == -16.0

    def test_batch_spinner(self, app):
        """Test batch size spinner configuration."""
        panel = NormalizationPanel()

        assert panel.batch_spin.value() == 50
        assert panel.batch_spin.minimum() == 10
        assert panel.batch_spin.maximum() == 500

    def test_workers_spinner(self, app):
        """Test parallel workers spinner configuration."""
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()

        panel = NormalizationPanel()

        # Default should be CPU count - 1 (at least 1)
        expected_default = max(1, cpu_count - 1)
        assert panel.workers_spin.value() == expected_default
        assert panel.workers_spin.minimum() == 1
        assert panel.workers_spin.maximum() == 20

        # Test setting custom value
        panel.workers_spin.setValue(2)
        assert panel.workers_spin.value() == 2

    def test_is_running(self, app):
        """Test is_running property."""
        panel = NormalizationPanel()

        assert not panel.is_running()

    def test_get_audio_paths_filters_correctly(self, app, sample_tracks):
        """Test that _get_audio_paths filters correctly."""
        panel = NormalizationPanel()

        mock_db = MagicMock()
        panel.set_database(mock_db, sample_tracks)

        paths = panel._get_audio_paths()

        # Should only include valid local audio files
        assert len(paths) == 2
        assert "/path/to/track1.mp3" in paths
        assert "/path/to/track2.m4a" in paths
        # Should not include streaming or Windows paths
        assert not any("netsearch" in p for p in paths)
        assert not any("D:/" in p for p in paths)


class TestNormalizationPanelIntegration:
    """Integration tests for NormalizationPanel."""

    def test_panel_widgets_connected(self, app):
        """Test that panel widgets are properly connected."""
        panel = NormalizationPanel()

        # Verify progress widget exists
        assert panel.progress_widget is not None

        # Verify results table exists
        assert panel.results_table is not None

        # Verify controls exist
        assert panel.lufs_spin is not None
        assert panel.batch_spin is not None
        assert panel.start_btn is not None
