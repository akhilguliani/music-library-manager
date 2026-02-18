"""Read and write embedded audio file tags using mutagen.

Supports MP3 (ID3), M4A/MP4, FLAC, OGG Vorbis, WAV, and AIFF.
"""

import logging
from pathlib import Path
from typing import Optional

from vdj_manager.core.models import Song

logger = logging.getLogger(__name__)

# Fields supported for read/write
SUPPORTED_FIELDS = [
    "title", "artist", "album", "genre", "year",
    "track_number", "bpm", "key", "composer", "comment",
]

# MP3 ID3 frame mapping
_ID3_FRAMES = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "genre": "TCON",
    "year": "TDRC",
    "track_number": "TRCK",
    "bpm": "TBPM",
    "key": "TKEY",
    "composer": "TCOM",
    # comment uses COMM frame (special handling)
}

# MP4/M4A tag mapping
_MP4_KEYS = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "genre": "\xa9gen",
    "year": "\xa9day",
    "track_number": "trkn",
    "bpm": "tmpo",
    "key": "----:com.apple.iTunes:initialkey",
    "composer": "\xa9wrt",
    "comment": "\xa9cmt",
}

# Vorbis comment mapping (FLAC, OGG)
_VORBIS_KEYS = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "genre": "genre",
    "year": "date",
    "track_number": "tracknumber",
    "bpm": "bpm",
    "key": "initialkey",
    "composer": "composer",
    "comment": "comment",
}


class FileTagEditor:
    """Read and write embedded tags in audio files.

    Uses mutagen (lazy-imported) to support MP3, M4A, FLAC, OGG, WAV, AIFF.
    """

    def read_tags(self, file_path: str) -> dict[str, Optional[str]]:
        """Read tags from an audio file.

        Args:
            file_path: Path to the audio file.

        Returns:
            Dict with SUPPORTED_FIELDS keys, values are strings or None.
        """
        result: dict[str, Optional[str]] = {f: None for f in SUPPORTED_FIELDS}

        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
        except Exception:
            logger.warning("Failed to open %s for tag reading", file_path, exc_info=True)
            return result

        if audio is None:
            return result

        ext = Path(file_path).suffix.lower()

        if ext == ".mp3":
            result = self._read_id3(audio, result)
        elif ext in (".m4a", ".mp4", ".aac"):
            result = self._read_mp4(audio, result)
        elif ext in (".flac", ".ogg"):
            result = self._read_vorbis(audio, result)
        elif ext in (".wav", ".aiff", ".aif"):
            # WAV/AIFF may have ID3 tags via mutagen
            result = self._read_id3(audio, result)

        return result

    def write_tags(self, file_path: str, tags: dict[str, Optional[str]]) -> bool:
        """Write tags to an audio file.

        Args:
            file_path: Path to the audio file.
            tags: Dict with field names from SUPPORTED_FIELDS.

        Returns:
            True if successful, False otherwise.
        """
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
        except Exception:
            logger.error("Failed to open %s for tag writing", file_path, exc_info=True)
            return False

        if audio is None:
            return False

        ext = Path(file_path).suffix.lower()

        try:
            if ext == ".mp3":
                self._write_id3(audio, tags)
            elif ext in (".m4a", ".mp4", ".aac"):
                self._write_mp4(audio, tags)
            elif ext in (".flac", ".ogg"):
                self._write_vorbis(audio, tags)
            elif ext in (".wav", ".aiff", ".aif"):
                self._write_id3(audio, tags)
            else:
                logger.warning("Unsupported format for writing: %s", ext)
                return False

            audio.save()
            return True
        except Exception:
            logger.error("Failed to write tags to %s", file_path, exc_info=True)
            return False

    # --- ID3 (MP3, WAV, AIFF) ---

    def _read_id3(self, audio, result: dict) -> dict:
        """Read ID3 tags from an MP3/WAV/AIFF file."""
        tags = getattr(audio, "tags", None)
        if tags is None:
            return result

        for field, frame_id in _ID3_FRAMES.items():
            frame = tags.get(frame_id)
            if frame is not None:
                text = str(frame.text[0]) if frame.text else None
                if text:
                    result[field] = text

        # Comment: COMM frame
        for key in tags:
            if key.startswith("COMM"):
                frame = tags[key]
                if frame.text:
                    result["comment"] = str(frame.text[0])
                break

        return result

    def _write_id3(self, audio, tags: dict) -> None:
        """Write ID3 tags to an MP3/WAV/AIFF file."""
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TDRC, TRCK, TBPM, TKEY, TCOM, COMM

        id3_tags = audio.tags
        if id3_tags is None:
            # Add ID3 tags if none exist
            audio.add_tags()
            id3_tags = audio.tags

        frame_classes = {
            "title": TIT2, "artist": TPE1, "album": TALB,
            "genre": TCON, "year": TDRC, "track_number": TRCK,
            "bpm": TBPM, "key": TKEY, "composer": TCOM,
        }

        for field, value in tags.items():
            if field == "comment":
                if value:
                    id3_tags.setall("COMM", [COMM(encoding=3, lang="eng", desc="", text=[value])])
                else:
                    id3_tags.delall("COMM")
                continue

            frame_id = _ID3_FRAMES.get(field)
            cls = frame_classes.get(field)
            if frame_id and cls:
                if value:
                    id3_tags.setall(frame_id, [cls(encoding=3, text=[value])])
                elif frame_id in id3_tags:
                    id3_tags.delall(frame_id)

    # --- MP4/M4A ---

    def _read_mp4(self, audio, result: dict) -> dict:
        """Read MP4/M4A tags."""
        tags = getattr(audio, "tags", None)
        if tags is None:
            return result

        for field, key in _MP4_KEYS.items():
            value = tags.get(key)
            if value is None:
                continue

            if field == "track_number":
                # MP4 track number is a list of (track, total) tuples
                if isinstance(value, list) and len(value) > 0:
                    track_tuple = value[0]
                    if isinstance(track_tuple, tuple):
                        result[field] = str(track_tuple[0])
                    else:
                        result[field] = str(track_tuple)
            elif field == "bpm":
                # tmpo is a list of ints
                if isinstance(value, list) and len(value) > 0:
                    result[field] = str(value[0])
            elif key.startswith("----"):
                # Freeform atoms are bytes
                if isinstance(value, list) and len(value) > 0:
                    val = value[0]
                    result[field] = val.decode("utf-8") if isinstance(val, bytes) else str(val)
            else:
                if isinstance(value, list) and len(value) > 0:
                    result[field] = str(value[0])

        return result

    def _write_mp4(self, audio, tags: dict) -> None:
        """Write MP4/M4A tags."""
        from mutagen.mp4 import MP4FreeForm

        mp4_tags = audio.tags
        if mp4_tags is None:
            audio.add_tags()
            mp4_tags = audio.tags

        for field, value in tags.items():
            key = _MP4_KEYS.get(field)
            if key is None:
                continue

            if value is None:
                mp4_tags.pop(key, None)
                continue

            if field == "track_number":
                try:
                    mp4_tags[key] = [(int(value), 0)]
                except (ValueError, TypeError):
                    pass
            elif field == "bpm":
                try:
                    mp4_tags[key] = [int(float(value))]
                except (ValueError, TypeError):
                    pass
            elif key.startswith("----"):
                mp4_tags[key] = [MP4FreeForm(value.encode("utf-8"))]
            else:
                mp4_tags[key] = [value]

    # --- Vorbis (FLAC, OGG) ---

    def _read_vorbis(self, audio, result: dict) -> dict:
        """Read Vorbis comments from FLAC/OGG."""
        tags = getattr(audio, "tags", None)
        if tags is None:
            # FLAC uses audio directly as a dict-like
            tags = audio

        for field, key in _VORBIS_KEYS.items():
            values = tags.get(key)
            if values and isinstance(values, list) and len(values) > 0:
                result[field] = str(values[0])

        return result

    def _write_vorbis(self, audio, tags: dict) -> None:
        """Write Vorbis comments to FLAC/OGG."""
        for field, value in tags.items():
            key = _VORBIS_KEYS.get(field)
            if key is None:
                continue

            if value:
                audio[key] = [value]
            elif key in audio:
                del audio[key]


def vdj_tags_to_file_tags(song: Song) -> dict[str, Optional[str]]:
    """Map VDJ database tags to FileTagEditor field dict.

    Args:
        song: Song model with tags.

    Returns:
        Dict with SUPPORTED_FIELDS keys mapped from VDJ tags.
    """
    tags = song.tags
    if tags is None:
        return {f: None for f in SUPPORTED_FIELDS}

    return {
        "title": tags.title,
        "artist": tags.author,
        "album": tags.album,
        "genre": tags.genre,
        "year": str(tags.year) if tags.year else None,
        "track_number": str(tags.track_number) if tags.track_number else None,
        "bpm": str(tags.bpm) if tags.bpm else None,
        "key": tags.key,
        "composer": tags.composer,
        "comment": tags.comment,
    }


def file_tags_to_vdj_kwargs(file_tags: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
    """Map file tags to update_song_tags() kwargs using XML aliases.

    Args:
        file_tags: Dict from FileTagEditor.read_tags().

    Returns:
        Dict of XML alias -> value for update_song_tags().
    """
    mapping = {
        "title": "Title",
        "artist": "Author",
        "album": "Album",
        "genre": "Genre",
        "year": "Year",
        "track_number": "TrackNumber",
        "bpm": "Bpm",
        "key": "Key",
        "composer": "Composer",
        "comment": "Comment",
    }

    result: dict[str, Optional[str]] = {}
    for file_key, vdj_alias in mapping.items():
        value = file_tags.get(file_key)
        if value is not None and value.strip():
            result[vdj_alias] = value.strip()

    return result
