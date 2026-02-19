"""Background workers for VDJ database operations."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal

from vdj_manager.core.backup import BackupManager
from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import DatabaseStats, Song
from vdj_manager.files.validator import FileValidator
from vdj_manager.ui.workers.base_worker import SimpleWorker


class DatabaseLoadResult:
    """Result of loading a VDJ database."""

    def __init__(
        self,
        success: bool,
        database: VDJDatabase | None = None,
        tracks: list[Song] | None = None,
        stats: DatabaseStats | None = None,
        error: str | None = None,
    ):
        """Initialize the result.

        Args:
            success: Whether loading succeeded.
            database: Loaded VDJDatabase object.
            tracks: List of Song objects.
            stats: Database statistics.
            error: Error message if failed.
        """
        self.success = success
        self.database = database
        self.tracks = tracks or []
        self.stats = stats
        self.error = error


class DatabaseLoadWorker(SimpleWorker):
    """Worker for loading a VDJ database in the background.

    This worker loads and parses the database XML file, extracting
    all songs and calculating statistics.

    Signals:
        progress: Emitted during loading (message)
    """

    progress = Signal(str)

    def __init__(
        self,
        database_path: Path,
        check_file_existence: bool = False,
        parent: Any = None,
    ) -> None:
        """Initialize the database load worker.

        Args:
            database_path: Path to the database.xml file.
            check_file_existence: Whether to check if files exist on disk.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self.database_path = database_path
        self.check_file_existence = check_file_existence

    def do_work(self) -> DatabaseLoadResult:
        """Load the database.

        Returns:
            DatabaseLoadResult with loaded data.
        """
        try:
            self.progress.emit(f"Loading {self.database_path.name}...")

            if not self.database_path.exists():
                return DatabaseLoadResult(
                    success=False,
                    error=f"Database file not found: {self.database_path}",
                )

            # Load and parse the database
            db = VDJDatabase(self.database_path)
            db.load()

            self.progress.emit("Extracting tracks...")

            # Get all songs as a list
            tracks = list(db.iter_songs())

            self.progress.emit("Calculating statistics...")

            # Get stats
            stats = db.get_stats(check_existence=self.check_file_existence)

            self.progress.emit(f"Loaded {len(tracks)} tracks")

            return DatabaseLoadResult(
                success=True,
                database=db,
                tracks=tracks,
                stats=stats,
            )

        except Exception as e:
            return DatabaseLoadResult(
                success=False,
                error=str(e),
            )


class DatabaseSaveWorker(SimpleWorker):
    """Worker for saving a VDJ database in the background."""

    def __init__(self, database: VDJDatabase, parent: Any = None) -> None:
        """Initialize the database save worker.

        Args:
            database: VDJDatabase to save.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self.database = database

    def do_work(self) -> bool:
        """Save the database.

        Returns:
            True if successful.
        """
        self.database.save()
        return True


class BackupWorker(SimpleWorker):
    """Worker for creating a database backup in the background."""

    def __init__(
        self,
        db_path: Path,
        label: str | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.db_path = db_path
        self.label = label

    def do_work(self) -> Path:
        """Create a backup of the database.

        Returns:
            Path to the created backup file.
        """
        manager = BackupManager()
        return manager.create_backup(self.db_path, label=self.label)


class ValidateWorker(SimpleWorker):
    """Worker for validating database entries in the background."""

    def __init__(self, tracks: list[Song], parent: Any = None) -> None:
        super().__init__(parent)
        self.tracks = tracks

    def do_work(self) -> dict:
        """Validate all tracks and return a report.

        Returns:
            Validation report dict from FileValidator.generate_report().
        """
        validator = FileValidator()
        return validator.generate_report(self.tracks)


class CleanWorker(SimpleWorker):
    """Worker for cleaning invalid entries from the database."""

    def __init__(
        self,
        database: VDJDatabase,
        tracks_to_remove: list[Song],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.tracks_to_remove = tracks_to_remove

    def do_work(self) -> int:
        """Remove invalid entries from the database.

        Returns:
            Number of entries removed.
        """
        removed = 0
        for song in self.tracks_to_remove:
            if self.database.remove_song(song.file_path):
                removed += 1
        if removed > 0:
            self.database.save()
        return removed
