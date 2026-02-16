"""Tests for Serato crate writer and name sanitization."""

from pathlib import Path

import pytest

from vdj_manager.export.serato import SeratoCrateWriter


@pytest.fixture
def writer(tmp_path):
    """Create a SeratoCrateWriter with a temp Serato directory."""
    return SeratoCrateWriter(serato_dir=tmp_path / "_Serato_")


class TestCrateNameSanitization:
    """Tests for crate name sanitization in write_crate."""

    def test_normal_name_unchanged(self, writer):
        path = writer.write_crate("My Crate", [])
        assert path.name == "My Crate.crate"

    def test_path_traversal_stripped(self, writer):
        path = writer.write_crate("../../evil", [])
        # File must remain inside the Subcrates directory
        assert path.parent == writer.subcrates_dir
        # Slashes replaced, so no directory traversal possible
        assert "/" not in path.stem
        assert "\\" not in path.stem

    def test_slashes_replaced(self, writer):
        path = writer.write_crate("foo/bar\\baz", [])
        assert "/" not in path.stem
        assert "\\" not in path.stem
        assert path.name == "foo_bar_baz.crate"

    def test_special_chars_replaced(self, writer):
        path = writer.write_crate('a:b*c?"d<e>f|g', [])
        # All unsafe chars should be replaced with _
        assert path.name == "a_b_c__d_e_f_g.crate"

    def test_empty_name_becomes_unnamed(self, writer):
        path = writer.write_crate("", [])
        assert path.name == "unnamed.crate"

    def test_dot_only_becomes_unnamed(self, writer):
        path = writer.write_crate(".", [])
        assert path.name == "unnamed.crate"

    def test_crate_file_written(self, writer):
        path = writer.write_crate("Test", ["/music/song.mp3"])
        assert path.exists()
        content = path.read_bytes()
        # Should contain the Serato crate header
        assert b"vrsn" in content


class TestCrateWriterBasics:
    """Tests for SeratoCrateWriter basic operations."""

    def test_ensure_directories(self, writer):
        writer.ensure_directories()
        assert writer.subcrates_dir.exists()

    def test_encode_path_utf16be(self, writer):
        encoded = writer.encode_path("/music/song.mp3")
        assert encoded == "/music/song.mp3".encode("utf-16-be")

    def test_list_crates_empty(self, writer):
        writer.ensure_directories()
        assert writer.list_crates() == []

    def test_list_crates_after_write(self, writer):
        writer.write_crate("TestCrate", [])
        crates = writer.list_crates()
        assert "TestCrate" in crates
