"""Album art extraction from audio file tags using mutagen."""

from pathlib import Path
from typing import Optional


def extract_album_art(file_path: str) -> Optional[bytes]:
    """Extract embedded album art from an audio file.

    Supports MP3 (ID3 APIC), MP4/M4A (covr), FLAC, OGG.
    Returns raw image bytes (JPEG/PNG) or None.
    """
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(file_path)
        if audio is None:
            return None

        # MP3 (ID3 APIC frames)
        if hasattr(audio, "tags") and audio.tags is not None:
            for key in audio.tags:
                if key.startswith("APIC"):
                    return audio.tags[key].data

        # MP4/M4A (covr atom)
        if hasattr(audio, "tags") and audio.tags is not None:
            covr = audio.tags.get("covr")
            if covr and len(covr) > 0:
                return bytes(covr[0])

        # FLAC (pictures list)
        if hasattr(audio, "pictures"):
            if audio.pictures:
                return audio.pictures[0].data

        # OGG Vorbis (metadata_block_picture)
        if hasattr(audio, "tags") and audio.tags is not None:
            pics = audio.tags.get("metadata_block_picture")
            if pics:
                import base64
                from mutagen.flac import Picture

                pic = Picture(base64.b64decode(pics[0]))
                return pic.data

    except Exception:
        pass

    return None
