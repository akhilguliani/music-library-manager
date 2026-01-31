"""Tests for VDJ database parser."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from lxml import etree

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song, Tags, Scan, Poi, PoiType


SAMPLE_DB_XML = """<?xml version="1.0" encoding="utf-8"?>
<VirtualDJ_Database Version="8">
 <Song FilePath="/path/to/track1.mp3" FileSize="5000000">
  <Tags Author="Artist One" Title="Track One" Genre="Dance" Grouping="Energy 7" />
  <Infos SongLength="180.5" Bitrate="320" />
  <Scan Bpm="0.5" Key="Am" Volume="1.0" />
  <Poi Type="cue" Pos="0.5" Num="1" Name="Intro" />
  <Poi Type="cue" Pos="30.0" Num="2" Name="Drop" />
  <Poi Type="beatgrid" Pos="0.0" Bpm="0.5" />
 </Song>
 <Song FilePath="/path/to/track2.mp3" FileSize="4000000">
  <Tags Author="Artist Two" Title="Track Two" />
  <Scan Bpm="0.4" Key="Cm" />
 </Song>
 <Song FilePath="D:/Windows/track3.mp3" FileSize="3000000">
  <Tags Author="Artist Three" Title="Track Three" />
 </Song>
 <Song FilePath="netsearch://spotify/track123" FileSize="0">
  <Tags Title="Streaming Track" />
 </Song>
</VirtualDJ_Database>
"""


@pytest.fixture
def temp_db_file():
    """Create a temporary database file for testing."""
    with NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(SAMPLE_DB_XML)
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


class TestVDJDatabase:
    def test_load_database(self, temp_db_file):
        """Test loading a database file."""
        db = VDJDatabase(temp_db_file)
        db.load()

        assert db.is_loaded
        assert len(db.songs) == 4

    def test_parse_song_with_full_metadata(self, temp_db_file):
        """Test parsing song with complete metadata."""
        db = VDJDatabase(temp_db_file)
        db.load()

        song = db.get_song("/path/to/track1.mp3")
        assert song is not None
        assert song.file_size == 5000000

        # Tags
        assert song.tags.author == "Artist One"
        assert song.tags.title == "Track One"
        assert song.tags.genre == "Dance"
        assert song.tags.grouping == "Energy 7"
        assert song.energy == 7

        # Scan
        assert song.scan.bpm == 0.5
        assert song.scan.actual_bpm == 120.0
        assert song.scan.key == "Am"

        # Pois
        assert len(song.pois) == 3
        assert len(song.cue_points) == 2
        assert song.beatgrid is not None

    def test_parse_windows_path(self, temp_db_file):
        """Test parsing Windows path detection."""
        db = VDJDatabase(temp_db_file)
        db.load()

        song = db.get_song("D:/Windows/track3.mp3")
        assert song is not None
        assert song.is_windows_path

    def test_parse_netsearch(self, temp_db_file):
        """Test parsing netsearch/streaming entries."""
        db = VDJDatabase(temp_db_file)
        db.load()

        song = db.get_song("netsearch://spotify/track123")
        assert song is not None
        assert song.is_netsearch

    def test_get_stats(self, temp_db_file):
        """Test database statistics calculation."""
        db = VDJDatabase(temp_db_file)
        db.load()

        stats = db.get_stats(check_existence=False)

        assert stats.total_songs == 4
        assert stats.windows_paths == 1
        assert stats.netsearch == 1
        assert stats.with_energy == 1
        assert stats.with_cue_points == 1

    def test_update_song_tags(self, temp_db_file):
        """Test updating song tags."""
        db = VDJDatabase(temp_db_file)
        db.load()

        result = db.update_song_tags("/path/to/track2.mp3", Grouping="Energy 5")
        assert result

        song = db.get_song("/path/to/track2.mp3")
        assert song.tags.grouping == "Energy 5"

    def test_remap_path(self, temp_db_file):
        """Test path remapping."""
        db = VDJDatabase(temp_db_file)
        db.load()

        old_path = "D:/Windows/track3.mp3"
        new_path = "/Volumes/MyNVMe/Windows/track3.mp3"

        result = db.remap_path(old_path, new_path)
        assert result

        # Old path should not exist
        assert db.get_song(old_path) is None
        # New path should exist
        assert db.get_song(new_path) is not None

    def test_remove_song(self, temp_db_file):
        """Test removing a song."""
        db = VDJDatabase(temp_db_file)
        db.load()

        initial_count = len(db.songs)
        result = db.remove_song("/path/to/track2.mp3")

        assert result
        assert len(db.songs) == initial_count - 1
        assert db.get_song("/path/to/track2.mp3") is None

    def test_add_song(self, temp_db_file):
        """Test adding a new song."""
        db = VDJDatabase(temp_db_file)
        db.load()

        initial_count = len(db.songs)
        db.add_song("/path/to/new_track.mp3", file_size=6000000)

        assert len(db.songs) == initial_count + 1
        song = db.get_song("/path/to/new_track.mp3")
        assert song is not None
        assert song.file_size == 6000000

    def test_save_and_reload(self, temp_db_file):
        """Test saving and reloading database."""
        db = VDJDatabase(temp_db_file)
        db.load()

        # Make changes
        db.update_song_tags("/path/to/track1.mp3", Grouping="Energy 10")
        db.save()

        # Reload
        db2 = VDJDatabase(temp_db_file)
        db2.load()

        song = db2.get_song("/path/to/track1.mp3")
        assert song.tags.grouping == "Energy 10"

    def test_iter_songs(self, temp_db_file):
        """Test iterating over songs."""
        db = VDJDatabase(temp_db_file)
        db.load()

        songs = list(db.iter_songs())
        assert len(songs) == 4


class TestVDJDatabaseFileNotFound:
    def test_load_nonexistent_file(self):
        """Test loading non-existent file raises error."""
        db = VDJDatabase(Path("/nonexistent/path/database.xml"))

        with pytest.raises(FileNotFoundError):
            db.load()
