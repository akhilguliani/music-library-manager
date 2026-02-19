"""Tests for file validator."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from vdj_manager.core.models import Song
from vdj_manager.files.validator import FileValidator


@pytest.fixture
def temp_audio_file():
    """Create a temporary 'audio' file."""
    with NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"fake audio data")
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


class TestFileValidator:
    def test_is_audio_file(self):
        """Test audio file extension detection."""
        validator = FileValidator()

        assert validator.is_audio_file("/path/to/track.mp3")
        assert validator.is_audio_file("/path/to/track.MP3")
        assert validator.is_audio_file("/path/to/track.flac")
        assert validator.is_audio_file("/path/to/track.wav")
        assert validator.is_audio_file("/path/to/track.m4a")

        assert not validator.is_audio_file("/path/to/file.zip")
        assert validator.is_audio_file("/path/to/track.mp4")

    def test_is_non_audio_file(self):
        """Test non-audio file detection."""
        validator = FileValidator()

        assert validator.is_non_audio_file("/path/to/file.zip")
        assert not validator.is_non_audio_file("/path/to/file.mp4")
        assert validator.is_non_audio_file("/path/to/file.pdf")
        assert validator.is_non_audio_file("/path/to/file.exe")

        assert not validator.is_non_audio_file("/path/to/track.mp3")

    def test_file_exists(self, temp_audio_file):
        """Test file existence check."""
        validator = FileValidator()

        assert validator.file_exists(str(temp_audio_file))
        assert not validator.file_exists("/nonexistent/file.mp3")

        # Windows paths should return False
        assert not validator.file_exists("D:/path/to/file.mp3")

        # Netsearch should return False
        assert not validator.file_exists("netsearch://track123")

    def test_validate_song_local(self, temp_audio_file):
        """Test validating a local song."""
        validator = FileValidator()
        song = Song(FilePath=str(temp_audio_file), FileSize=15)

        result = validator.validate_song(song)

        assert result["is_audio"]
        assert not result["is_non_audio"]
        assert not result["is_windows_path"]
        assert not result["is_netsearch"]
        assert result["exists"]
        assert result["extension"] == ".mp3"

    def test_validate_song_windows(self):
        """Test validating a Windows path song."""
        validator = FileValidator()
        song = Song(FilePath="E:/Music/track.mp3")

        result = validator.validate_song(song)

        assert result["is_audio"]
        assert result["is_windows_path"]
        assert not result["exists"]  # Can't check Windows paths

    def test_validate_song_netsearch(self):
        """Test validating a netsearch song."""
        validator = FileValidator()
        song = Song(FilePath="netsearch://spotify/track123")

        result = validator.validate_song(song)

        assert result["is_netsearch"]
        assert not result["exists"]

    def test_find_missing_files(self, temp_audio_file):
        """Test finding songs with missing files."""
        validator = FileValidator()
        songs = [
            Song(FilePath=str(temp_audio_file)),  # Exists
            Song(FilePath="/nonexistent/file.mp3"),  # Missing
            Song(FilePath="D:/Windows/track.mp3"),  # Windows - skipped
        ]

        missing = validator.find_missing_files(iter(songs))

        assert len(missing) == 1
        assert missing[0].file_path == "/nonexistent/file.mp3"

    def test_find_non_audio_entries(self):
        """Test finding non-audio entries."""
        validator = FileValidator()
        songs = [
            Song(FilePath="/path/track.mp3"),
            Song(FilePath="/path/video.mkv"),
            Song(FilePath="/path/archive.zip"),
            Song(FilePath="netsearch://track"),  # Skipped
        ]

        non_audio = validator.find_non_audio_entries(iter(songs))

        assert len(non_audio) == 2
        paths = [s.file_path for s in non_audio]
        assert "/path/video.mkv" in paths
        assert "/path/archive.zip" in paths

    def test_categorize_entries(self, temp_audio_file):
        """Test categorizing all entries."""
        validator = FileValidator()
        songs = [
            Song(FilePath=str(temp_audio_file)),  # audio_exists
            Song(FilePath="/missing/track.mp3"),  # audio_missing
            Song(FilePath="/path/file.zip"),  # non_audio
            Song(FilePath="D:/Windows/track.mp3"),  # windows_paths
            Song(FilePath="netsearch://track"),  # netsearch
        ]

        categories = validator.categorize_entries(iter(songs))

        assert len(categories["audio_exists"]) == 1
        assert len(categories["audio_missing"]) == 1
        assert len(categories["non_audio"]) == 1
        assert len(categories["windows_paths"]) == 1
        assert len(categories["netsearch"]) == 1

    def test_generate_report(self, temp_audio_file):
        """Test generating validation report."""
        validator = FileValidator()
        songs = [
            Song(FilePath=str(temp_audio_file)),
            Song(FilePath="/missing/track.flac"),
            Song(FilePath="/path/file.zip"),
            Song(FilePath="D:/Windows/track.mp3"),
        ]

        report = validator.generate_report(songs)

        assert report["total"] == 4
        assert report["audio_valid"] == 1
        assert report["audio_missing"] == 1
        assert report["non_audio"] == 1
        assert report["windows_paths"] == 1
        assert ".mp3" in report["extensions"]
        assert ".flac" in report["extensions"]
