"""Serato export functionality."""

import logging
import struct
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, TXXX, TKEY, TBPM, GEOB
    from mutagen.mp4 import MP4
    from mutagen.flac import FLAC
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from ..core.models import Song
from ..config import SERATO_LOCAL, SERATO_MYNVME
from .mapper import VDJToSeratoMapper


class SeratoCrateWriter:
    """Write Serato crate files."""

    # Serato crate file header
    CRATE_HEADER = b"vrsn\x00\x00\x00\x008\x00.\x001\x00/\x00S\x00e\x00r\x00a\x00t\x00o\x00 \x00S\x00c\x00r\x00a\x00t\x00c\x00h\x00L\x00i\x00v\x00e\x00 \x00C\x00r\x00a\x00t\x00e"

    def __init__(self, serato_dir: Optional[Path] = None):
        """Initialize crate writer.

        Args:
            serato_dir: Serato directory (default: ~/Music/_Serato_)
        """
        self.serato_dir = serato_dir or SERATO_LOCAL
        self.subcrates_dir = self.serato_dir / "Subcrates"

    def ensure_directories(self) -> None:
        """Create Serato directories if they don't exist."""
        self.subcrates_dir.mkdir(parents=True, exist_ok=True)

    def encode_path(self, file_path: str) -> bytes:
        """Encode a file path for Serato crate format.

        Serato uses UTF-16BE encoding for paths.

        Args:
            file_path: File path string

        Returns:
            Encoded path bytes
        """
        # Serato expects paths relative to drive root or absolute
        path_bytes = file_path.encode("utf-16-be")
        return path_bytes

    def create_track_entry(self, file_path: str) -> bytes:
        """Create a track entry for the crate file.

        Args:
            file_path: Path to audio file

        Returns:
            Binary track entry
        """
        # Track entry format:
        # "otrk" + 4-byte length + "ptrk" + 4-byte path length + path
        path_encoded = self.encode_path(file_path)
        path_length = len(path_encoded)

        ptrk = b"ptrk" + struct.pack(">I", path_length) + path_encoded
        otrk = b"otrk" + struct.pack(">I", len(ptrk)) + ptrk

        return otrk

    def write_crate(self, name: str, file_paths: list[str]) -> Path:
        """Write a Serato crate file.

        Args:
            name: Crate name
            file_paths: List of file paths to include

        Returns:
            Path to created crate file
        """
        self.ensure_directories()

        # Build crate content
        content = bytearray(self.CRATE_HEADER)

        for path in file_paths:
            track_entry = self.create_track_entry(path)
            content.extend(track_entry)

        # Sanitize crate name: strip path separators and filesystem-unsafe chars
        import re
        safe_name = re.sub(r'[/\\:*?"<>|]', "_", name)
        # Remove path components (e.g. "../../evil" → "evil" after sub becomes "_.._evil")
        safe_name = Path(safe_name).name
        if not safe_name or safe_name == ".":
            safe_name = "unnamed"

        # Write crate file
        crate_path = self.subcrates_dir / f"{safe_name}.crate"
        with open(crate_path, "wb") as f:
            f.write(content)

        return crate_path

    def list_crates(self) -> list[str]:
        """List existing Serato crates.

        Returns:
            List of crate names
        """
        if not self.subcrates_dir.exists():
            return []

        return [p.stem for p in self.subcrates_dir.glob("*.crate")]


class SeratoTagWriter:
    """Write Serato metadata to audio file tags."""

    # Serato marker colors (ARGB format)
    COLORS = [
        0xFFCC0000,  # Red
        0xFFCC4400,  # Orange
        0xFFCCCC00,  # Yellow
        0xFF00CC00,  # Green
        0xFF00CCCC,  # Cyan
        0xFF0088CC,  # Blue
        0xFF8800CC,  # Purple
        0xFFCC00CC,  # Magenta
    ]

    def __init__(self):
        if not MUTAGEN_AVAILABLE:
            raise ImportError("mutagen is required for Serato tag writing")

    def write_tags(
        self,
        file_path: str,
        bpm: Optional[float] = None,
        key: Optional[str] = None,
        cue_points: Optional[list] = None,
        comment: Optional[str] = None,
    ) -> bool:
        """Write Serato-compatible tags to an audio file.

        Args:
            file_path: Path to audio file
            bpm: BPM value
            key: Key string
            cue_points: List of cue point dicts
            comment: Comment string

        Returns:
            True if successful
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        try:
            if ext == ".mp3":
                return self._write_mp3_tags(file_path, bpm, key, cue_points, comment)
            elif ext in (".m4a", ".aac", ".mp4"):
                return self._write_mp4_tags(file_path, bpm, key, comment)
            elif ext == ".flac":
                return self._write_flac_tags(file_path, bpm, key, comment)
            else:
                return False
        except Exception as e:
            logger.error("Failed to write tags to %s: %s", file_path, e)
            return False

    def _write_mp3_tags(
        self,
        file_path: str,
        bpm: Optional[float],
        key: Optional[str],
        cue_points: Optional[list],
        comment: Optional[str],
    ) -> bool:
        """Write tags to MP3 file."""
        try:
            audio = ID3(file_path)
        except Exception:
            logger.debug("No existing ID3 tag in %s, creating new", file_path)
            audio = ID3()

        # Write BPM
        if bpm:
            audio.delall("TBPM")
            audio.add(TBPM(encoding=3, text=[str(int(bpm))]))

        # Write key
        if key:
            audio.delall("TKEY")
            audio.add(TKEY(encoding=3, text=[key]))

        # Write comment as TXXX frame
        if comment:
            # Remove existing comment TXXX
            audio.delall("TXXX:COMMENT")
            audio.add(TXXX(encoding=3, desc="COMMENT", text=[comment]))

        # Write Serato markers (cue points)
        if cue_points:
            markers_data = self._create_serato_markers2(cue_points)
            audio.delall("GEOB:Serato Markers2")
            audio.add(GEOB(
                encoding=0,
                mime="application/octet-stream",
                desc="Serato Markers2",
                data=markers_data,
            ))

        audio.save(file_path)
        return True

    def _write_mp4_tags(
        self,
        file_path: str,
        bpm: Optional[float],
        key: Optional[str],
        comment: Optional[str],
    ) -> bool:
        """Write tags to M4A/AAC file."""
        audio = MP4(file_path)

        if bpm:
            audio["tmpo"] = [int(bpm)]

        if key:
            audio["----:com.apple.iTunes:INITIALKEY"] = key.encode("utf-8")

        if comment:
            audio["\xa9cmt"] = [comment]

        audio.save()
        return True

    def _write_flac_tags(
        self,
        file_path: str,
        bpm: Optional[float],
        key: Optional[str],
        comment: Optional[str],
    ) -> bool:
        """Write tags to FLAC file."""
        audio = FLAC(file_path)

        if bpm:
            audio["BPM"] = str(int(bpm))

        if key:
            audio["INITIALKEY"] = key

        if comment:
            audio["COMMENT"] = comment

        audio.save()
        return True

    def _create_serato_markers2(self, cue_points: list) -> bytes:
        """Create Serato Markers2 binary data.

        This is a simplified implementation. The full Serato Markers2
        format is complex with base64-encoded sections.

        Args:
            cue_points: List of cue point dicts with position_ms, name, color

        Returns:
            Binary data for GEOB tag
        """
        # Serato Markers2 format header
        header = b"\x01\x01"  # Version

        # Each cue point entry
        entries = []
        for i, cue in enumerate(cue_points[:8]):  # Max 8 cue points
            pos_ms = cue.get("position_ms", 0)
            color = self.COLORS[i % len(self.COLORS)]
            name = cue.get("name", f"Cue {i + 1}")[:32]  # Max 32 chars

            # Cue point entry: type(1) + position(4) + color(4) + name
            entry = struct.pack(">B", 0)  # Type 0 = cue
            entry += struct.pack(">I", pos_ms)
            entry += struct.pack(">I", color)
            entry += struct.pack(">B", len(name))
            entry += name.encode("utf-8")
            entries.append(entry)

        # Combine header and entries
        data = header + struct.pack(">I", len(entries))
        for entry in entries:
            data += struct.pack(">I", len(entry)) + entry

        return data


class SeratoExporter:
    """Export VDJ library to Serato format."""

    def __init__(self, serato_dir: Optional[Path] = None):
        """Initialize Serato exporter.

        Args:
            serato_dir: Serato directory path
        """
        self.mapper = VDJToSeratoMapper()
        self.crate_writer = SeratoCrateWriter(serato_dir)

        try:
            self.tag_writer = SeratoTagWriter()
        except ImportError:
            self.tag_writer = None

    def export_song(self, song: Song, cues_only: bool = False) -> bool:
        """Export a single song to Serato format.

        Args:
            song: VDJ Song object
            cues_only: Only export cue points, not metadata

        Returns:
            True if successful
        """
        if not self.tag_writer:
            return False

        if not Path(song.file_path).exists():
            return False

        # Map VDJ metadata to Serato format
        mapped = self.mapper.map_song(song)

        if cues_only:
            # Only write cue points
            return self.tag_writer.write_tags(
                song.file_path,
                cue_points=mapped["cue_points"],
            )
        else:
            # Write all metadata
            return self.tag_writer.write_tags(
                song.file_path,
                bpm=mapped["bpm"],
                key=mapped["key"],
                cue_points=mapped["cue_points"],
                comment=mapped["comment"],
            )

    def create_crate(self, name: str, file_paths: list[str]) -> Path:
        """Create a Serato crate.

        Args:
            name: Crate name
            file_paths: List of file paths

        Returns:
            Path to created crate file
        """
        return self.crate_writer.write_crate(name, file_paths)

    def export_playlist(self, name: str, songs: list[Song]) -> tuple[int, Path]:
        """Export a playlist as a Serato crate.

        Args:
            name: Playlist/crate name
            songs: List of VDJ Song objects

        Returns:
            Tuple of (exported count, crate path)
        """
        exported = 0
        file_paths = []

        for song in songs:
            if Path(song.file_path).exists():
                if self.export_song(song):
                    exported += 1
                file_paths.append(song.file_path)

        crate_path = self.create_crate(name, file_paths)

        return exported, crate_path

    def list_existing_crates(self) -> list[str]:
        """List existing Serato crates.

        Returns:
            List of crate names
        """
        return self.crate_writer.list_crates()
