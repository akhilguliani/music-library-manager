"""Directory scanning utilities for finding audio files."""

from collections.abc import Iterator
from pathlib import Path

from ..config import AUDIO_EXTENSIONS


class DirectoryScanner:
    """Scans directories for audio files."""

    def __init__(self, extensions: set[str] | None = None):
        self.extensions = extensions or AUDIO_EXTENSIONS

    def scan_directory(self, directory: Path, recursive: bool = True) -> Iterator[Path]:
        """Scan a directory for audio files.

        Args:
            directory: Directory to scan
            recursive: Whether to scan subdirectories

        Yields:
            Paths to audio files found
        """
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        if recursive:
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in self.extensions:
                    yield path
        else:
            for path in directory.iterdir():
                if path.is_file() and path.suffix.lower() in self.extensions:
                    yield path

    def scan_with_metadata(self, directory: Path, recursive: bool = True) -> Iterator[dict]:
        """Scan directory and return file metadata.

        Args:
            directory: Directory to scan
            recursive: Whether to scan subdirectories

        Yields:
            Dicts with file path and metadata
        """
        for path in self.scan_directory(directory, recursive):
            stat = path.stat()
            yield {
                "path": path,
                "file_path": str(path),
                "file_size": stat.st_size,
                "modified": stat.st_mtime,
                "extension": path.suffix.lower(),
                "name": path.stem,
            }

    def count_files(self, directory: Path, recursive: bool = True) -> dict:
        """Count audio files by extension.

        Args:
            directory: Directory to scan
            recursive: Whether to scan subdirectories

        Returns:
            Dict with counts by extension and total
        """
        counts: dict[str, int] = {}
        total = 0

        for path in self.scan_directory(directory, recursive):
            ext = path.suffix.lower()
            counts[ext] = counts.get(ext, 0) + 1
            total += 1

        return {
            "by_extension": dict(sorted(counts.items())),
            "total": total,
        }

    def find_new_files(
        self,
        directory: Path,
        existing_paths: set[str],
        recursive: bool = True,
    ) -> list[dict]:
        """Find files not already in a database.

        Args:
            directory: Directory to scan
            existing_paths: Set of file paths already in database
            recursive: Whether to scan subdirectories

        Returns:
            List of file metadata dicts for new files
        """
        new_files = []

        for file_info in self.scan_with_metadata(directory, recursive):
            if file_info["file_path"] not in existing_paths:
                new_files.append(file_info)

        return new_files

    def find_orphaned_files(
        self,
        directory: Path,
        database_paths: set[str],
        recursive: bool = True,
    ) -> list[Path]:
        """Find files on disk not in the database.

        Args:
            directory: Directory to scan
            database_paths: Set of file paths in database
            recursive: Whether to scan subdirectories

        Returns:
            List of paths to orphaned files
        """
        orphaned = []

        for path in self.scan_directory(directory, recursive):
            if str(path) not in database_paths:
                orphaned.append(path)

        return orphaned
