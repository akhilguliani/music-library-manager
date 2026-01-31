"""Backup management for VDJ databases."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import BACKUP_DIR


class BackupManager:
    """Manages timestamped backups of VDJ database files."""

    def __init__(self, backup_dir: Optional[Path] = None):
        self.backup_dir = backup_dir or BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, db_path: Path, label: Optional[str] = None) -> Path:
        """Create a timestamped backup of a database file.

        Args:
            db_path: Path to the database file to backup
            label: Optional label to include in backup filename

        Returns:
            Path to the created backup file
        """
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create a descriptive backup name
        db_name = db_path.stem
        if "MyNVMe" in str(db_path):
            source_label = "mynvme"
        elif "Application Support" in str(db_path):
            source_label = "local"
        else:
            source_label = "unknown"

        if label:
            backup_name = f"{db_name}_{source_label}_{label}_{timestamp}.xml"
        else:
            backup_name = f"{db_name}_{source_label}_{timestamp}.xml"

        backup_path = self.backup_dir / backup_name
        shutil.copy2(db_path, backup_path)

        return backup_path

    def list_backups(self, source: Optional[str] = None) -> list[Path]:
        """List all backup files, optionally filtered by source.

        Args:
            source: Filter by source label ('local', 'mynvme', etc.)

        Returns:
            List of backup file paths, sorted by modification time (newest first)
        """
        pattern = "*.xml"
        if source:
            pattern = f"*_{source}_*.xml"

        backups = list(self.backup_dir.glob(pattern))
        return sorted(backups, key=lambda p: p.stat().st_mtime, reverse=True)

    def get_latest_backup(self, source: Optional[str] = None) -> Optional[Path]:
        """Get the most recent backup file.

        Args:
            source: Filter by source label ('local', 'mynvme', etc.)

        Returns:
            Path to the most recent backup, or None if no backups exist
        """
        backups = self.list_backups(source)
        return backups[0] if backups else None

    def restore_backup(self, backup_path: Path, target_path: Path) -> None:
        """Restore a backup to a target location.

        Args:
            backup_path: Path to the backup file
            target_path: Path where to restore the backup
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        # Create a safety backup of current file before restoring
        if target_path.exists():
            self.create_backup(target_path, label="pre_restore")

        shutil.copy2(backup_path, target_path)

    def cleanup_old_backups(self, keep_count: int = 10, source: Optional[str] = None) -> int:
        """Remove old backups, keeping the most recent ones.

        Args:
            keep_count: Number of backups to keep
            source: Filter by source label ('local', 'mynvme', etc.)

        Returns:
            Number of backups removed
        """
        backups = self.list_backups(source)

        if len(backups) <= keep_count:
            return 0

        to_remove = backups[keep_count:]
        for backup in to_remove:
            backup.unlink()

        return len(to_remove)

    def get_backup_info(self, backup_path: Path) -> dict:
        """Get information about a backup file.

        Args:
            backup_path: Path to the backup file

        Returns:
            Dict with backup metadata
        """
        stat = backup_path.stat()
        name_parts = backup_path.stem.split("_")

        return {
            "path": backup_path,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime),
            "source": name_parts[1] if len(name_parts) > 1 else "unknown",
            "label": name_parts[2] if len(name_parts) > 3 else None,
        }

    @property
    def total_backup_size(self) -> int:
        """Calculate total size of all backups in bytes."""
        return sum(f.stat().st_size for f in self.backup_dir.glob("*.xml"))
