"""Pydantic models for VirtualDJ database structures."""

from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, computed_field


class PoiType(str, Enum):
    """Types of Point of Interest markers in VDJ."""
    CUE = "cue"
    BEATGRID = "beatgrid"
    LOOP = "loop"
    REMIX = "remix"
    AUTOMIX = "automix"


class Poi(BaseModel):
    """Point of Interest marker (cue points, loops, beatgrid, etc.)."""
    type: PoiType = Field(alias="Type")
    pos: float = Field(alias="Pos", description="Position in seconds")
    name: Optional[str] = Field(default=None, alias="Name")
    num: Optional[int] = Field(default=None, alias="Num", description="Cue point number (1-8)")
    size: Optional[float] = Field(default=None, alias="Size", description="Loop size in seconds")
    point: Optional[float] = Field(default=None, alias="Point")
    bpm: Optional[float] = Field(default=None, alias="Bpm", description="Local BPM at this position")

    model_config = {"populate_by_name": True}


class Tags(BaseModel):
    """Song metadata tags."""
    author: Optional[str] = Field(default=None, alias="Author")
    title: Optional[str] = Field(default=None, alias="Title")
    genre: Optional[str] = Field(default=None, alias="Genre")
    album: Optional[str] = Field(default=None, alias="Album")
    track_number: Optional[int] = Field(default=None, alias="TrackNumber")
    year: Optional[int] = Field(default=None, alias="Year")
    composer: Optional[str] = Field(default=None, alias="Composer")
    grouping: Optional[str] = Field(default=None, alias="Grouping", description="Used for Energy tags")
    remix: Optional[str] = Field(default=None, alias="Remix")
    label: Optional[str] = Field(default=None, alias="Label")
    comment: Optional[str] = Field(default=None, alias="Comment", description="Often contains Camelot key")
    bpm: Optional[float] = Field(default=None, alias="Bpm", description="User-set BPM")
    key: Optional[str] = Field(default=None, alias="Key", description="User-set key")
    color: Optional[str] = Field(default=None, alias="Color")
    rating: Optional[int] = Field(default=None, alias="Rating", description="0-5 star rating")
    flag: Optional[int] = Field(default=None, alias="Flag")
    user2: Optional[str] = Field(default=None, alias="User2", description="Hashtag-based style/mood tags")

    model_config = {"populate_by_name": True}

    @computed_field
    @property
    def energy_level(self) -> Optional[int]:
        """Extract energy level from Grouping field.

        Supports both plain number format ("7") and legacy "Energy 7" format.
        """
        if not self.grouping:
            return None
        text = self.grouping.strip()
        # Plain number format (preferred)
        if text.isdigit():
            val = int(text)
            if 1 <= val <= 10:
                return val
        # Legacy "Energy N" format
        grouping_lower = text.lower()
        if "energy" in grouping_lower:
            parts = text.split()
            for i, part in enumerate(parts):
                if part.lower() == "energy" and i + 1 < len(parts):
                    try:
                        return int(parts[i + 1])
                    except ValueError:
                        pass
        return None


class Infos(BaseModel):
    """Technical information about the audio file."""
    song_length: Optional[float] = Field(default=None, alias="SongLength", description="Duration in seconds")
    first_seen: Optional[int] = Field(default=None, alias="FirstSeen", description="Unix timestamp")
    last_played: Optional[int] = Field(default=None, alias="LastPlay", description="Unix timestamp")
    play_count: Optional[int] = Field(default=None, alias="PlayCount")
    bitrate: Optional[int] = Field(default=None, alias="Bitrate", description="Bitrate in kbps")
    cover: Optional[str] = Field(default=None, alias="Cover", description="Cover art path or base64")

    model_config = {"populate_by_name": True}


class Scan(BaseModel):
    """VDJ audio analysis results."""
    bpm: Optional[float] = Field(default=None, alias="Bpm", description="BPM as fraction of 60")
    key: Optional[str] = Field(default=None, alias="Key", description="Detected key")
    volume: Optional[float] = Field(default=None, alias="Volume", description="Gain adjustment")
    flag: Optional[int] = Field(default=None, alias="Flag")

    model_config = {"populate_by_name": True}

    @computed_field
    @property
    def actual_bpm(self) -> Optional[float]:
        """Convert VDJ BPM fraction to actual BPM (e.g., 0.5 -> 120)."""
        if self.bpm is None or self.bpm == 0:
            return None
        return 60.0 / self.bpm


class Link(BaseModel):
    """Link to related songs (stems, remixes, etc.)."""
    source: str = Field(alias="Source")

    model_config = {"populate_by_name": True}


class Song(BaseModel):
    """Complete VirtualDJ song entry."""
    file_path: str = Field(alias="FilePath")
    file_size: Optional[int] = Field(default=None, alias="FileSize")
    tags: Optional[Tags] = None
    infos: Optional[Infos] = None
    scan: Optional[Scan] = None
    pois: list[Poi] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @computed_field
    @property
    def path(self) -> Path:
        """Return file path as Path object."""
        return Path(self.file_path)

    @computed_field
    @property
    def extension(self) -> str:
        """Return lowercase file extension."""
        return Path(self.file_path).suffix.lower()

    @computed_field
    @property
    def is_windows_path(self) -> bool:
        """Check if path is a Windows path."""
        return len(self.file_path) > 1 and self.file_path[1] == ":"

    @computed_field
    @property
    def is_netsearch(self) -> bool:
        """Check if this is a streaming/netsearch entry."""
        return "://" in self.file_path and not self.file_path.startswith("file://")

    @computed_field
    @property
    def display_name(self) -> str:
        """Return display name (artist - title or filename)."""
        if self.tags:
            if self.tags.author and self.tags.title:
                return f"{self.tags.author} - {self.tags.title}"
            if self.tags.title:
                return self.tags.title
        return Path(self.file_path).stem

    @property
    def energy(self) -> Optional[int]:
        """Get energy level from tags."""
        return self.tags.energy_level if self.tags else None

    @property
    def mood(self) -> Optional[str]:
        """Get mood from User2 hashtags (last hashtag added by mood analysis)."""
        if not self.tags or not self.tags.user2:
            return None
        # User2 contains space-separated hashtags like "#ClearBeat #Mellow #happy"
        # Mood tags are lowercase hashtags added by the analyzer
        hashtags = self.tags.user2.split()
        mood_tags = [h[1:] for h in hashtags if h.startswith("#") and h[1:].islower()]
        return mood_tags[-1] if mood_tags else None

    @property
    def actual_bpm(self) -> Optional[float]:
        """Get actual BPM value."""
        return self.scan.actual_bpm if self.scan else None

    @property
    def cue_points(self) -> list[Poi]:
        """Get cue point markers."""
        return [p for p in self.pois if p.type == PoiType.CUE]

    @property
    def loops(self) -> list[Poi]:
        """Get loop markers."""
        return [p for p in self.pois if p.type == PoiType.LOOP]

    @property
    def beatgrid(self) -> Optional[Poi]:
        """Get beatgrid marker."""
        for p in self.pois:
            if p.type == PoiType.BEATGRID:
                return p
        return None


class Playlist(BaseModel):
    """VirtualDJ playlist (MyList)."""
    name: str = Field(alias="Name")
    file_paths: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class DatabaseStats(BaseModel):
    """Statistics about a VDJ database."""
    total_songs: int = 0
    local_files: int = 0
    windows_paths: int = 0
    netsearch: int = 0
    with_energy: int = 0
    with_cue_points: int = 0
    audio_files: int = 0
    non_audio_files: int = 0
    missing_files: int = 0

    # Path breakdowns
    windows_c_paths: int = 0
    windows_d_paths: int = 0
    windows_e_paths: int = 0

    # Location breakdowns
    mac_home_paths: int = 0
    mynvme_paths: int = 0
