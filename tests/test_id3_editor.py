"""Tests for FileTagEditor — read/write embedded audio file tags."""

from unittest.mock import MagicMock, patch
import pytest

from vdj_manager.core.models import Song, Tags
from vdj_manager.files.id3_editor import (
    FileTagEditor,
    SUPPORTED_FIELDS,
    vdj_tags_to_file_tags,
    file_tags_to_vdj_kwargs,
)

# Patch target: mutagen.File is lazy-imported inside methods as MutagenFile
_MUTAGEN_FILE = "mutagen.File"


class TestFileTagEditorRead:
    """Tests for reading tags from audio files."""

    def test_read_nonexistent_returns_none_values(self):
        """Reading a nonexistent file returns dict with all None values."""
        editor = FileTagEditor()
        with patch(_MUTAGEN_FILE, side_effect=Exception("not found")):
            result = editor.read_tags("/nonexistent/file.mp3")

        assert all(result[f] is None for f in SUPPORTED_FIELDS)

    def test_read_unsupported_format_returns_none_values(self):
        """Reading a file that mutagen returns None for gives all None values."""
        editor = FileTagEditor()
        with patch(_MUTAGEN_FILE, return_value=None):
            result = editor.read_tags("/test/file.xyz")

        assert all(result[f] is None for f in SUPPORTED_FIELDS)

    def test_read_mp3_extracts_id3_frames(self):
        """Reading MP3 should extract standard ID3 frames."""
        editor = FileTagEditor()

        mock_audio = MagicMock()
        mock_frame = MagicMock()
        mock_frame.text = ["Test Title"]
        mock_audio.tags = {"TIT2": mock_frame}

        with patch(_MUTAGEN_FILE, return_value=mock_audio):
            result = editor.read_tags("/test/song.mp3")

        assert result["title"] == "Test Title"

    def test_read_mp3_extracts_comment(self):
        """Reading MP3 should extract COMM frame for comment."""
        editor = FileTagEditor()

        mock_comm = MagicMock()
        mock_comm.text = ["Great track"]

        # Use a real dict with COMM key
        tags_dict = {"COMM::eng": mock_comm}
        mock_audio = MagicMock()
        mock_audio.tags = tags_dict

        with patch(_MUTAGEN_FILE, return_value=mock_audio):
            result = editor.read_tags("/test/song.mp3")

        assert result["comment"] == "Great track"

    def test_read_flac_extracts_vorbis_comments(self):
        """Reading FLAC should extract Vorbis comment fields."""
        editor = FileTagEditor()

        tags_data = {"artist": ["DJ Test"], "title": ["Flac Track"]}
        mock_audio = MagicMock()
        mock_audio.tags = tags_data

        with patch(_MUTAGEN_FILE, return_value=mock_audio):
            result = editor.read_tags("/test/song.flac")

        assert result["artist"] == "DJ Test"
        assert result["title"] == "Flac Track"


class TestFileTagEditorWrite:
    """Tests for writing tags to audio files."""

    def test_write_mp3_saves_frames(self):
        """Writing to MP3 should set ID3 frames and call save()."""
        editor = FileTagEditor()

        mock_audio = MagicMock()
        mock_audio.tags = MagicMock()
        mock_audio.tags.__contains__ = lambda self, key: False

        with patch(_MUTAGEN_FILE, return_value=mock_audio):
            ok = editor.write_tags("/test/song.mp3", {"title": "New Title", "bpm": "128"})

        assert ok
        mock_audio.save.assert_called_once()

    def test_write_nonexistent_returns_false(self):
        """Writing to a file that can't be opened returns False."""
        editor = FileTagEditor()

        with patch(_MUTAGEN_FILE, side_effect=Exception("fail")):
            ok = editor.write_tags("/nonexistent/file.mp3", {"title": "Test"})

        assert not ok

    def test_write_unsupported_format_returns_false(self):
        """Writing to unsupported format returns False."""
        editor = FileTagEditor()

        mock_audio = MagicMock()
        with patch(_MUTAGEN_FILE, return_value=mock_audio):
            ok = editor.write_tags("/test/file.xyz", {"title": "Test"})

        assert not ok


class TestVDJConversion:
    """Tests for VDJ <-> file tag conversion helpers."""

    def test_vdj_tags_to_file_tags_maps_correctly(self):
        """vdj_tags_to_file_tags should map VDJ fields to file tag fields."""
        song = Song(
            file_path="/music/test.mp3",
            tags=Tags(
                title="My Track",
                author="DJ Test",
                album="Test Album",
                genre="House",
                year=2024,
                bpm=128.0,
                key="Am",
                composer="Comp",
                comment="Nice",
            ),
        )
        result = vdj_tags_to_file_tags(song)

        assert result["title"] == "My Track"
        assert result["artist"] == "DJ Test"
        assert result["album"] == "Test Album"
        assert result["genre"] == "House"
        assert result["year"] == "2024"
        assert result["bpm"] == "128.0"
        assert result["key"] == "Am"
        assert result["composer"] == "Comp"
        assert result["comment"] == "Nice"

    def test_vdj_tags_to_file_tags_skips_none(self):
        """vdj_tags_to_file_tags should return None for missing VDJ fields."""
        song = Song(file_path="/music/test.mp3", tags=Tags(title="Only Title"))
        result = vdj_tags_to_file_tags(song)

        assert result["title"] == "Only Title"
        assert result["artist"] is None
        assert result["album"] is None

    def test_vdj_tags_to_file_tags_no_tags(self):
        """vdj_tags_to_file_tags with no tags returns all None."""
        song = Song(file_path="/music/test.mp3", tags=None)
        result = vdj_tags_to_file_tags(song)

        assert all(v is None for v in result.values())

    def test_file_tags_to_vdj_kwargs_maps_correctly(self):
        """file_tags_to_vdj_kwargs should map file fields to VDJ XML aliases."""
        file_tags = {
            "title": "Track Title",
            "artist": "Artist Name",
            "album": "Album Name",
            "genre": "Techno",
            "year": "2024",
            "track_number": "5",
            "bpm": "130",
            "key": "Cm",
            "composer": "Comp",
            "comment": "Great",
        }
        result = file_tags_to_vdj_kwargs(file_tags)

        assert result["Title"] == "Track Title"
        assert result["Author"] == "Artist Name"
        assert result["Album"] == "Album Name"
        assert result["Genre"] == "Techno"
        assert result["Year"] == "2024"
        assert result["TrackNumber"] == "5"
        assert result["Bpm"] == "130"
        assert result["Key"] == "Cm"
        assert result["Composer"] == "Comp"
        assert result["Comment"] == "Great"

    def test_file_tags_to_vdj_kwargs_skips_none(self):
        """file_tags_to_vdj_kwargs should skip None values."""
        file_tags = {"title": "Track", "artist": None, "genre": ""}
        result = file_tags_to_vdj_kwargs(file_tags)

        assert "Title" in result
        assert "Author" not in result
        assert "Genre" not in result  # Empty string skipped
