"""Duplicate detection utilities."""

import hashlib
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from ..core.models import Song


class DuplicateDetector:
    """Detects duplicate songs by various criteria."""

    @staticmethod
    def compute_file_hash(path: str, chunk_size: int = 65536) -> str | None:
        """Compute SHA-256 hash of a file.

        Args:
            path: Path to file
            chunk_size: Size of chunks to read

        Returns:
            Hex digest of file hash, or None if file not accessible
        """
        try:
            hasher = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, FileNotFoundError):
            return None

    @staticmethod
    def compute_partial_hash(path: str, bytes_to_read: int = 1024 * 1024) -> str | None:
        """Compute hash of first N bytes for quick comparison.

        Args:
            path: Path to file
            bytes_to_read: Number of bytes to hash (default 1MB)

        Returns:
            Hex digest, or None if file not accessible
        """
        try:
            hasher = hashlib.sha256()
            with open(path, "rb") as f:
                data = f.read(bytes_to_read)
                hasher.update(data)
            return hasher.hexdigest()
        except (OSError, FileNotFoundError):
            return None

    def find_by_metadata(self, songs: Iterator[Song]) -> dict[str, list[Song]]:
        """Find potential duplicates by artist + title.

        Args:
            songs: Iterator of Song objects

        Returns:
            Dict mapping metadata key to list of songs with same key
        """
        groups: dict[str, list[Song]] = defaultdict(list)

        for song in songs:
            if song.tags and song.tags.author and song.tags.title:
                # Normalize: lowercase, strip whitespace
                key = f"{song.tags.author.lower().strip()}|{song.tags.title.lower().strip()}"
                groups[key].append(song)

        # Filter to only duplicates (more than one entry)
        return {k: v for k, v in groups.items() if len(v) > 1}

    def find_by_filename(self, songs: Iterator[Song]) -> dict[str, list[Song]]:
        """Find potential duplicates by filename (ignoring path).

        Args:
            songs: Iterator of Song objects

        Returns:
            Dict mapping filename to list of songs with same filename
        """
        groups: dict[str, list[Song]] = defaultdict(list)

        for song in songs:
            filename = Path(song.file_path).name.lower()
            groups[filename].append(song)

        return {k: v for k, v in groups.items() if len(v) > 1}

    def find_by_size(self, songs: Iterator[Song]) -> dict[int, list[Song]]:
        """Find potential duplicates by file size.

        Args:
            songs: Iterator of Song objects

        Returns:
            Dict mapping file size to list of songs with same size
        """
        groups: dict[int, list[Song]] = defaultdict(list)

        for song in songs:
            if song.file_size:
                groups[song.file_size].append(song)

        return {k: v for k, v in groups.items() if len(v) > 1}

    def find_by_hash(
        self,
        songs: list[Song],
        use_partial: bool = True,
        verify_full: bool = True,
    ) -> list[list[Song]]:
        """Find exact duplicates by file hash.

        Args:
            songs: List of Song objects
            use_partial: Use partial hash for initial grouping
            verify_full: Verify with full hash

        Returns:
            List of duplicate groups (each group is a list of duplicate songs)
        """
        # First, group by file size (quick filter)
        by_size = self.find_by_size(iter(songs))

        # Then hash files with same size
        duplicates = []

        for size_group in by_size.values():
            if len(size_group) < 2:
                continue

            # Compute hashes for files that exist
            hash_groups: dict[str, list[Song]] = defaultdict(list)

            for song in size_group:
                if song.is_windows_path or song.is_netsearch:
                    continue

                if use_partial:
                    file_hash = self.compute_partial_hash(song.file_path)
                else:
                    file_hash = self.compute_file_hash(song.file_path)

                if file_hash:
                    hash_groups[file_hash].append(song)

            # Verify partial hash matches with full hash
            for group in hash_groups.values():
                if len(group) < 2:
                    continue

                if use_partial and verify_full and len(group) > 2:
                    # Only do expensive full-hash verification for groups of 3+
                    # where partial hash collisions are more likely.
                    # Groups of 2 matching on size + 1MB partial hash are
                    # near-certainly true duplicates.
                    full_hash_groups: dict[str, list[Song]] = defaultdict(list)
                    for song in group:
                        full_hash = self.compute_file_hash(song.file_path)
                        if full_hash:
                            full_hash_groups[full_hash].append(song)

                    for full_group in full_hash_groups.values():
                        if len(full_group) > 1:
                            duplicates.append(full_group)
                else:
                    duplicates.append(group)

        return duplicates

    def find_all_duplicates(
        self,
        songs: list[Song],
        include_hash: bool = False,
    ) -> dict:
        """Find all types of duplicates.

        Args:
            songs: List of Song objects
            include_hash: Whether to compute file hashes (slow)

        Returns:
            Dict with duplicate groups by type
        """
        result = {
            "by_metadata": self.find_by_metadata(iter(songs)),
            "by_filename": self.find_by_filename(iter(songs)),
            "by_size": {},  # Converted to list of song paths
            "by_hash": [],
            "summary": {
                "metadata_groups": 0,
                "filename_groups": 0,
                "exact_duplicates": 0,
            },
        }

        result["summary"]["metadata_groups"] = len(result["by_metadata"])  # type: ignore[index]
        result["summary"]["filename_groups"] = len(result["by_filename"])  # type: ignore[index]

        if include_hash:
            hash_dupes = self.find_by_hash(songs)
            result["by_hash"] = [[s.file_path for s in group] for group in hash_dupes]  # type: ignore[misc]
            result["summary"]["exact_duplicates"] = sum(len(group) - 1 for group in hash_dupes)  # type: ignore[index]

        return result

    def suggest_duplicates_to_remove(
        self,
        duplicate_groups: list[list[Song]],
        prefer_local: bool = True,
    ) -> list[Song]:
        """Suggest which duplicates to remove.

        Args:
            duplicate_groups: List of duplicate song groups
            prefer_local: Prefer keeping local files over external drive

        Returns:
            List of songs suggested for removal
        """
        to_remove = []

        for group in duplicate_groups:
            if len(group) < 2:
                continue

            # Sort by preference
            def sort_key(song: Song) -> tuple:
                # Prefer: existing > missing, local > external, has metadata > no metadata
                exists = Path(song.file_path).exists() if not song.is_windows_path else False
                is_local = song.file_path.startswith("/Users/")
                has_metadata = song.tags is not None and song.tags.author is not None

                if prefer_local:
                    return (not exists, not is_local, not has_metadata)
                return (not exists, is_local, not has_metadata)

            sorted_group = sorted(group, key=sort_key)

            # Keep the first one (best), suggest removing the rest
            to_remove.extend(sorted_group[1:])

        return to_remove
