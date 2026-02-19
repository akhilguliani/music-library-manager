"""Tests for VDJDatabase.update_song_infos and update_song_pois methods."""

import pytest

from vdj_manager.core.database import VDJDatabase


def _create_test_db(tmp_path, songs_xml=""):
    """Create a minimal VDJ database for testing."""
    db_path = tmp_path / "database.xml"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
        '<VirtualDJ_Database Version="2024">\r\n'
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


SONG_WITH_POIS = (
    '  <Song FilePath="/test/song.mp3">\r\n'
    '    <Tags Author="Artist" Title="Song" />\r\n'
    '    <Infos SongLength="240.0" />\r\n'
    '    <Poi Type="cue" Pos="10.5" Name="Intro" Num="1" />\r\n'
    '    <Poi Type="cue" Pos="60.0" Name="Drop" Num="2" />\r\n'
    '    <Poi Type="beatgrid" Pos="0.123" Bpm="0.5" />\r\n'
    "  </Song>\r\n"
)


class TestUpdateSongPois:
    """Tests for update_song_pois method."""

    def test_replaces_cue_pois(self, tmp_path):
        """Should replace cue POIs while preserving beatgrid."""
        db_path = _create_test_db(tmp_path, SONG_WITH_POIS)
        db = VDJDatabase(db_path)
        db.load()

        song = db.get_song("/test/song.mp3")
        assert len(song.cue_points) == 2
        assert song.beatgrid is not None

        new_cues = [
            {"pos": 5.0, "name": "Start", "num": 1},
            {"pos": 45.0, "name": "Bridge", "num": 2},
            {"pos": 90.0, "name": "Outro", "num": 3},
        ]
        result = db.update_song_pois("/test/song.mp3", new_cues)
        assert result is True

        song = db.get_song("/test/song.mp3")
        assert len(song.cue_points) == 3
        assert song.cue_points[0].pos == 5.0
        assert song.cue_points[0].name == "Start"
        assert song.cue_points[2].name == "Outro"
        assert song.beatgrid is not None  # preserved

    def test_enforces_max_8(self, tmp_path):
        """Should enforce max 8 cue points."""
        db_path = _create_test_db(tmp_path, SONG_WITH_POIS)
        db = VDJDatabase(db_path)
        db.load()

        cues = [{"pos": float(i), "name": f"C{i}", "num": i} for i in range(1, 12)]
        db.update_song_pois("/test/song.mp3", cues)

        song = db.get_song("/test/song.mp3")
        assert len(song.cue_points) == 8

    def test_empty_clears_cues(self, tmp_path):
        """Empty list should remove all cue POIs but keep beatgrid."""
        db_path = _create_test_db(tmp_path, SONG_WITH_POIS)
        db = VDJDatabase(db_path)
        db.load()

        db.update_song_pois("/test/song.mp3", [])

        song = db.get_song("/test/song.mp3")
        assert len(song.cue_points) == 0
        assert song.beatgrid is not None

    def test_returns_false_for_unknown_song(self, tmp_path):
        """Should return False for unknown file path."""
        db_path = _create_test_db(tmp_path, SONG_WITH_POIS)
        db = VDJDatabase(db_path)
        db.load()

        assert db.update_song_pois("/nonexistent.mp3", []) is False

    def test_raises_when_not_loaded(self, tmp_path):
        """Should raise RuntimeError when database not loaded."""
        db_path = _create_test_db(tmp_path)
        db = VDJDatabase(db_path)

        with pytest.raises(RuntimeError, match="not loaded"):
            db.update_song_pois("/test/song.mp3", [])

    def test_persists_after_save_reload(self, tmp_path):
        """Changed cues should survive save/reload cycle."""
        db_path = _create_test_db(tmp_path, SONG_WITH_POIS)
        db = VDJDatabase(db_path)
        db.load()

        db.update_song_pois("/test/song.mp3", [{"pos": 15.0, "name": "Saved", "num": 1}])
        db.save()

        db2 = VDJDatabase(db_path)
        db2.load()
        song = db2.get_song("/test/song.mp3")
        assert len(song.cue_points) == 1
        assert song.cue_points[0].pos == 15.0
        assert song.cue_points[0].name == "Saved"
