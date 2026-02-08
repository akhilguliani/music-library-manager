"""Tests for DatabasePanel operations: backup, validate, clean."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QCoreApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.widgets.database_panel import DatabasePanel
from vdj_manager.ui.workers.database_worker import BackupWorker, ValidateWorker, CleanWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestDatabasePanelButtons:
    """Tests for database panel action buttons."""

    def test_backup_button_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.backup_btn is not None
        assert panel.backup_btn.text() == "Backup"

    def test_validate_button_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.validate_btn is not None
        assert panel.validate_btn.text() == "Validate"

    def test_clean_button_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.clean_btn is not None
        assert panel.clean_btn.text() == "Clean"

    def test_buttons_disabled_without_database(self, qapp):
        panel = DatabasePanel()
        assert not panel.backup_btn.isEnabled()
        assert not panel.validate_btn.isEnabled()
        assert not panel.clean_btn.isEnabled()

    def test_backup_no_database_does_nothing(self, qapp):
        panel = DatabasePanel()
        panel._on_backup_clicked()
        # Should not crash, should not create a worker
        assert panel._backup_worker is None


class TestBackupWorker:
    """Tests for BackupWorker."""

    def test_backup_worker_success(self, qapp):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            f.write(b"<VirtualDJ_Database></VirtualDJ_Database>")
            db_path = Path(f.name)

        try:
            with tempfile.TemporaryDirectory() as backup_dir:
                with patch("vdj_manager.core.backup.BACKUP_DIR", Path(backup_dir)):
                    worker = BackupWorker(db_path)
                    results = []
                    worker.finished_work.connect(lambda r: results.append(r))
                    worker.start()
                    worker.wait(5000)
                    QCoreApplication.processEvents()

                    assert len(results) == 1
                    assert Path(results[0]).exists()
                    assert Path(results[0]).suffix == ".xml"
        finally:
            db_path.unlink(missing_ok=True)

    def test_backup_worker_missing_file(self, qapp):
        worker = BackupWorker(Path("/nonexistent/database.xml"))
        errors = []
        worker.error.connect(lambda e: errors.append(e))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(errors) == 1
        assert "not found" in errors[0]


class TestDatabasePanelBackup:
    """Tests for backup operation in DatabasePanel."""

    def test_on_backup_finished(self, qapp):
        panel = DatabasePanel()
        panel._on_backup_finished(Path("/backups/database_local_20260101_120000.xml"))

        assert panel.backup_btn.isEnabled()
        assert "Backup created" in panel.status_label.text()
        assert "database_local_20260101_120000.xml" in panel.status_label.text()

    def test_on_backup_error(self, qapp):
        panel = DatabasePanel()
        panel._on_backup_error("File not found")

        assert panel.backup_btn.isEnabled()
        assert "Backup failed" in panel.status_label.text()
        assert "File not found" in panel.status_label.text()


def _make_song(path: str, is_netsearch: bool = False) -> Song:
    """Helper to create a Song for testing."""
    return Song(file_path=path, tags=Tags(author="Artist", title="Title"))


class TestValidateWorker:
    """Tests for ValidateWorker."""

    def test_validate_worker_runs(self, qapp):
        tracks = [_make_song("/music/song.mp3")]
        worker = ValidateWorker(tracks)
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        report = results[0]
        assert "total" in report
        assert report["total"] == 1

    def test_validate_worker_counts_categories(self, qapp):
        tracks = [
            _make_song("/music/song.mp3"),
            _make_song("/music/video.mp4"),
        ]
        worker = ValidateWorker(tracks)
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        report = results[0]
        assert report["total"] == 2
        assert report["non_audio"] >= 1  # mp4 is non-audio


class TestDatabasePanelValidate:
    """Tests for validation in DatabasePanel."""

    def test_on_validate_finished_shows_summary(self, qapp):
        panel = DatabasePanel()
        report = {
            "total": 100,
            "audio_valid": 90,
            "audio_missing": 5,
            "non_audio": 3,
            "windows_paths": 2,
            "netsearch": 0,
            "unknown": 0,
        }

        with patch.object(QMessageBox, "information"):
            panel._on_validate_finished(report)

        assert panel.validate_btn.isEnabled()
        assert "90 valid" in panel.status_label.text()
        assert "5 missing" in panel.status_label.text()

    def test_on_validate_finished_green_when_no_missing(self, qapp):
        panel = DatabasePanel()
        report = {
            "total": 100,
            "audio_valid": 100,
            "audio_missing": 0,
            "non_audio": 0,
            "windows_paths": 0,
            "netsearch": 0,
        }

        with patch.object(QMessageBox, "information"):
            panel._on_validate_finished(report)

        assert "green" in panel.status_label.styleSheet()

    def test_on_validate_error(self, qapp):
        panel = DatabasePanel()
        panel._on_validate_error("Something went wrong")

        assert panel.validate_btn.isEnabled()
        assert "Validation failed" in panel.status_label.text()

    def test_validate_no_tracks_does_nothing(self, qapp):
        panel = DatabasePanel()
        panel._on_validate_clicked()
        assert panel._validate_worker is None


class TestDatabasePanelClean:
    """Tests for clean operation in DatabasePanel."""

    def test_clean_nothing_to_clean(self, qapp):
        panel = DatabasePanel()
        panel._database = MagicMock()
        panel._tracks = [_make_song("/existing/song.mp3")]

        with patch("vdj_manager.files.validator.FileValidator.categorize_entries") as mock_cat:
            mock_cat.return_value = {
                "non_audio": [],
                "audio_missing": [],
                "audio_exists": [_make_song("/existing/song.mp3")],
                "windows_paths": [],
                "netsearch": [],
                "unknown": [],
            }
            with patch.object(QMessageBox, "information") as mock_info:
                panel._on_clean_clicked()
                mock_info.assert_called_once()

    def test_on_clean_finished(self, qapp):
        panel = DatabasePanel()
        panel._database = MagicMock()
        panel._database.iter_songs.return_value = iter([])
        panel._database.get_stats.return_value = None

        panel._on_clean_finished(5)

        assert panel.clean_btn.isEnabled()
        assert "Cleaned 5" in panel.status_label.text()

    def test_on_clean_error(self, qapp):
        panel = DatabasePanel()
        panel._on_clean_error("Remove failed")

        assert panel.clean_btn.isEnabled()
        assert "Clean failed" in panel.status_label.text()


class TestDatabasePanelTagEditing:
    """Tests for tag editing in DatabasePanel."""

    def test_tag_edit_group_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.tag_energy_spin is not None
        assert panel.tag_key_input is not None
        assert panel.tag_comment_input is not None
        assert panel.tag_save_btn is not None

    def test_tag_save_disabled_initially(self, qapp):
        panel = DatabasePanel()
        assert not panel.tag_save_btn.isEnabled()

    def test_populate_tag_fields(self, qapp):
        panel = DatabasePanel()
        track = Song(
            file_path="/music/test.mp3",
            tags=Tags(author="Artist", title="Title", grouping="Energy 7", key="Am", comment="Mood: happy"),
        )
        panel._populate_tag_fields(track)

        assert panel.tag_energy_spin.value() == 7
        assert panel.tag_key_input.text() == "Am"
        assert panel.tag_comment_input.text() == "Mood: happy"
        assert panel.tag_save_btn.isEnabled()
        assert "Artist - Title" in panel.tag_track_label.text()

    def test_populate_tag_fields_no_tags(self, qapp):
        panel = DatabasePanel()
        track = Song(file_path="/music/test.mp3", tags=Tags())
        panel._populate_tag_fields(track)

        assert panel.tag_energy_spin.value() == 0  # "None"
        assert panel.tag_key_input.text() == ""
        assert panel.tag_comment_input.text() == ""

    def test_tag_save_updates_database(self, qapp):
        panel = DatabasePanel()
        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([])
        panel._database = mock_db

        track = Song(file_path="/music/test.mp3", tags=Tags())
        panel._populate_tag_fields(track)
        panel.tag_energy_spin.setValue(5)
        panel.tag_key_input.setText("Cm")
        panel.tag_comment_input.setText("energetic")

        panel._on_tag_save_clicked()

        mock_db.update_song_tags.assert_called_once_with(
            "/music/test.mp3",
            Grouping="Energy 5",
            Key="Cm",
            Comment="energetic",
        )
        mock_db.save.assert_called_once()
        assert "Tags saved" in panel.status_label.text()

    def test_tag_save_clears_energy(self, qapp):
        panel = DatabasePanel()
        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([])
        panel._database = mock_db

        track = Song(
            file_path="/music/test.mp3",
            tags=Tags(grouping="Energy 7"),
        )
        panel._populate_tag_fields(track)
        panel.tag_energy_spin.setValue(0)  # Clear energy

        panel._on_tag_save_clicked()

        call_kwargs = mock_db.update_song_tags.call_args
        assert call_kwargs[1]["Grouping"] is None

    def test_tag_save_no_database_does_nothing(self, qapp):
        panel = DatabasePanel()
        panel._on_tag_save_clicked()
        # Should not crash


class TestDatabasePanelOperationLog:
    """Tests for operation log."""

    def test_operation_log_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.operation_log is not None

    def test_log_operation_adds_entry(self, qapp):
        panel = DatabasePanel()
        panel._log_operation("Test operation")
        assert panel.operation_log.count() == 1
        assert "Test operation" in panel.operation_log.item(0).text()

    def test_log_operation_prepends(self, qapp):
        panel = DatabasePanel()
        panel._log_operation("First")
        panel._log_operation("Second")
        assert panel.operation_log.count() == 2
        assert "Second" in panel.operation_log.item(0).text()
        assert "First" in panel.operation_log.item(1).text()

    def test_log_operation_max_20(self, qapp):
        panel = DatabasePanel()
        for i in range(25):
            panel._log_operation(f"Operation {i}")
        assert panel.operation_log.count() == 20

    def test_backup_logs_operation(self, qapp):
        panel = DatabasePanel()
        panel._on_backup_finished(Path("/backups/db_backup.xml"))
        assert panel.operation_log.count() == 1
        assert "Backup" in panel.operation_log.item(0).text()

    def test_clean_logs_operation(self, qapp):
        panel = DatabasePanel()
        panel._database = MagicMock()
        panel._database.iter_songs.return_value = iter([])
        panel._database.get_stats.return_value = None
        panel._on_clean_finished(5)
        assert panel.operation_log.count() == 1
        assert "Cleaned 5" in panel.operation_log.item(0).text()

    def test_validate_logs_operation(self, qapp):
        panel = DatabasePanel()
        report = {
            "total": 10, "audio_valid": 8, "audio_missing": 2,
            "non_audio": 0, "windows_paths": 0, "netsearch": 0,
        }
        with patch.object(QMessageBox, "information"):
            panel._on_validate_finished(report)
        assert panel.operation_log.count() == 1
        assert "Validation" in panel.operation_log.item(0).text()
