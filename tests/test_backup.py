"""Tests for backup manager."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile
from datetime import datetime

from vdj_manager.core.backup import BackupManager


@pytest.fixture
def temp_backup_dir():
    """Create temporary backup directory."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_db_file():
    """Create a sample database file."""
    with NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write('<?xml version="1.0"?><VirtualDJ_Database></VirtualDJ_Database>')
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


class TestBackupManager:
    def test_create_backup(self, temp_backup_dir, sample_db_file):
        """Test creating a backup."""
        mgr = BackupManager(backup_dir=temp_backup_dir)
        backup_path = mgr.create_backup(sample_db_file)

        assert backup_path.exists()
        assert backup_path.suffix == ".xml"
        # Backup name contains the original file stem
        assert sample_db_file.stem in backup_path.name

    def test_create_backup_with_label(self, temp_backup_dir, sample_db_file):
        """Test creating backup with custom label."""
        mgr = BackupManager(backup_dir=temp_backup_dir)
        backup_path = mgr.create_backup(sample_db_file, label="test_label")

        assert "test_label" in backup_path.name

    def test_list_backups(self, temp_backup_dir, sample_db_file):
        """Test listing backups."""
        mgr = BackupManager(backup_dir=temp_backup_dir)

        # Create multiple backups
        mgr.create_backup(sample_db_file, label="first")
        mgr.create_backup(sample_db_file, label="second")
        mgr.create_backup(sample_db_file, label="third")

        backups = mgr.list_backups()
        assert len(backups) == 3

        # All backups should contain labels
        backup_names = [b.name for b in backups]
        assert any("first" in n for n in backup_names)
        assert any("second" in n for n in backup_names)
        assert any("third" in n for n in backup_names)

    def test_get_latest_backup(self, temp_backup_dir, sample_db_file):
        """Test getting latest backup."""
        import time
        mgr = BackupManager(backup_dir=temp_backup_dir)

        mgr.create_backup(sample_db_file, label="old")
        time.sleep(1.1)  # Ensure different timestamps (need >1 second for reliable mtime difference)
        latest_path = mgr.create_backup(sample_db_file, label="latest")

        latest = mgr.get_latest_backup()
        assert latest == latest_path

    def test_get_latest_backup_empty(self, temp_backup_dir):
        """Test getting latest backup when none exist."""
        mgr = BackupManager(backup_dir=temp_backup_dir)
        assert mgr.get_latest_backup() is None

    def test_cleanup_old_backups(self, temp_backup_dir, sample_db_file):
        """Test cleaning up old backups."""
        mgr = BackupManager(backup_dir=temp_backup_dir)

        # Create 5 backups
        for i in range(5):
            mgr.create_backup(sample_db_file, label=f"backup_{i}")

        assert len(mgr.list_backups()) == 5

        # Keep only 2
        removed = mgr.cleanup_old_backups(keep_count=2)

        assert removed == 3
        assert len(mgr.list_backups()) == 2

    def test_total_backup_size(self, temp_backup_dir, sample_db_file):
        """Test calculating total backup size."""
        mgr = BackupManager(backup_dir=temp_backup_dir)

        mgr.create_backup(sample_db_file)
        mgr.create_backup(sample_db_file)

        total_size = mgr.total_backup_size
        assert total_size > 0

    def test_get_backup_info(self, temp_backup_dir, sample_db_file):
        """Test getting backup info."""
        mgr = BackupManager(backup_dir=temp_backup_dir)
        backup_path = mgr.create_backup(sample_db_file, label="info_test")

        info = mgr.get_backup_info(backup_path)

        assert info["path"] == backup_path
        assert info["size"] > 0
        assert isinstance(info["created"], datetime)

    def test_backup_nonexistent_file(self, temp_backup_dir):
        """Test backing up non-existent file raises error."""
        mgr = BackupManager(backup_dir=temp_backup_dir)

        with pytest.raises(FileNotFoundError):
            mgr.create_backup(Path("/nonexistent/file.xml"))

    def test_backup_mtime_reflects_creation_time(self, temp_backup_dir, sample_db_file):
        """Test that backup file mtime reflects backup creation time, not source mtime.

        Bug fix: shutil.copy2 preserves source mtime, which broke sorting backups
        by creation order. The fix touches the file after copying to update mtime.
        """
        import time
        mgr = BackupManager(backup_dir=temp_backup_dir)

        # Create first backup
        first_backup = mgr.create_backup(sample_db_file, label="first")
        first_mtime = first_backup.stat().st_mtime

        # Wait to ensure different timestamps
        time.sleep(0.1)

        # Create second backup
        second_backup = mgr.create_backup(sample_db_file, label="second")
        second_mtime = second_backup.stat().st_mtime

        # Second backup should have a later mtime
        assert second_mtime > first_mtime, (
            f"Second backup mtime ({second_mtime}) should be > first backup mtime ({first_mtime})"
        )
