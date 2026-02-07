"""Tests for performance fixes across the codebase.

Each test class corresponds to a specific fix from the performance review.
"""

import hashlib
import time
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import patch, MagicMock
from lxml import etree

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song, Tags, Scan, Poi, PoiType
from vdj_manager.files.path_remapper import PathRemapper
from vdj_manager.files.duplicates import DuplicateDetector
from vdj_manager.files.validator import FileValidator
from vdj_manager.normalize.loudness import LoudnessMeasurer


# --- Helpers ---

def _make_db_xml(num_songs: int) -> str:
    """Generate a VDJ database XML string with N songs."""
    songs_xml = []
    for i in range(num_songs):
        songs_xml.append(
            f' <Song FilePath="/path/to/track{i}.mp3" FileSize="{1000 + i}">\n'
            f'  <Tags Author="Artist {i}" Title="Track {i}" Grouping="Energy {(i % 10) + 1}" />\n'
            f'  <Scan Bpm="0.5" Key="Am" />\n'
            f' </Song>'
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<VirtualDJ_Database Version="8">\n'
        + "\n".join(songs_xml) + "\n"
        "</VirtualDJ_Database>"
    )


SAMPLE_DB_XML = _make_db_xml(4)

MERGE_SOURCE_XML = """<?xml version="1.0" encoding="utf-8"?>
<VirtualDJ_Database Version="8">
 <Song FilePath="/path/to/track0.mp3" FileSize="1000">
  <Tags Author="Artist 0" Title="Track 0" Grouping="Energy 9" />
  <Scan Bpm="0.4" Key="Cm" />
 </Song>
 <Song FilePath="/path/to/new_track.mp3" FileSize="9999">
  <Tags Author="New Artist" Title="New Track" Grouping="Energy 5" />
  <Scan Bpm="0.5" Key="Am" />
 </Song>
</VirtualDJ_Database>
"""


@pytest.fixture
def temp_db_file():
    """Create a temporary database file."""
    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(SAMPLE_DB_XML)
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def temp_merge_source():
    """Create a temporary merge source database file."""
    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(MERGE_SOURCE_XML)
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def large_db_file():
    """Create a 1000-song database for performance testing."""
    xml = _make_db_xml(1000)
    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


# --- Fix 1: database.py element index for O(1) lookups ---

class TestDatabaseElementIndex:
    """Tests for Fix 1: filepath-to-element index in database.py."""

    def test_element_index_built_on_load(self, temp_db_file):
        """Verify element index is populated after load."""
        db = VDJDatabase(temp_db_file)
        db.load()

        assert len(db._filepath_to_elem) == len(db.songs)
        for fp in db.songs:
            assert fp in db._filepath_to_elem

    def test_update_tags_uses_index(self, temp_db_file):
        """Verify update_song_tags works correctly via index."""
        db = VDJDatabase(temp_db_file)
        db.load()

        result = db.update_song_tags("/path/to/track1.mp3", Grouping="Energy 8")
        assert result is True

        song = db.get_song("/path/to/track1.mp3")
        assert song.tags.grouping == "Energy 8"

    def test_update_tags_nonexistent_returns_false(self, temp_db_file):
        """Verify update returns False for missing song."""
        db = VDJDatabase(temp_db_file)
        db.load()

        result = db.update_song_tags("/nonexistent.mp3", Grouping="Energy 1")
        assert result is False

    def test_update_scan_uses_index(self, temp_db_file):
        """Verify update_song_scan works correctly via index."""
        db = VDJDatabase(temp_db_file)
        db.load()

        result = db.update_song_scan("/path/to/track0.mp3", Bpm="0.6", Key="Dm")
        assert result is True

    def test_remap_path_updates_index(self, temp_db_file):
        """Verify remap_path keeps element index in sync."""
        db = VDJDatabase(temp_db_file)
        db.load()

        old_path = "/path/to/track0.mp3"
        new_path = "/new/path/track0.mp3"

        assert old_path in db._filepath_to_elem
        result = db.remap_path(old_path, new_path)
        assert result is True

        # Old path removed from index
        assert old_path not in db._filepath_to_elem
        # New path added to index
        assert new_path in db._filepath_to_elem
        # Song lookup works
        assert db.get_song(new_path) is not None
        assert db.get_song(old_path) is None

    def test_remove_song_updates_index(self, temp_db_file):
        """Verify remove_song cleans up element index."""
        db = VDJDatabase(temp_db_file)
        db.load()

        fp = "/path/to/track0.mp3"
        assert fp in db._filepath_to_elem

        result = db.remove_song(fp)
        assert result is True
        assert fp not in db._filepath_to_elem
        assert fp not in db.songs

    def test_add_song_updates_index(self, temp_db_file):
        """Verify add_song adds to element index."""
        db = VDJDatabase(temp_db_file)
        db.load()

        new_fp = "/brand/new/track.mp3"
        db.add_song(new_fp, file_size=5000)

        assert new_fp in db._filepath_to_elem
        assert new_fp in db.songs

    def test_save_and_reload_preserves_index(self, temp_db_file):
        """Verify index is rebuilt correctly after save/reload."""
        db = VDJDatabase(temp_db_file)
        db.load()
        db.update_song_tags("/path/to/track0.mp3", Grouping="Energy 10")
        db.save()

        db2 = VDJDatabase(temp_db_file)
        db2.load()

        assert len(db2._filepath_to_elem) == len(db2.songs)
        song = db2.get_song("/path/to/track0.mp3")
        assert song.tags.grouping == "Energy 10"

    def test_large_db_lookup_performance(self, large_db_file):
        """Verify O(1) lookups on a 1000-song database are fast."""
        db = VDJDatabase(large_db_file)
        db.load()
        assert len(db.songs) == 1000

        # Time 100 update operations
        start = time.perf_counter()
        for i in range(100):
            db.update_song_tags(f"/path/to/track{i}.mp3", Grouping=f"Energy {(i % 10) + 1}")
        elapsed = time.perf_counter() - start

        # Should be well under 1 second for 100 O(1) operations
        assert elapsed < 1.0, f"100 updates took {elapsed:.3f}s (should be <1s)"


# --- Fix 2: database.py O(n) merge_from ---

class TestDatabaseMergeOptimized:
    """Tests for Fix 2: optimized merge_from using element index."""

    def test_merge_adds_new_songs(self, temp_db_file, temp_merge_source):
        """Verify merge adds songs not in the target."""
        db = VDJDatabase(temp_db_file)
        db.load()
        other = VDJDatabase(temp_merge_source)
        other.load()

        initial_count = len(db.songs)
        stats = db.merge_from(other)

        assert stats["added"] == 1  # /path/to/new_track.mp3
        assert len(db.songs) == initial_count + 1
        assert db.get_song("/path/to/new_track.mp3") is not None

    def test_merge_updates_existing_songs(self, temp_db_file, temp_merge_source):
        """Verify merge updates metadata for overlapping songs."""
        db = VDJDatabase(temp_db_file)
        db.load()
        other = VDJDatabase(temp_merge_source)
        other.load()

        stats = db.merge_from(other, prefer_other=True)

        # track0 exists in both, should be updated or skipped depending on metadata
        assert stats["added"] + stats["updated"] + stats["skipped"] == 2

    def test_merge_index_updated_for_new_songs(self, temp_db_file, temp_merge_source):
        """Verify element index is updated for newly merged songs."""
        db = VDJDatabase(temp_db_file)
        db.load()
        other = VDJDatabase(temp_merge_source)
        other.load()

        db.merge_from(other)

        new_fp = "/path/to/new_track.mp3"
        assert new_fp in db._filepath_to_elem
        assert new_fp in db.songs

    def test_merge_preserves_existing_data(self, temp_db_file, temp_merge_source):
        """Verify merge doesn't corrupt existing songs."""
        db = VDJDatabase(temp_db_file)
        db.load()
        other = VDJDatabase(temp_merge_source)
        other.load()

        # Record existing songs before merge
        existing_fps = set(db.songs.keys())

        db.merge_from(other)

        # All originally existing songs should still be present
        for fp in existing_fps:
            assert fp in db.songs


# --- Fix 3: path_remapper.py cached sorted prefixes ---

class TestPathRemapperCachedPrefixes:
    """Tests for Fix 3: cached sorted prefixes in PathRemapper."""

    def test_remap_still_works_with_cache(self):
        """Verify remap produces correct results with caching."""
        remapper = PathRemapper()
        result = remapper.remap_path("D:/Main/artist/track.mp3")
        assert result == "/Volumes/MyNVMe/Main/artist/track.mp3"

    def test_cache_invalidated_on_add_mapping(self):
        """Verify adding a mapping invalidates the cache."""
        remapper = PathRemapper()
        # Trigger cache build
        remapper.remap_path("D:/Main/track.mp3")
        assert remapper._sorted_prefixes is not None

        # Add mapping — should invalidate
        remapper.add_mapping("X:/Custom/", "/Volumes/Custom/")
        assert remapper._sorted_prefixes is None

        # Should work with new mapping
        result = remapper.remap_path("X:/Custom/track.mp3")
        assert result == "/Volumes/Custom/track.mp3"

    def test_cache_invalidated_on_remove_mapping(self):
        """Verify removing a mapping invalidates the cache."""
        remapper = PathRemapper()
        remapper.add_mapping("X:/Test/", "/Volumes/Test/")

        # Trigger cache build
        remapper.remap_path("X:/Test/track.mp3")
        assert remapper._sorted_prefixes is not None

        remapper.remove_mapping("X:/Test/")
        assert remapper._sorted_prefixes is None

        # X:/Test should no longer remap
        assert remapper.remap_path("X:/Test/track.mp3") is None

    def test_longest_prefix_wins(self):
        """Verify longest prefix match is selected (cache order correct)."""
        remapper = PathRemapper(mappings={
            "D:/": "/short/",
            "D:/Music/": "/long/",
            "D:/Music/DJ/": "/longest/",
        })

        assert remapper.remap_path("D:/Music/DJ/track.mp3") == "/longest/track.mp3"
        assert remapper.remap_path("D:/Music/other.mp3") == "/long/other.mp3"
        assert remapper.remap_path("D:/docs/file.txt") == "/short/docs/file.txt"

    def test_repeated_remap_uses_cache(self):
        """Verify cache is reused across multiple remap calls."""
        remapper = PathRemapper()
        remapper.remap_path("D:/Main/track1.mp3")
        cached = remapper._sorted_prefixes
        assert cached is not None

        # Second call should reuse same cache object
        remapper.remap_path("D:/Main/track2.mp3")
        assert remapper._sorted_prefixes is cached


# --- Fix 4: duplicates.py skip full hash for small groups ---

class TestDuplicateHashOptimization:
    """Tests for Fix 4: skip full-hash verification for pairs."""

    def test_pair_skips_full_hash(self):
        """Verify groups of 2 don't trigger full hash computation."""
        detector = DuplicateDetector()

        with TemporaryDirectory() as tmpdir:
            # Create two identical files
            content = b"identical content " * 1000  # > 1KB
            f1 = Path(tmpdir) / "file1.mp3"
            f2 = Path(tmpdir) / "file2.mp3"
            f1.write_bytes(content)
            f2.write_bytes(content)

            songs = [
                Song(FilePath=str(f1), FileSize=len(content)),
                Song(FilePath=str(f2), FileSize=len(content)),
            ]

            # Track compute_file_hash calls
            original_full_hash = DuplicateDetector.compute_file_hash
            full_hash_calls = []

            def tracking_full_hash(path, chunk_size=65536):
                full_hash_calls.append(path)
                return original_full_hash(path, chunk_size)

            with patch.object(DuplicateDetector, "compute_file_hash", side_effect=tracking_full_hash):
                duplicates = detector.find_by_hash(songs, use_partial=True, verify_full=True)

            # Should find 1 duplicate group
            assert len(duplicates) == 1
            assert len(duplicates[0]) == 2
            # Full hash should NOT have been called (group of 2, skipped)
            assert len(full_hash_calls) == 0

    def test_triple_still_verifies_full_hash(self):
        """Verify groups of 3+ still compute full hashes."""
        detector = DuplicateDetector()

        with TemporaryDirectory() as tmpdir:
            content = b"identical content " * 1000
            files = []
            songs = []
            for i in range(3):
                f = Path(tmpdir) / f"file{i}.mp3"
                f.write_bytes(content)
                files.append(f)
                songs.append(Song(FilePath=str(f), FileSize=len(content)))

            original_full_hash = DuplicateDetector.compute_file_hash
            full_hash_calls = []

            def tracking_full_hash(path, chunk_size=65536):
                full_hash_calls.append(path)
                return original_full_hash(path, chunk_size)

            with patch.object(DuplicateDetector, "compute_file_hash", side_effect=tracking_full_hash):
                duplicates = detector.find_by_hash(songs, use_partial=True, verify_full=True)

            assert len(duplicates) == 1
            assert len(duplicates[0]) == 3
            # Full hash SHOULD have been called for group of 3
            assert len(full_hash_calls) == 3

    def test_no_false_positives_with_different_content(self):
        """Verify files with same size but different content aren't grouped."""
        detector = DuplicateDetector()

        with TemporaryDirectory() as tmpdir:
            # Same size, different content
            f1 = Path(tmpdir) / "file1.mp3"
            f2 = Path(tmpdir) / "file2.mp3"
            content1 = b"A" * 2000
            content2 = b"B" * 2000
            f1.write_bytes(content1)
            f2.write_bytes(content2)

            songs = [
                Song(FilePath=str(f1), FileSize=2000),
                Song(FilePath=str(f2), FileSize=2000),
            ]

            duplicates = detector.find_by_hash(songs, use_partial=True, verify_full=True)
            assert len(duplicates) == 0


# --- Fix 5: loudness.py shared JSON parser ---

class TestLoudnessJsonParser:
    """Tests for Fix 5: extracted _parse_ffmpeg_json in LoudnessMeasurer."""

    def test_parse_valid_json(self):
        """Test parsing valid ffmpeg loudnorm JSON output."""
        stderr = """
frame=  100 fps=50 size=N/A time=00:03:30.00 bitrate=N/A
{
    "input_i" : "-14.50",
    "input_tp" : "-1.20",
    "input_lra" : "8.30",
    "input_thresh" : "-25.10"
}
"""
        data = LoudnessMeasurer._parse_ffmpeg_json(stderr)
        assert data is not None
        assert data["input_i"] == "-14.50"
        assert data["input_tp"] == "-1.20"

    def test_parse_no_json(self):
        """Test parsing stderr with no JSON block."""
        stderr = "frame=  100 fps=50 size=N/A\nNo JSON here\n"
        data = LoudnessMeasurer._parse_ffmpeg_json(stderr)
        assert data is None

    def test_parse_malformed_json(self):
        """Test parsing malformed JSON gracefully."""
        stderr = '{\n"input_i": "bad_value",\ntruncated...'
        data = LoudnessMeasurer._parse_ffmpeg_json(stderr)
        # Should return None on parse failure
        assert data is None

    def test_parse_loudnorm_output_missing_input_i(self):
        """Test _parse_loudnorm_output returns None when input_i is missing."""
        measurer = LoudnessMeasurer.__new__(LoudnessMeasurer)
        stderr = '{\n"input_tp": "-1.0"\n}'
        result = measurer._parse_loudnorm_output(stderr)
        assert result is None

    def test_parse_loudnorm_output_valid(self):
        """Test _parse_loudnorm_output returns correct float."""
        measurer = LoudnessMeasurer.__new__(LoudnessMeasurer)
        stderr = '{\n"input_i": "-14.5",\n"input_tp": "-1.0"\n}'
        result = measurer._parse_loudnorm_output(stderr)
        assert result == -14.5

    def test_parse_loudnorm_zero_is_valid(self):
        """Test that 0.0 LUFS is returned correctly (not treated as missing)."""
        measurer = LoudnessMeasurer.__new__(LoudnessMeasurer)
        stderr = '{\n"input_i": "0.0"\n}'
        result = measurer._parse_loudnorm_output(stderr)
        assert result == 0.0

    def test_parse_json_with_prefix_text_on_brace_line(self):
        """Test parsing when { appears after other text on same line."""
        stderr = 'Parsed_loudnorm: {\n"input_i": "-10.0"\n}'
        data = LoudnessMeasurer._parse_ffmpeg_json(stderr)
        assert data is not None
        assert data["input_i"] == "-10.0"


# --- Fix 6: validator.py redundant extension extraction ---

class TestValidatorExtensionOptimization:
    """Tests for Fix 6: single extension extraction in FileValidator."""

    def test_validate_song_returns_correct_extension(self):
        """Verify validate_song includes correct extension."""
        validator = FileValidator()
        song = Song(FilePath="/path/to/track.MP3")

        result = validator.validate_song(song)
        assert result["extension"] == ".mp3"
        assert result["is_audio"] is True
        assert result["is_non_audio"] is False

    def test_validate_non_audio_song(self):
        """Verify non-audio files are correctly identified."""
        validator = FileValidator()
        song = Song(FilePath="/path/to/image.jpg")

        result = validator.validate_song(song)
        assert result["is_audio"] is False
        assert result["is_non_audio"] is True

    def test_generate_report_includes_extensions(self):
        """Verify generate_report collects extension counts in single pass."""
        validator = FileValidator()
        songs = [
            Song(FilePath="/path/track1.mp3"),
            Song(FilePath="/path/track2.mp3"),
            Song(FilePath="/path/track3.flac"),
            Song(FilePath="/path/image.jpg"),
        ]

        report = validator.generate_report(songs)

        assert ".mp3" in report["extensions"]
        assert report["extensions"][".mp3"] == 2
        assert report["extensions"][".flac"] == 1
        assert report["extensions"][".jpg"] == 1
        assert report["total"] == 4

    def test_categorize_entries_without_extensions(self):
        """Verify categorize_entries works without extension collection."""
        validator = FileValidator()
        songs = [
            Song(FilePath="/path/track.mp3"),
            Song(FilePath="netsearch://spotify/abc"),
        ]

        categories = validator.categorize_entries(iter(songs), collect_extensions=False)
        assert "extensions" not in categories

    def test_categorize_entries_with_extensions(self):
        """Verify categorize_entries collects extensions when requested."""
        validator = FileValidator()
        songs = [
            Song(FilePath="/path/track.mp3"),
            Song(FilePath="netsearch://spotify/abc"),
        ]

        categories = validator.categorize_entries(iter(songs), collect_extensions=True)
        assert "extensions" in categories
        assert ".mp3" in categories["extensions"]

    def test_internal_ext_helpers(self):
        """Test the internal _is_audio_ext and _is_non_audio_ext helpers."""
        assert FileValidator._is_audio_ext(".mp3") is True
        assert FileValidator._is_audio_ext(".jpg") is False
        assert FileValidator._is_non_audio_ext(".jpg") is True
        assert FileValidator._is_non_audio_ext(".mp3") is False


# --- Fix 7: loudness.py ffmpeg verification cache ---

class TestFfmpegVerificationCache:
    """Tests for Fix 7: cached ffmpeg verification in LoudnessMeasurer."""

    def setup_method(self):
        """Clear verification cache before each test."""
        LoudnessMeasurer._verified_paths.clear()

    def test_first_creation_verifies(self):
        """Test that first instantiation runs verification."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            LoudnessMeasurer("ffmpeg")

            # Should have called ffmpeg -version
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["ffmpeg", "-version"]

    def test_second_creation_skips_verification(self):
        """Test that second instantiation with same path skips verification."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            LoudnessMeasurer("ffmpeg")
            LoudnessMeasurer("ffmpeg")

            # Should only have been called once
            assert mock_run.call_count == 1

    def test_different_path_verifies_again(self):
        """Test that a different ffmpeg path triggers new verification."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            LoudnessMeasurer("ffmpeg")
            LoudnessMeasurer("/usr/local/bin/ffmpeg")

            # Should have been called twice (once per unique path)
            assert mock_run.call_count == 2

    def test_many_instances_single_verification(self):
        """Test that 100 instances only verify once."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            for _ in range(100):
                LoudnessMeasurer("ffmpeg")

            assert mock_run.call_count == 1

    def test_failed_verification_not_cached(self):
        """Test that failed verification is not cached."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            with pytest.raises(RuntimeError):
                LoudnessMeasurer("bad_ffmpeg")

            # Should not be in cache
            assert "bad_ffmpeg" not in LoudnessMeasurer._verified_paths
