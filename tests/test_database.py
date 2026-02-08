"""Tests for VDJ database parser."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from lxml import etree

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song, Tags, Scan, Poi, PoiType


SAMPLE_DB_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\r\n'
    '<VirtualDJ_Database Version="8">\r\n'
    ' <Song FilePath="/path/to/track1.mp3" FileSize="5000000">\r\n'
    '  <Tags Author="Artist One" Title="Track One" Genre="Dance" Grouping="Energy 7" />\r\n'
    '  <Infos SongLength="180.5" Bitrate="320" />\r\n'
    '  <Scan Bpm="0.5" Key="Am" Volume="1.0" />\r\n'
    '  <Poi Type="cue" Pos="0.5" Num="1" Name="Intro" />\r\n'
    '  <Poi Type="cue" Pos="30.0" Num="2" Name="Drop" />\r\n'
    '  <Poi Type="beatgrid" Pos="0.0" Bpm="0.5" />\r\n'
    ' </Song>\r\n'
    ' <Song FilePath="/path/to/track2.mp3" FileSize="4000000">\r\n'
    '  <Tags Author="Artist Two" Title="Track Two" />\r\n'
    '  <Scan Bpm="0.4" Key="Cm" />\r\n'
    ' </Song>\r\n'
    ' <Song FilePath="D:/Windows/track3.mp3" FileSize="3000000">\r\n'
    '  <Tags Author="Artist Three" Title="Track Three" />\r\n'
    ' </Song>\r\n'
    ' <Song FilePath="netsearch://spotify/track123" FileSize="0">\r\n'
    '  <Tags Title="Streaming Track" />\r\n'
    ' </Song>\r\n'
    '</VirtualDJ_Database>\r\n'
)


@pytest.fixture
def temp_db_file():
    """Create a temporary database file for testing."""
    with NamedTemporaryFile(mode='wb', suffix='.xml', delete=False) as f:
        f.write(SAMPLE_DB_XML.encode("utf-8"))
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


class TestVDJDatabaseSaveFormat:
    """Tests for VDJ database save format compatibility.

    VirtualDJ database format (verified from actual VDJ-created files):
    - Double quotes in XML declaration
    - UTF-8 encoding (uppercase)
    - CRLF line endings
    - Space before /> in self-closing tags
    - Apostrophes as &apos; entities in attribute values
    - Trailing CRLF after root element
    """

    def test_save_produces_double_quote_declaration(self, temp_db_file):
        """Saved XML declaration must use double quotes."""
        db = VDJDatabase(temp_db_file)
        db.load()
        db.save()

        content = temp_db_file.read_bytes()
        assert content.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')

    def test_save_uses_crlf_line_endings(self, temp_db_file):
        """Saved file must use CRLF line endings."""
        db = VDJDatabase(temp_db_file)
        db.load()
        db.save()

        content = temp_db_file.read_bytes()
        # Every LF should be preceded by CR
        lf_count = content.count(b"\n")
        crlf_count = content.count(b"\r\n")
        assert lf_count == crlf_count
        assert lf_count > 0

    def test_save_has_space_before_self_closing(self, temp_db_file):
        """Self-closing tags must have space before />."""
        db = VDJDatabase(temp_db_file)
        db.load()
        db.save()

        content = temp_db_file.read_text(encoding="utf-8")
        # All /> should be preceded by a space
        assert "/>" in content
        import re
        no_space = re.findall(r'[^ ]/>',  content)
        assert no_space == [], f"Found '/>' without preceding space: {no_space}"

    def test_save_ends_with_crlf(self, temp_db_file):
        """File must end with CRLF."""
        db = VDJDatabase(temp_db_file)
        db.load()
        db.save()

        content = temp_db_file.read_bytes()
        assert content.endswith(b"\r\n")

    def test_save_round_trip_byte_identical(self, temp_db_file):
        """Save should produce byte-identical output for unmodified database."""
        original = temp_db_file.read_bytes()

        db = VDJDatabase(temp_db_file)
        db.load()
        db.save()

        saved = temp_db_file.read_bytes()
        assert original == saved

    def test_save_preserves_apostrophe_entities(self):
        """Apostrophes in attribute values must be saved as &apos;."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\r\n'
            '<VirtualDJ_Database Version="8">\r\n'
            ' <Song FilePath="/path/to/it&apos;s a track.mp3" FileSize="100">\r\n'
            '  <Tags Author="Rock&apos;n Roll" Title="Test" />\r\n'
            ' </Song>\r\n'
            '</VirtualDJ_Database>\r\n'
        )
        with NamedTemporaryFile(mode='wb', suffix='.xml', delete=False) as f:
            f.write(xml.encode("utf-8"))
            tmp = Path(f.name)
        try:
            db = VDJDatabase(tmp)
            db.load()
            db.save()

            content = tmp.read_bytes().decode("utf-8")
            assert "&apos;" in content
            assert "it&apos;s a track" in content
            assert "Rock&apos;n Roll" in content
        finally:
            tmp.unlink(missing_ok=True)

    def test_save_produces_valid_xml(self, temp_db_file):
        """Saved XML can be parsed back successfully."""
        db = VDJDatabase(temp_db_file)
        db.load()
        db.save()

        db2 = VDJDatabase(temp_db_file)
        db2.load()

        assert db2.is_loaded
        assert len(db2.songs) == len(db.songs)

    def test_save_preserves_data_after_modification(self, temp_db_file):
        """Data is preserved after modifying and saving."""
        db = VDJDatabase(temp_db_file)
        db.load()

        db.update_song_tags("/path/to/track1.mp3", Grouping="Energy 9")
        db.save()

        db2 = VDJDatabase(temp_db_file)
        db2.load()

        song = db2.get_song("/path/to/track1.mp3")
        assert song.tags.grouping == "Energy 9"


class TestVDJDatabaseFileNotFound:
    def test_load_nonexistent_file(self):
        """Test loading non-existent file raises error."""
        db = VDJDatabase(Path("/nonexistent/path/database.xml"))

        with pytest.raises(FileNotFoundError):
            db.load()
