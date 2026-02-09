"""Tests for VDJDatabase.update_song_infos method."""

import tempfile
from pathlib import Path

import pytest
from lxml import etree

from vdj_manager.core.database import VDJDatabase


def _create_test_db(tmp_path, songs_xml=""):
    """Create a minimal VDJ database for testing."""
    db_path = tmp_path / "database.xml"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
        "<VirtualDJ_Database Version=\"2024\">\r\n"
        f"{songs_xml}"
        "</VirtualDJ_Database>\r\n"
    )
    db_path.write_text(xml, encoding="utf-8")
    return db_path


class TestUpdateSongInfos:
    """Tests for update_song_infos method."""

    def test_update_play_count(self, tmp_path):
        """Should update PlayCount in XML and in-memory model."""
        db_path = _create_test_db(
            tmp_path,
            '  <Song FilePath="/test/song.mp3">\r\n'
            '    <Tags Author="Artist" Title="Song" />\r\n'
            '    <Infos SongLength="240.5" PlayCount="3" />\r\n'
            "  </Song>\r\n",
        )
        db = VDJDatabase(db_path)
        db.load()

        result = db.update_song_infos("/test/song.mp3", PlayCount=4)
        assert result is True

        # Check in-memory model
        song = db.get_song("/test/song.mp3")
        assert song.infos.play_count == 4

    def test_update_last_played(self, tmp_path):
        """Should update LastPlay timestamp."""
        db_path = _create_test_db(
            tmp_path,
            '  <Song FilePath="/test/song.mp3">\r\n'
            '    <Infos SongLength="180.0" />\r\n'
            "  </Song>\r\n",
        )
        db = VDJDatabase(db_path)
        db.load()

        result = db.update_song_infos("/test/song.mp3", LastPlay=1700000000)
        assert result is True

        song = db.get_song("/test/song.mp3")
        assert song.infos.last_played == 1700000000

    def test_creates_infos_element_if_missing(self, tmp_path):
        """Should create Infos element when it doesn't exist."""
        db_path = _create_test_db(
            tmp_path,
            '  <Song FilePath="/test/bare.mp3">\r\n'
            '    <Tags Author="Artist" />\r\n'
            "  </Song>\r\n",
        )
        db = VDJDatabase(db_path)
        db.load()

        result = db.update_song_infos("/test/bare.mp3", PlayCount=1, LastPlay=1700000000)
        assert result is True

        song = db.get_song("/test/bare.mp3")
        assert song.infos is not None
        assert song.infos.play_count == 1

    def test_returns_false_for_unknown_song(self, tmp_path):
        """Should return False when file_path not found."""
        db_path = _create_test_db(tmp_path)
        db = VDJDatabase(db_path)
        db.load()

        result = db.update_song_infos("/nonexistent.mp3", PlayCount=1)
        assert result is False

    def test_raises_when_not_loaded(self, tmp_path):
        """Should raise RuntimeError when database not loaded."""
        db_path = _create_test_db(tmp_path)
        db = VDJDatabase(db_path)

        with pytest.raises(RuntimeError, match="not loaded"):
            db.update_song_infos("/test/song.mp3", PlayCount=1)

    def test_persists_to_xml(self, tmp_path):
        """Updated values should persist after save and reload."""
        db_path = _create_test_db(
            tmp_path,
            '  <Song FilePath="/test/song.mp3">\r\n'
            '    <Infos SongLength="200.0" />\r\n'
            "  </Song>\r\n",
        )
        db = VDJDatabase(db_path)
        db.load()

        db.update_song_infos("/test/song.mp3", PlayCount=5, LastPlay=1700000000)
        db.save()

        # Reload and verify
        db2 = VDJDatabase(db_path)
        db2.load()
        song = db2.get_song("/test/song.mp3")
        assert song.infos.play_count == 5
