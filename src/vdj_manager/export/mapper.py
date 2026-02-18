"""VirtualDJ to Serato metadata mapping."""

from ..core.models import Poi, PoiType, Song


class VDJToSeratoMapper:
    """Map VirtualDJ metadata to Serato format."""

    # Serato cue point colors (hex values)
    SERATO_COLORS = [
        "CC0000",  # Red
        "CC4400",  # Orange
        "CC8800",  # Yellow-Orange
        "CCCC00",  # Yellow
        "88CC00",  # Yellow-Green
        "00CC00",  # Green
        "00CC88",  # Green-Blue
        "00CCCC",  # Cyan
        "0088CC",  # Light Blue
        "0000CC",  # Blue
        "8800CC",  # Purple
        "CC00CC",  # Magenta
    ]

    def convert_bpm(self, vdj_bpm: float) -> float:
        """Convert VDJ BPM fraction to actual BPM.

        VDJ stores BPM as seconds per beat (fraction of 60).
        e.g., 0.5 = 120 BPM (60 / 0.5 = 120)

        Args:
            vdj_bpm: VDJ BPM value (fraction)

        Returns:
            Actual BPM value
        """
        if vdj_bpm <= 0:
            return 0.0
        return round(60.0 / vdj_bpm, 2)

    def convert_cue_position(self, pos_seconds: float) -> int:
        """Convert cue point position from seconds to milliseconds.

        Args:
            pos_seconds: Position in seconds

        Returns:
            Position in milliseconds
        """
        return int(pos_seconds * 1000)

    def convert_key(self, vdj_key: str | None) -> str | None:
        """Convert VDJ key notation to Serato-compatible format.

        VDJ and Serato both support standard key notation (Am, Gb, etc.)
        and Camelot notation (8A, 9B, etc.)

        Args:
            vdj_key: VDJ key string

        Returns:
            Serato-compatible key string
        """
        if not vdj_key:
            return None

        # VDJ might store as "Am" or "8A" - both work in Serato
        return vdj_key.strip()

    def map_cue_point(self, poi: Poi, index: int = 0) -> dict:
        """Map a VDJ cue point to Serato format.

        Args:
            poi: VDJ Poi object
            index: Cue point index (0-7)

        Returns:
            Dict with Serato cue point data
        """
        color = self.SERATO_COLORS[index % len(self.SERATO_COLORS)]

        return {
            "index": index,
            "position_ms": self.convert_cue_position(poi.pos),
            "position_sec": poi.pos,
            "name": poi.name or f"Cue {index + 1}",
            "color": color,
            "type": "cue",
        }

    def map_loop(self, poi: Poi, index: int = 0) -> dict:
        """Map a VDJ loop to Serato format.

        Args:
            poi: VDJ Poi object with loop data
            index: Loop index

        Returns:
            Dict with Serato loop data
        """
        start_ms = self.convert_cue_position(poi.pos)
        length_ms = self.convert_cue_position(poi.size) if poi.size else 0

        return {
            "index": index,
            "start_ms": start_ms,
            "end_ms": start_ms + length_ms,
            "name": poi.name or f"Loop {index + 1}",
            "locked": True,
            "type": "loop",
        }

    def map_song(self, song: Song) -> dict:
        """Map all metadata from a VDJ song to Serato format.

        Args:
            song: VDJ Song object

        Returns:
            Dict with all Serato-compatible metadata
        """
        result = {
            "file_path": song.file_path,
            "bpm": None,
            "key": None,
            "artist": None,
            "title": None,
            "album": None,
            "genre": None,
            "comment": None,
            "energy": None,
            "cue_points": [],
            "loops": [],
            "beatgrid": None,
        }

        # Basic metadata from tags
        if song.tags:
            result["artist"] = song.tags.author
            result["title"] = song.tags.title
            result["album"] = song.tags.album
            result["genre"] = song.tags.genre

            # Energy to comment
            if song.tags.energy_level:
                result["energy"] = song.tags.energy_level
                result["comment"] = f"Energy: {song.tags.energy_level}"

            # Original comment
            if song.tags.comment and not result["comment"]:
                result["comment"] = song.tags.comment

        # BPM and key from scan
        if song.scan:
            if song.scan.bpm:
                result["bpm"] = self.convert_bpm(song.scan.bpm)
            if song.scan.key:
                result["key"] = self.convert_key(song.scan.key)

        # Cue points and loops
        cue_index = 0
        loop_index = 0

        for poi in song.pois:
            if poi.type == PoiType.CUE:
                if cue_index < 8:  # Serato supports 8 cue points
                    result["cue_points"].append(self.map_cue_point(poi, cue_index))
                    cue_index += 1

            elif poi.type == PoiType.LOOP:
                if loop_index < 8:  # Serato supports 8 loops
                    result["loops"].append(self.map_loop(poi, loop_index))
                    loop_index += 1

            elif poi.type == PoiType.BEATGRID:
                result["beatgrid"] = {
                    "position_ms": self.convert_cue_position(poi.pos),
                    "bpm": self.convert_bpm(poi.bpm) if poi.bpm else result["bpm"],
                }

        return result

    def generate_serato_markers(self, song: Song) -> bytes:
        """Generate Serato Markers2 binary data for a song.

        This creates the binary data that goes in the GEOB tag
        for MP3 files or equivalent for other formats.

        Args:
            song: VDJ Song object

        Returns:
            Binary data for Serato Markers2 tag
        """
        # This is a simplified version - full implementation would use
        # the serato-tools library or implement the full binary format
        self.map_song(song)

        # For now, return empty markers - full implementation in serato.py
        return b""
