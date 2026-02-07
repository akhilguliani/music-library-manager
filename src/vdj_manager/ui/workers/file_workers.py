"""Background workers for file management operations."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.files.duplicates import DuplicateDetector
from vdj_manager.files.path_remapper import PathRemapper
from vdj_manager.files.scanner import DirectoryScanner
from vdj_manager.ui.workers.base_worker import SimpleWorker


class ScanWorker(SimpleWorker):
    """Worker for scanning a directory for new audio files."""

    def __init__(
        self,
        directory: Path,
        existing_paths: set[str],
        recursive: bool = True,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.directory = directory
        self.existing_paths = existing_paths
        self.recursive = recursive

    def do_work(self) -> list[dict]:
        """Scan directory and return new files not in database.

        Returns:
            List of file metadata dicts.
        """
        scanner = DirectoryScanner()
        return scanner.find_new_files(
            self.directory, self.existing_paths, self.recursive
        )


class ImportWorker(SimpleWorker):
    """Worker for importing scanned files into the database."""

    def __init__(
        self,
        database: VDJDatabase,
        file_paths: list[str],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.file_paths = file_paths

    def do_work(self) -> dict:
        """Import files into database.

        Returns:
            Dict with 'added' and 'failed' counts.
        """
        added = 0
        failed = 0
        for path in self.file_paths:
            try:
                self.database.add_song(path)
                added += 1
            except Exception:
                failed += 1

        if added > 0:
            self.database.save()

        return {"added": added, "failed": failed}


class RemoveWorker(SimpleWorker):
    """Worker for removing entries from the database."""

    def __init__(
        self,
        database: VDJDatabase,
        paths_to_remove: list[str],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.paths_to_remove = paths_to_remove

    def do_work(self) -> int:
        """Remove entries from database.

        Returns:
            Number of entries removed.
        """
        removed = 0
        for path in self.paths_to_remove:
            if self.database.remove_song(path):
                removed += 1
        if removed > 0:
            self.database.save()
        return removed


class RemapWorker(SimpleWorker):
    """Worker for remapping Windows paths to macOS paths."""

    def __init__(
        self,
        database: VDJDatabase,
        songs: list[Song],
        remapper: PathRemapper,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.songs = songs
        self.remapper = remapper

    def do_work(self) -> dict:
        """Remap paths in database.

        Returns:
            Dict with 'remapped', 'skipped', and 'failed' counts.
        """
        remapped = 0
        skipped = 0
        failed = 0

        for song in self.songs:
            if not song.is_windows_path:
                skipped += 1
                continue

            new_path = self.remapper.remap_path(song.file_path)
            if new_path is None:
                skipped += 1
                continue

            try:
                if self.database.remap_path(song.file_path, new_path):
                    remapped += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        if remapped > 0:
            self.database.save()

        return {"remapped": remapped, "skipped": skipped, "failed": failed}


class DuplicateWorker(SimpleWorker):
    """Worker for finding duplicate entries."""

    def __init__(
        self,
        tracks: list[Song],
        by_metadata: bool = True,
        by_filename: bool = True,
        by_hash: bool = False,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.tracks = tracks
        self.by_metadata = by_metadata
        self.by_filename = by_filename
        self.by_hash = by_hash

    def do_work(self) -> dict:
        """Find duplicates.

        Returns:
            Dict from DuplicateDetector.find_all_duplicates().
        """
        detector = DuplicateDetector()
        return detector.find_all_duplicates(
            self.tracks, include_hash=self.by_hash
        )
