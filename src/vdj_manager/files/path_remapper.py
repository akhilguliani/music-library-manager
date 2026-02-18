"""Path remapping utilities for Windows to macOS conversion."""

from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from ..config import DEFAULT_PATH_MAPPINGS
from ..core.models import Song


class PathRemapper:
    """Handles remapping Windows paths to macOS paths."""

    def __init__(self, mappings: dict[str, str] | None = None):
        self.mappings = mappings or DEFAULT_PATH_MAPPINGS.copy()
        self._sorted_prefixes: list[str] | None = None

    def add_mapping(self, windows_prefix: str, mac_prefix: str) -> None:
        """Add a path mapping.

        Args:
            windows_prefix: Windows path prefix (e.g., "E:/Main/")
            mac_prefix: macOS path prefix (e.g., "/Volumes/MyNVMe/Main/")
        """
        # Normalize to forward slashes
        windows_prefix = windows_prefix.replace("\\", "/")
        self.mappings[windows_prefix] = mac_prefix
        self._sorted_prefixes = None  # Invalidate cache

    def remove_mapping(self, windows_prefix: str) -> bool:
        """Remove a path mapping.

        Args:
            windows_prefix: Windows path prefix to remove

        Returns:
            True if mapping was removed, False if not found
        """
        windows_prefix = windows_prefix.replace("\\", "/")
        if windows_prefix in self.mappings:
            del self.mappings[windows_prefix]
            self._sorted_prefixes = None  # Invalidate cache
            return True
        return False

    def remap_path(self, path: str) -> str | None:
        """Remap a single path using configured mappings.

        Args:
            path: File path to remap

        Returns:
            Remapped path, or None if no mapping found
        """
        # Normalize backslashes
        normalized = path.replace("\\", "/")

        # Build sorted prefix cache on first use (invalidated on mapping changes)
        if self._sorted_prefixes is None:
            self._sorted_prefixes = sorted(self.mappings.keys(), key=len, reverse=True)

        # Try each mapping, longest prefix first
        for win_prefix in self._sorted_prefixes:
            if normalized.startswith(win_prefix):
                mac_prefix = self.mappings[win_prefix]
                return mac_prefix + normalized[len(win_prefix) :]

        return None

    def can_remap(self, path: str) -> bool:
        """Check if a path can be remapped."""
        return self.remap_path(path) is not None

    def detect_windows_prefixes(self, songs: Iterator[Song]) -> dict[str, list[str]]:
        """Detect unique Windows path prefixes from songs.

        Args:
            songs: Iterator of Song objects

        Returns:
            Dict mapping detected prefixes to example file paths
        """
        prefixes: dict[str, list[str]] = defaultdict(list)

        for song in songs:
            if not song.is_windows_path:
                continue

            path = song.file_path.replace("\\", "/")

            # Extract drive letter and first directory
            parts = path.split("/")
            if len(parts) >= 2:
                # e.g., "D:/Main/" or "E:/"
                prefix = f"{parts[0]}/"
                if len(parts) >= 2 and parts[1]:
                    prefix = f"{parts[0]}/{parts[1]}/"

                prefixes[prefix].append(song.file_path)

        return dict(prefixes)

    def detect_mappable_paths(self, songs: Iterator[Song]) -> dict:
        """Analyze Windows paths and suggest mappings.

        Args:
            songs: Iterator of Song objects

        Returns:
            Dict with analysis results
        """
        songs_list = list(songs)
        prefixes = self.detect_windows_prefixes(iter(songs_list))

        result = {
            "total_windows_paths": 0,
            "mappable": 0,
            "unmappable": 0,
            "by_prefix": {},
        }

        for prefix, examples in prefixes.items():
            count = len(examples)
            result["total_windows_paths"] += count  # type: ignore[operator]

            # Check if we have a mapping for this prefix
            has_mapping = any(
                prefix.startswith(win_prefix) or win_prefix.startswith(prefix)
                for win_prefix in self.mappings
            )

            # Check if files would exist after mapping
            sample_mapped = None
            sample_exists = False
            if has_mapping and examples:
                sample_mapped = self.remap_path(examples[0])
                if sample_mapped:
                    sample_exists = Path(sample_mapped).exists()

            result["by_prefix"][prefix] = {  # type: ignore[index]
                "count": count,
                "has_mapping": has_mapping,
                "sample_original": examples[0] if examples else None,
                "sample_mapped": sample_mapped,
                "sample_exists": sample_exists,
                "examples": examples[:5],  # First 5 examples
            }

            if has_mapping:
                result["mappable"] += count  # type: ignore[operator]
            else:
                result["unmappable"] += count  # type: ignore[operator]

        return result

    def remap_songs(
        self,
        songs: Iterator[Song],
        verify_exists: bool = True,
    ) -> Iterator[tuple[str, str, bool]]:
        """Generate path remappings for songs.

        Args:
            songs: Iterator of Song objects
            verify_exists: Whether to verify remapped files exist

        Yields:
            Tuples of (old_path, new_path, exists)
        """
        for song in songs:
            if not song.is_windows_path:
                continue

            new_path = self.remap_path(song.file_path)
            if new_path:
                exists = Path(new_path).exists() if verify_exists else True
                yield (song.file_path, new_path, exists)

    def suggest_mapping(self, windows_path: str, mac_base: str = "/Volumes/MyNVMe") -> str:
        """Suggest a macOS path mapping for a Windows path.

        Args:
            windows_path: Windows path to map
            mac_base: Base macOS path for the drive

        Returns:
            Suggested macOS path
        """
        # Normalize and extract path after drive letter
        normalized = windows_path.replace("\\", "/")
        if len(normalized) > 2 and normalized[1] == ":":
            path_part = normalized[2:]  # Remove "X:"
            return mac_base + path_part
        return normalized

    def get_unmapped_prefixes(self, songs: Iterator[Song]) -> list[str]:
        """Get Windows path prefixes that have no mapping.

        Args:
            songs: Iterator of Song objects

        Returns:
            List of unmapped prefixes
        """
        prefixes = self.detect_windows_prefixes(songs)
        unmapped = []

        for prefix in prefixes:
            if not any(
                prefix.startswith(win_prefix) or win_prefix.startswith(prefix)
                for win_prefix in self.mappings
            ):
                unmapped.append(prefix)

        return unmapped
