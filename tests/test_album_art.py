"""Tests for album art extraction."""

from unittest.mock import patch, MagicMock

import pytest

from vdj_manager.player.album_art import extract_album_art


class TestExtractAlbumArt:
    """Tests for extract_album_art function."""

    def test_mp3_apic_frame(self):
        """Should extract APIC frame data from MP3."""
        mock_apic = MagicMock()
        mock_apic.data = b"\xff\xd8\xff\xe0JPEG_DATA"

        mock_tags = MagicMock()
        mock_tags.__iter__ = MagicMock(return_value=iter(["APIC:"]))
        mock_tags.__getitem__ = MagicMock(return_value=mock_apic)
        mock_tags.startswith = MagicMock()  # Not needed on tags
        mock_tags.get = MagicMock(return_value=None)

        mock_audio = MagicMock()
        mock_audio.tags = mock_tags
        mock_audio.pictures = []

        with patch("mutagen.File", return_value=mock_audio):
            result = extract_album_art("/test.mp3")
            assert result == b"\xff\xd8\xff\xe0JPEG_DATA"

    def test_flac_pictures(self):
        """Should extract picture from FLAC."""
        mock_tags = MagicMock()
        mock_tags.__iter__ = MagicMock(return_value=iter([]))
        mock_tags.get = MagicMock(return_value=None)

        mock_picture = MagicMock()
        mock_picture.data = b"PNG_DATA"

        mock_audio = MagicMock()
        mock_audio.tags = mock_tags
        mock_audio.pictures = [mock_picture]

        with patch("mutagen.File", return_value=mock_audio):
            result = extract_album_art("/test.flac")
            assert result == b"PNG_DATA"

    def test_no_art_returns_none(self):
        """Should return None when no art is embedded."""
        mock_tags = MagicMock()
        mock_tags.__iter__ = MagicMock(return_value=iter([]))
        mock_tags.get = MagicMock(return_value=None)

        mock_audio = MagicMock()
        mock_audio.tags = mock_tags
        mock_audio.pictures = []

        with patch("mutagen.File", return_value=mock_audio):
            result = extract_album_art("/test.mp3")
            assert result is None

    def test_unsupported_file_returns_none(self):
        """Should return None for unreadable files."""
        with patch("mutagen.File", return_value=None):
            result = extract_album_art("/test.xyz")
            assert result is None

    def test_exception_returns_none(self):
        """Should return None on any error."""
        with patch("mutagen.File", side_effect=Exception("bad")):
            result = extract_album_art("/bad.mp3")
            assert result is None
