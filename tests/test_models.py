"""Tests for Pydantic models."""

import pytest
from vdj_manager.core.models import Song, Tags, Scan, Poi, PoiType, DatabaseStats


class TestTags:
    def test_energy_extraction_plain_number(self):
        """Test energy level extraction from plain number format."""
        tags = Tags(Grouping="7")
        assert tags.energy_level == 7

        tags = Tags(Grouping="10")
        assert tags.energy_level == 10

        tags = Tags(Grouping="1")
        assert tags.energy_level == 1

    def test_energy_extraction_legacy_format(self):
        """Test energy level extraction from legacy 'Energy N' format."""
        tags = Tags(Grouping="Energy 7")
        assert tags.energy_level == 7

        tags = Tags(Grouping="Energy 10")
        assert tags.energy_level == 10

        tags = Tags(Grouping="energy 5")  # lowercase
        assert tags.energy_level == 5

    def test_energy_extraction_no_energy(self):
        """Test when no energy in Grouping."""
        tags = Tags(Grouping="Some other value")
        assert tags.energy_level is None

        tags = Tags(Grouping=None)
        assert tags.energy_level is None

    def test_energy_extraction_invalid_value(self):
        """Test with invalid energy value."""
        tags = Tags(Grouping="Energy abc")
        assert tags.energy_level is None

    def test_energy_extraction_out_of_range(self):
        """Test plain number out of 1-10 range."""
        tags = Tags(Grouping="0")
        assert tags.energy_level is None

        tags = Tags(Grouping="11")
        assert tags.energy_level is None


class TestScan:
    def test_bpm_conversion(self):
        """Test VDJ BPM fraction to actual BPM conversion."""
        scan = Scan(Bpm=0.5)  # 0.5 = 120 BPM
        assert scan.actual_bpm == 120.0

        scan = Scan(Bpm=0.571429)  # ~105 BPM
        assert abs(scan.actual_bpm - 105.0) < 0.1

    def test_bpm_zero(self):
        """Test with zero BPM."""
        scan = Scan(Bpm=0)
        assert scan.actual_bpm is None

        scan = Scan(Bpm=None)
        assert scan.actual_bpm is None


class TestPoi:
    def test_cue_point(self):
        """Test cue point creation."""
        poi = Poi(Type=PoiType.CUE, Pos=10.5, Name="Drop", Num=1)
        assert poi.type == PoiType.CUE
        assert poi.pos == 10.5
        assert poi.name == "Drop"
        assert poi.num == 1

    def test_loop(self):
        """Test loop marker."""
        poi = Poi(Type=PoiType.LOOP, Pos=30.0, Size=8.0)
        assert poi.type == PoiType.LOOP
        assert poi.size == 8.0


class TestSong:
    def test_windows_path_detection(self):
        """Test Windows path detection."""
        song = Song(FilePath="E:/Music/track.mp3")
        assert song.is_windows_path is True

        song = Song(FilePath="/Users/user/Music/track.mp3")
        assert song.is_windows_path is False

    def test_netsearch_detection(self):
        """Test netsearch/streaming detection."""
        song = Song(FilePath="netsearch://spotify/track123")
        assert song.is_netsearch is True

        song = Song(FilePath="/local/file.mp3")
        assert song.is_netsearch is False

    def test_extension(self):
        """Test extension extraction."""
        song = Song(FilePath="/path/to/track.MP3")
        assert song.extension == ".mp3"

        song = Song(FilePath="/path/to/track.FLAC")
        assert song.extension == ".flac"

    def test_display_name_with_tags(self):
        """Test display name generation."""
        song = Song(
            FilePath="/path/track.mp3",
            tags=Tags(Author="Artist", Title="Song Title"),
        )
        assert song.display_name == "Artist - Song Title"

    def test_display_name_fallback(self):
        """Test display name fallback to filename."""
        song = Song(FilePath="/path/My Track.mp3")
        assert song.display_name == "My Track"

    def test_cue_points_filter(self):
        """Test cue points filtering."""
        song = Song(
            FilePath="/path/track.mp3",
            pois=[
                Poi(Type=PoiType.CUE, Pos=0.0),
                Poi(Type=PoiType.BEATGRID, Pos=0.5),
                Poi(Type=PoiType.CUE, Pos=30.0),
            ],
        )
        assert len(song.cue_points) == 2
        assert len(song.loops) == 0


class TestDatabaseStats:
    def test_default_values(self):
        """Test default statistics values."""
        stats = DatabaseStats()
        assert stats.total_songs == 0
        assert stats.with_energy == 0
        assert stats.missing_files == 0
