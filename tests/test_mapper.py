"""Tests for VDJ to Serato mapper."""

import pytest
from vdj_manager.export.mapper import VDJToSeratoMapper
from vdj_manager.core.models import Song, Tags, Scan, Poi, PoiType


class TestVDJToSeratoMapper:
    def test_bpm_conversion(self):
        """Test VDJ BPM fraction to actual BPM."""
        mapper = VDJToSeratoMapper()

        # 0.5 seconds per beat = 120 BPM
        assert mapper.convert_bpm(0.5) == 120.0

        # 0.4 seconds per beat = 150 BPM
        assert mapper.convert_bpm(0.4) == 150.0

        # Edge case
        assert mapper.convert_bpm(0) == 0.0

    def test_cue_position_conversion(self):
        """Test seconds to milliseconds conversion."""
        mapper = VDJToSeratoMapper()

        assert mapper.convert_cue_position(1.0) == 1000
        assert mapper.convert_cue_position(30.5) == 30500
        assert mapper.convert_cue_position(0.123) == 123

    def test_map_cue_point(self):
        """Test cue point mapping."""
        mapper = VDJToSeratoMapper()
        poi = Poi(Type=PoiType.CUE, Pos=10.5, Name="Drop")

        result = mapper.map_cue_point(poi, index=0)

        assert result["index"] == 0
        assert result["position_ms"] == 10500
        assert result["name"] == "Drop"
        assert result["type"] == "cue"

    def test_map_loop(self):
        """Test loop mapping."""
        mapper = VDJToSeratoMapper()
        poi = Poi(Type=PoiType.LOOP, Pos=30.0, Size=8.0, Name="Verse")

        result = mapper.map_loop(poi, index=0)

        assert result["start_ms"] == 30000
        assert result["end_ms"] == 38000  # 30 + 8 seconds
        assert result["name"] == "Verse"
        assert result["type"] == "loop"

    def test_map_song_basic(self):
        """Test basic song mapping."""
        mapper = VDJToSeratoMapper()
        song = Song(
            FilePath="/path/track.mp3",
            tags=Tags(Author="Artist", Title="Title", Grouping="7"),
            scan=Scan(Bpm=0.5, Key="Am"),
        )

        result = mapper.map_song(song)

        assert result["file_path"] == "/path/track.mp3"
        assert result["artist"] == "Artist"
        assert result["title"] == "Title"
        assert result["bpm"] == 120.0
        assert result["key"] == "Am"
        assert result["energy"] == 7
        assert "Energy: 7" in result["comment"]

    def test_map_song_with_cues(self):
        """Test song mapping with cue points."""
        mapper = VDJToSeratoMapper()
        song = Song(
            FilePath="/path/track.mp3",
            pois=[
                Poi(Type=PoiType.CUE, Pos=0.0, Num=1),
                Poi(Type=PoiType.CUE, Pos=30.0, Num=2),
                Poi(Type=PoiType.BEATGRID, Pos=0.5, Bpm=0.5),
            ],
        )

        result = mapper.map_song(song)

        assert len(result["cue_points"]) == 2
        assert result["cue_points"][0]["position_ms"] == 0
        assert result["cue_points"][1]["position_ms"] == 30000
        assert result["beatgrid"]["bpm"] == 120.0
