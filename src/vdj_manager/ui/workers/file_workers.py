"""Background workers for file management operations.

File mutation workers (Import, Remove, Remap) return lists of pending
mutations instead of modifying the database directly.  The main-thread
panel handler applies these mutations, keeping VDJDatabase access
single-threaded and avoiding cross-thread data races.
"""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal

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
    """Worker for importing scanned files into the database.

    Does NOT mutate the database.  Returns a list of file paths
    to add so the main thread can call ``database.add_song()``
    and ``database.save()`` safely.
    """

    def __init__(
        self,
        file_paths: list[str],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.file_paths = file_paths

    def do_work(self) -> dict:
        """Validate and return paths to import.

        Returns:
            Dict with 'paths_to_add' list of valid file paths.
        """
        return {"paths_to_add": list(self.file_paths)}


class RemoveWorker(SimpleWorker):
    """Worker for removing entries from the database.

    Does NOT mutate the database.  Returns a list of paths
    to remove so the main thread can call ``database.remove_song()``
    and ``database.save()`` safely.
    """

    def __init__(
        self,
        paths_to_remove: list[str],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.paths_to_remove = paths_to_remove

    def do_work(self) -> dict:
        """Return paths to remove.

        Returns:
            Dict with 'paths_to_remove' list.
        """
        return {"paths_to_remove": list(self.paths_to_remove)}


class RemapWorker(SimpleWorker):
    """Worker for computing Windows→macOS path remappings.

    Does NOT mutate the database.  Returns a list of
    (old_path, new_path) tuples so the main thread can call
    ``database.remap_path()`` and ``database.save()`` safely.
    """

    def __init__(
        self,
        songs: list[Song],
        remapper: PathRemapper,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.songs = songs
        self.remapper = remapper

    def do_work(self) -> dict:
        """Compute path remappings.

        Returns:
            Dict with 'remappings' (list of (old, new) tuples),
            'skipped' count, and 'failed' count.
        """
        remappings: list[tuple[str, str]] = []
        skipped = 0

        for song in self.songs:
            if not song.is_windows_path:
                skipped += 1
                continue

            new_path = self.remapper.remap_path(song.file_path)
            if new_path is None:
                skipped += 1
                continue

            remappings.append((song.file_path, new_path))

        return {"remappings": remappings, "skipped": skipped}


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
