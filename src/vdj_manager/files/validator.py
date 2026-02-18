"""File validation utilities."""

from collections.abc import Iterator
from pathlib import Path

from ..config import AUDIO_EXTENSIONS, NON_AUDIO_EXTENSIONS
from ..core.models import Song


class FileValidator:
    """Validates files and detects non-audio entries."""

    @staticmethod
    def _get_extension(path: str) -> str:
        """Extract lowercase file extension from a path."""
        return Path(path).suffix.lower()

    @staticmethod
    def is_audio_file(path: str) -> bool:
        """Check if a file path has an audio extension."""
        ext = Path(path).suffix.lower()
        return ext in AUDIO_EXTENSIONS

    @staticmethod
    def is_non_audio_file(path: str) -> bool:
        """Check if a file path has a known non-audio extension."""
        ext = Path(path).suffix.lower()
        return ext in NON_AUDIO_EXTENSIONS

    @staticmethod
    def _is_audio_ext(ext: str) -> bool:
        """Check if an extension is an audio extension (pre-extracted)."""
        return ext in AUDIO_EXTENSIONS

    @staticmethod
    def _is_non_audio_ext(ext: str) -> bool:
        """Check if an extension is a non-audio extension (pre-extracted)."""
        return ext in NON_AUDIO_EXTENSIONS

    @staticmethod
    def file_exists(path: str) -> bool:
        """Check if a file exists on disk."""
        # Skip Windows paths and network paths
        if len(path) > 1 and path[1] == ":":
            return False
        if path.startswith("netsearch://") or "://" in path:
            return False
        return Path(path).exists()

    @staticmethod
    def get_file_size(path: str) -> int | None:
        """Get file size in bytes, or None if file doesn't exist."""
        try:
            return Path(path).stat().st_size
        except (OSError, FileNotFoundError):
            return None

    def validate_song(self, song: Song) -> dict:
        """Validate a single song entry.

        Returns:
            Dict with validation results
        """
        ext = self._get_extension(song.file_path)
        result = {
            "file_path": song.file_path,
            "is_audio": self._is_audio_ext(ext),
            "is_non_audio": self._is_non_audio_ext(ext),
            "is_windows_path": song.is_windows_path,
            "is_netsearch": song.is_netsearch,
            "exists": False,
            "size_match": None,
            "extension": ext,
        }

        # Only check existence for local paths
        if not song.is_windows_path and not song.is_netsearch:
            result["exists"] = self.file_exists(song.file_path)

            # Check if file size matches
            if result["exists"] and song.file_size:
                actual_size = self.get_file_size(song.file_path)
                if actual_size:
                    result["size_match"] = actual_size == song.file_size

        return result

    def find_missing_files(self, songs: Iterator[Song]) -> list[Song]:
        """Find songs with missing files."""
        missing = []
        for song in songs:
            if song.is_windows_path or song.is_netsearch:
                continue
            if not self.file_exists(song.file_path):
                missing.append(song)
        return missing

    def find_non_audio_entries(self, songs: Iterator[Song]) -> list[Song]:
        """Find songs that are not audio files."""
        non_audio = []
        for song in songs:
            if song.is_netsearch:
                continue
            if self.is_non_audio_file(song.file_path):
                non_audio.append(song)
            elif not self.is_audio_file(song.file_path):
                # Unknown extension, might be non-audio
                non_audio.append(song)
        return non_audio

    def categorize_entries(self, songs: Iterator[Song], collect_extensions: bool = False) -> dict:
        """Categorize all entries by type.

        Args:
            songs: Iterator of Song objects
            collect_extensions: If True, also collect extension counts

        Returns:
            Dict with categorized song lists (and 'extensions' if collect_extensions)
        """
        categories = {
            "audio_exists": [],
            "audio_missing": [],
            "non_audio": [],
            "windows_paths": [],
            "netsearch": [],
            "unknown": [],
        }
        extensions: dict[str, int] = {}

        for song in songs:
            if collect_extensions:
                ext = self._get_extension(song.file_path) or "(none)"
                extensions[ext] = extensions.get(ext, 0) + 1

            if song.is_netsearch:
                categories["netsearch"].append(song)
            elif song.is_windows_path:
                categories["windows_paths"].append(song)
            elif self.is_non_audio_file(song.file_path):
                categories["non_audio"].append(song)
            elif self.is_audio_file(song.file_path):
                if self.file_exists(song.file_path):
                    categories["audio_exists"].append(song)
                else:
                    categories["audio_missing"].append(song)
            else:
                categories["unknown"].append(song)

        if collect_extensions:
            categories["extensions"] = extensions

        return categories

    def generate_report(self, songs: list[Song]) -> dict:
        """Generate a detailed validation report.

        Args:
            songs: List of songs to validate

        Returns:
            Dict with report data
        """
        categories = self.categorize_entries(iter(songs), collect_extensions=True)

        extensions = categories.pop("extensions", {})

        # Group Windows paths by drive
        windows_drives: dict[str, int] = {}
        for song in categories["windows_paths"]:
            drive = song.file_path[0].upper() if song.file_path else "?"
            windows_drives[drive] = windows_drives.get(drive, 0) + 1

        return {
            "total": len(songs),
            "audio_valid": len(categories["audio_exists"]),
            "audio_missing": len(categories["audio_missing"]),
            "non_audio": len(categories["non_audio"]),
            "windows_paths": len(categories["windows_paths"]),
            "netsearch": len(categories["netsearch"]),
            "unknown": len(categories["unknown"]),
            "extensions": dict(sorted(extensions.items(), key=lambda x: -x[1])),
            "windows_drives": windows_drives,
            "missing_files": [s.file_path for s in categories["audio_missing"]],
            "non_audio_files": [s.file_path for s in categories["non_audio"]],
        }
