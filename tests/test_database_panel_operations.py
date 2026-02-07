"""Tests for DatabasePanel operations: backup, validate, clean."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from vdj_manager.ui.widgets.database_panel import DatabasePanel
from vdj_manager.ui.workers.database_worker import BackupWorker


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
