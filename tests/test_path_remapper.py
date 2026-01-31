"""Tests for path remapper."""

import pytest
from vdj_manager.files.path_remapper import PathRemapper
from vdj_manager.core.models import Song


class TestPathRemapper:
    def test_default_mappings(self):
        """Test that default mappings are loaded."""
        remapper = PathRemapper()
        assert "D:/Main/" in remapper.mappings
        assert "E:/Main/" in remapper.mappings

    def test_remap_d_drive(self):
        """Test remapping D:/ paths."""
        remapper = PathRemapper()
        result = remapper.remap_path("D:/Main/artist/track.mp3")
        assert result == "/Volumes/MyNVMe/Main/artist/track.mp3"

    def test_remap_e_drive(self):
        """Test remapping E:/ paths."""
        remapper = PathRemapper()
        result = remapper.remap_path("E:/Main/artist/track.mp3")
        assert result == "/Volumes/MyNVMe/Main/artist/track.mp3"

    def test_remap_backslashes(self):
        """Test that backslashes are handled."""
        remapper = PathRemapper()
        result = remapper.remap_path("D:\\Main\\artist\\track.mp3")
        assert result == "/Volumes/MyNVMe/Main/artist/track.mp3"

    def test_no_mapping_found(self):
        """Test when no mapping exists."""
        remapper = PathRemapper()
        result = remapper.remap_path("X:/Unknown/track.mp3")
        assert result is None

    def test_add_custom_mapping(self):
        """Test adding custom mapping."""
        remapper = PathRemapper()
        remapper.add_mapping("X:/Custom/", "/Volumes/Custom/")
        result = remapper.remap_path("X:/Custom/track.mp3")
        assert result == "/Volumes/Custom/track.mp3"

    def test_can_remap(self):
        """Test can_remap check."""
        remapper = PathRemapper()
        assert remapper.can_remap("D:/Main/track.mp3") is True
        assert remapper.can_remap("X:/Unknown/track.mp3") is False

    def test_suggest_mapping(self):
        """Test mapping suggestion."""
        remapper = PathRemapper()
        result = remapper.suggest_mapping("D:/NewFolder/track.mp3")
        assert result == "/Volumes/MyNVMe/NewFolder/track.mp3"

    def test_detect_windows_prefixes(self):
        """Test Windows prefix detection."""
        songs = [
            Song(FilePath="D:/Main/track1.mp3"),
            Song(FilePath="D:/Main/track2.mp3"),
            Song(FilePath="E:/Other/track3.mp3"),
            Song(FilePath="/local/track4.mp3"),  # Not Windows
        ]

        remapper = PathRemapper()
        prefixes = remapper.detect_windows_prefixes(iter(songs))

        assert "D:/Main/" in prefixes
        assert "E:/Other/" in prefixes
        assert len(prefixes["D:/Main/"]) == 2
