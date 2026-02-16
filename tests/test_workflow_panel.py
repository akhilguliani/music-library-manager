"""Tests for WorkflowPanel — unified parallel workflow launcher."""

import gc
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QCoreApplication

from vdj_manager.core.models import Song, Tags, Infos
from vdj_manager.ui.widgets.workflow_panel import WorkflowPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_song(name: str, energy=None, ext=".mp3", is_windows=False) -> Song:
    """Create a mock Song for testing."""
    prefix = "D:\\Music" if is_windows else "/music"
    sep = "\\" if is_windows else "/"
    fp = f"{prefix}{sep}{name}{ext}"
    return Song(
        file_path=fp,
        file_size=1000,
        tags=Tags(title=name, author="Artist"),
        infos=Infos(song_length=200.0),
    )


class TestWorkflowPanelCreation:
    """Tests for panel initialization."""

    def test_panel_has_checkboxes(self, qapp):
        """Panel should have energy, mood, and normalization checkboxes."""
        panel = WorkflowPanel()
        assert hasattr(panel, "energy_check")
        assert hasattr(panel, "mood_check")
        assert hasattr(panel, "norm_check")

    def test_panel_has_controls(self, qapp):
        """Panel should have run and cancel buttons."""
        panel = WorkflowPanel()
        assert hasattr(panel, "run_btn")
        assert hasattr(panel, "cancel_btn")
        assert not panel.run_btn.isEnabled()  # No database yet

    def test_set_database_enables_run(self, qapp):
        """set_database with valid data enables the run button."""
        panel = WorkflowPanel()
        db = MagicMock()
        tracks = [_make_song("A"), _make_song("B")]
        panel.set_database(db, tracks)
        assert panel.run_btn.isEnabled()

    def test_set_database_none_disables_run(self, qapp):
        """set_database(None) disables the run button."""
        panel = WorkflowPanel()
        panel.set_database(None)
        assert not panel.run_btn.isEnabled()


class TestWorkflowPanelRunLogic:
    """Tests for run/cancel logic."""

    def test_run_no_selection_warns(self, qapp):
        """Running with no checkboxes checked shows a warning."""
        panel = WorkflowPanel()
        db = MagicMock()
        tracks = [_make_song("A")]
        panel.set_database(db, tracks)

        panel.energy_check.setChecked(False)
        panel.mood_check.setChecked(False)
        panel.norm_check.setChecked(False)

        with patch.object(QMessageBox, "warning") as mock_warn:
            panel._on_run_clicked()
            mock_warn.assert_called_once()

    @patch("vdj_manager.ui.widgets.workflow_panel.EnergyWorker")
    @patch("vdj_manager.core.backup.BackupManager")
    def test_run_energy_only(self, MockBackup, MockEnergyWorker, qapp):
        """Running with only energy checked creates an EnergyWorker."""
        panel = WorkflowPanel()
        db = MagicMock()
        db.db_path = Path("/tmp/test.xml")
        tracks = [_make_song("A")]
        panel.set_database(db, tracks)

        panel.energy_check.setChecked(True)
        panel.mood_check.setChecked(False)
        panel.norm_check.setChecked(False)

        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = False
        MockEnergyWorker.return_value = mock_worker

        with patch.object(Path, "exists", return_value=True):
            panel._on_run_clicked()

        MockEnergyWorker.assert_called_once()
        mock_worker.start.assert_called_once()

    @patch("vdj_manager.ui.widgets.workflow_panel.MoodWorker")
    @patch("vdj_manager.ui.widgets.workflow_panel.EnergyWorker")
    @patch("vdj_manager.core.backup.BackupManager")
    def test_run_energy_and_mood_parallel(self, MockBackup, MockEnergyWorker, MockMoodWorker, qapp):
        """Running energy + mood creates both workers."""
        panel = WorkflowPanel()
        db = MagicMock()
        db.db_path = Path("/tmp/test.xml")
        tracks = [_make_song("A")]
        panel.set_database(db, tracks)

        panel.energy_check.setChecked(True)
        panel.mood_check.setChecked(True)
        panel.norm_check.setChecked(False)

        mock_energy = MagicMock()
        mock_energy.isRunning.return_value = False
        MockEnergyWorker.return_value = mock_energy

        mock_mood = MagicMock()
        mock_mood.isRunning.return_value = False
        MockMoodWorker.return_value = mock_mood

        with patch.object(Path, "exists", return_value=True):
            panel._on_run_clicked()

        MockEnergyWorker.assert_called_once()
        MockMoodWorker.assert_called_once()
        mock_energy.start.assert_called_once()
        mock_mood.start.assert_called_once()

    @patch("vdj_manager.core.backup.BackupManager")
    def test_auto_backup_called_once(self, MockBackup, qapp):
        """Auto-backup should be called exactly once regardless of how many operations."""
        panel = WorkflowPanel()
        db = MagicMock()
        db.db_path = Path("/tmp/test.xml")
        tracks = [_make_song("A")]
        panel.set_database(db, tracks)

        panel.energy_check.setChecked(True)
        panel.mood_check.setChecked(True)
        panel.norm_check.setChecked(False)

        mock_backup = MagicMock()
        MockBackup.return_value = mock_backup

        with patch("vdj_manager.ui.widgets.workflow_panel.EnergyWorker") as ME, \
             patch("vdj_manager.ui.widgets.workflow_panel.MoodWorker") as MM, \
             patch.object(Path, "exists", return_value=True):
            me = MagicMock()
            me.isRunning.return_value = False
            ME.return_value = me
            mm = MagicMock()
            mm.isRunning.return_value = False
            MM.return_value = mm
            panel._on_run_clicked()

        mock_backup.create_backup.assert_called_once()

    def test_apply_result_to_db(self, qapp):
        """_apply_result_to_db updates database tags."""
        panel = WorkflowPanel()
        db = MagicMock()
        panel._database = db

        result = {
            "file_path": "/music/A.mp3",
            "tag_updates": {"Grouping": "7"},
        }
        panel._apply_result_to_db(result)

        db.update_song_tags.assert_called_once_with("/music/A.mp3", Grouping="7")
        assert panel._unsaved_count == 1

    def test_db_saved_when_last_worker_finishes(self, qapp):
        """Database is saved when the last worker finishes."""
        panel = WorkflowPanel()
        db = MagicMock()
        panel._database = db
        panel._unsaved_count = 5
        panel._workers_running = 2

        panel._on_energy_finished({})
        db.save.assert_not_called()  # one worker still running

        panel._on_mood_finished({})
        db.save.assert_called_once()
        assert panel._unsaved_count == 0

    def test_cancel_all_stops_running_workers(self, qapp):
        """Cancel all should call cancel() on running workers."""
        panel = WorkflowPanel()

        mock_energy = MagicMock()
        mock_energy.isRunning.return_value = True
        panel._energy_worker = mock_energy

        mock_mood = MagicMock()
        mock_mood.isRunning.return_value = True
        panel._mood_worker = mock_mood

        panel._on_cancel_all_clicked()

        mock_energy.cancel.assert_called_once()
        mock_mood.cancel.assert_called_once()

    def test_panel_has_progress_widgets(self, qapp):
        """Panel should have separate progress widgets for each operation."""
        panel = WorkflowPanel()
        assert hasattr(panel, "energy_progress")
        assert hasattr(panel, "mood_progress")
        assert hasattr(panel, "norm_progress")

    @patch("vdj_manager.core.backup.BackupManager")
    def test_run_no_eligible_tracks_resets_ui(self, MockBackup, qapp):
        """When all checked ops have 0 eligible tracks, UI should reset (not get stuck)."""
        panel = WorkflowPanel()
        db = MagicMock()
        db.db_path = Path("/tmp/test.xml")
        # Non-audio extension — not eligible for any analysis
        tracks = [_make_song("A", ext=".txt")]
        panel.set_database(db, tracks)

        panel.energy_check.setChecked(True)
        panel.mood_check.setChecked(False)
        panel.norm_check.setChecked(False)

        panel._on_run_clicked()

        # Run button should be re-enabled, not stuck disabled
        assert panel.run_btn.isEnabled()
        assert not panel.cancel_btn.isEnabled()
        assert "No eligible" in panel.status_label.text()

    def test_save_failure_shows_error_status(self, qapp):
        """_save_if_needed should catch OSError and update status label."""
        panel = WorkflowPanel()
        db = MagicMock()
        db.save.side_effect = OSError("disk full")
        panel._database = db
        panel._unsaved_count = 5

        panel._save_if_needed()

        assert "Failed to save" in panel.status_label.text()

    def test_energy_finished_with_failures_shows_status(self, qapp):
        """Progress should show failure count when energy analysis has failures."""
        panel = WorkflowPanel()
        panel._workers_running = 1
        panel._database = MagicMock()
        panel._unsaved_count = 0

        panel._on_energy_finished({"analyzed": 5, "failed": 2, "results": []})

        assert panel._workers_running == 0
