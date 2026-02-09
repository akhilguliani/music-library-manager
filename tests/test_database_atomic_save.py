"""Tests for atomic database save to prevent corruption."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from lxml import etree

from vdj_manager.core.database import VDJDatabase


@pytest.fixture
def db_with_song(tmp_path):
    """Create a minimal VDJ database with one song."""
    db_path = tmp_path / "database.xml"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
        '<VirtualDJ_Database Version="2024">\r\n'
        '  <Song FilePath="/test/song.mp3">\r\n'
        '    <Tags Author="Artist" Title="Title" />\r\n'
        '  </Song>\r\n'
        '</VirtualDJ_Database>\r\n'
    )
    db_path.write_bytes(xml.encode("utf-8"))
    db = VDJDatabase(db_path)
    db.load()
    return db


class TestAtomicSave:
    """Tests for atomic save via temp file + os.replace."""

    def test_save_produces_valid_file(self, db_with_song):
        """Save should produce a valid, readable database file."""
        db_with_song.save()
        # Reload and verify
        db2 = VDJDatabase(db_with_song.db_path)
        db2.load()
        assert len(db2.songs) > 0

    def test_save_uses_atomic_replace(self, db_with_song):
        """Save should write to .tmp then os.replace to the target path."""
        with patch("vdj_manager.core.database.os.replace", wraps=os.replace) as mock_replace:
            db_with_song.save()
            mock_replace.assert_called_once()
            args = mock_replace.call_args[0]
            assert args[0].endswith(".xml.tmp")
            assert args[1] == str(db_with_song.db_path)

    def test_save_cleans_up_temp_on_failure(self, db_with_song, tmp_path):
        """If os.replace fails, temp file should be cleaned up."""
        tmp_file = db_with_song.db_path.with_suffix(".xml.tmp")

        with patch("vdj_manager.core.database.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                db_with_song.save()

        # Temp file should be cleaned up
        assert not tmp_file.exists()
        # Original file should still exist and be valid
        assert db_with_song.db_path.exists()

    def test_save_does_not_corrupt_on_write_failure(self, db_with_song):
        """Original database should remain intact if save fails mid-write."""
        # Read original content
        original_content = db_with_song.db_path.read_bytes()

        # Make write_bytes fail on the temp file
        with patch.object(Path, "write_bytes", side_effect=IOError("write failed")):
            with pytest.raises(IOError):
                db_with_song.save()

        # Original file should be unchanged
        assert db_with_song.db_path.read_bytes() == original_content

    def test_no_temp_file_left_after_successful_save(self, db_with_song):
        """After a successful save, no .xml.tmp file should remain."""
        db_with_song.save()
        tmp_file = db_with_song.db_path.with_suffix(".xml.tmp")
        assert not tmp_file.exists()
