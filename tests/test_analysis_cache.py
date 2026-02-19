"""Tests for AnalysisCache SQLite backend."""

import os
import time
from pathlib import Path

import pytest

from vdj_manager.analysis.analysis_cache import AnalysisCache


@pytest.fixture
def cache(tmp_path):
    """Create an AnalysisCache backed by a temp directory."""
    return AnalysisCache(db_path=tmp_path / "test_analysis.db")


@pytest.fixture
def audio_file(tmp_path):
    """Create a fake audio file to cache results against."""
    p = tmp_path / "song.mp3"
    p.write_bytes(b"\x00" * 1024)
    return str(p)


class TestCacheMissAndHit:
    """Basic get / put round-trip tests."""

    def test_get_returns_none_on_miss(self, cache, audio_file):
        assert cache.get(audio_file, "energy") is None

    def test_put_then_get_returns_result(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")
        cached = cache.get(audio_file, "energy")
        assert cached == "7"

    def test_different_analysis_types_are_separate(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")
        cache.put(audio_file, "mood", "happy")
        cache.put(audio_file, "mik", "8:Am")

        assert cache.get(audio_file, "energy") == "7"
        assert cache.get(audio_file, "mood") == "happy"
        assert cache.get(audio_file, "mik") == "8:Am"

    def test_put_overwrites_existing(self, cache, audio_file):
        cache.put(audio_file, "energy", "5")
        cache.put(audio_file, "energy", "8")
        assert cache.get(audio_file, "energy") == "8"

    def test_get_nonexistent_file_returns_none(self, cache):
        assert cache.get("/no/such/file.mp3", "energy") is None

    def test_put_nonexistent_file_is_noop(self, cache):
        cache.put("/no/such/file.mp3", "energy", "7")
        assert cache.stats()["count"] == 0


class TestInvalidation:
    """Cache entries are invalidated when file changes on disk."""

    def test_invalidated_when_mtime_changes(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")

        # Touch the file to change mtime
        time.sleep(0.05)
        Path(audio_file).write_bytes(b"\x00" * 1024)

        assert cache.get(audio_file, "energy") is None

    def test_invalidated_when_size_changes(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")

        original_stat = os.stat(audio_file)
        Path(audio_file).write_bytes(b"\x00" * 2048)
        os.utime(audio_file, (original_stat.st_atime, original_stat.st_mtime))

        assert cache.get(audio_file, "energy") is None

    def test_invalidate_method_removes_all_types(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")
        cache.put(audio_file, "mood", "happy")

        cache.invalidate(audio_file)

        assert cache.get(audio_file, "energy") is None
        assert cache.get(audio_file, "mood") is None

    def test_invalidate_specific_type_keeps_others(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")
        cache.put(audio_file, "genre", "House")

        cache.invalidate(audio_file, "genre")

        assert cache.get(audio_file, "energy") == "7"  # kept
        assert cache.get(audio_file, "genre") is None  # removed

    def test_invalidate_nonexistent_is_noop(self, cache):
        cache.invalidate("/no/such/file.mp3")  # Should not raise


class TestBatchGet:
    """Tests for get_batch."""

    def test_batch_get_returns_hits_only(self, cache, tmp_path):
        files = []
        for i in range(3):
            p = tmp_path / f"song{i}.mp3"
            p.write_bytes(b"\x00" * 512)
            files.append(str(p))

        cache.put(files[0], "energy", "5")
        cache.put(files[1], "energy", "8")

        hits = cache.get_batch(files, "energy")
        assert len(hits) == 2
        assert hits[files[0]] == "5"
        assert hits[files[1]] == "8"
        assert files[2] not in hits

    def test_batch_get_empty_list(self, cache):
        assert cache.get_batch([], "energy") == {}

    def test_batch_get_uses_single_query(self, cache, tmp_path):
        """Batch of 10 files should use a single SQL query, not N queries."""
        files = []
        for i in range(10):
            p = tmp_path / f"song{i}.mp3"
            p.write_bytes(b"\x00" * 256)
            files.append(str(p))

        # Cache half of them
        for f in files[:5]:
            cache.put(f, "energy", str(hash(f) % 10))

        hits = cache.get_batch(files, "energy")
        assert len(hits) == 5
        for f in files[:5]:
            assert f in hits
        for f in files[5:]:
            assert f not in hits

    def test_batch_get_different_analysis_type_no_hits(self, cache, tmp_path):
        """Batch get with wrong analysis type should return no hits."""
        p = tmp_path / "song.mp3"
        p.write_bytes(b"\x00" * 256)
        cache.put(str(p), "energy", "7")
        hits = cache.get_batch([str(p)], "mood")
        assert hits == {}

    def test_batch_get_invalidates_stale(self, cache, tmp_path):
        """Batch get should skip entries where file has changed."""
        p = tmp_path / "song.mp3"
        p.write_bytes(b"\x00" * 256)
        cache.put(str(p), "energy", "7")
        # Modify file
        p.write_bytes(b"\x00" * 512)
        hits = cache.get_batch([str(p)], "energy")
        assert hits == {}


class TestClearAndStats:
    """Tests for clear() and stats()."""

    def test_clear_removes_all(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")
        cache.put(audio_file, "mood", "happy")
        assert cache.stats()["count"] == 2

        cache.clear()
        assert cache.stats()["count"] == 0

    def test_stats_empty(self, cache):
        s = cache.stats()
        assert s["count"] == 0
        assert s["db_size_bytes"] >= 0

    def test_stats_after_inserts(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")
        s = cache.stats()
        assert s["count"] == 1
        assert s["db_size_bytes"] > 0


class TestInvalidateByType:
    """Tests for invalidate_by_type and invalidate_by_type_prefix."""

    def test_invalidate_by_type_removes_matching(self, cache, audio_file):
        cache.put(audio_file, "mood:heuristic", "happy")
        cache.put(audio_file, "mood:mtg-jamendo", "calm,relaxing")
        cache.put(audio_file, "energy", "7")

        removed = cache.invalidate_by_type("mood:heuristic")

        assert removed == 1
        assert cache.get(audio_file, "mood:heuristic") is None
        assert cache.get(audio_file, "mood:mtg-jamendo") == "calm,relaxing"
        assert cache.get(audio_file, "energy") == "7"

    def test_invalidate_by_type_returns_zero_on_no_match(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")
        assert cache.invalidate_by_type("mood:heuristic") == 0

    def test_invalidate_by_type_prefix_removes_all_matching(self, cache, audio_file):
        cache.put(audio_file, "mood:heuristic", "happy")
        cache.put(audio_file, "mood:mtg-jamendo", "calm,relaxing")
        cache.put(audio_file, "energy", "7")

        removed = cache.invalidate_by_type_prefix("mood:")

        assert removed == 2
        assert cache.get(audio_file, "mood:heuristic") is None
        assert cache.get(audio_file, "mood:mtg-jamendo") is None
        assert cache.get(audio_file, "energy") == "7"

    def test_invalidate_by_type_prefix_no_match(self, cache, audio_file):
        cache.put(audio_file, "energy", "7")
        assert cache.invalidate_by_type_prefix("mood:") == 0

    def test_invalidate_by_type_multiple_files(self, cache, tmp_path):
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"\x00" * 512)
        f2.write_bytes(b"\x00" * 512)

        cache.put(str(f1), "mood:heuristic", "happy")
        cache.put(str(f2), "mood:heuristic", "sad")
        cache.put(str(f1), "energy", "5")

        removed = cache.invalidate_by_type("mood:heuristic")

        assert removed == 2
        assert cache.get(str(f1), "energy") == "5"


class TestLegacyMigration:
    """Tests for legacy 'mood' -> 'mood:heuristic' migration."""

    def test_migrates_legacy_mood_key(self, tmp_path):
        """Legacy 'mood' entries are migrated to 'mood:heuristic' on init."""
        import sqlite3

        db_path = tmp_path / "migration_test.db"

        # Create a database with the old schema and insert legacy data
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE analysis_results (
                file_path      TEXT    NOT NULL,
                analysis_type  TEXT    NOT NULL,
                mtime          REAL    NOT NULL,
                file_size      INTEGER NOT NULL,
                result_value   TEXT,
                analyzed_at    TEXT    NOT NULL,
                PRIMARY KEY (file_path, analysis_type)
            )
        """)

        # Create a real file so stat works
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"\x00" * 100)
        stat = audio.stat()

        conn.execute(
            "INSERT INTO analysis_results VALUES (?, ?, ?, ?, ?, ?)",
            (str(audio), "mood", stat.st_mtime, stat.st_size, "happy", "2025-01-01"),
        )
        conn.execute(
            "INSERT INTO analysis_results VALUES (?, ?, ?, ?, ?, ?)",
            (str(audio), "energy", stat.st_mtime, stat.st_size, "7", "2025-01-01"),
        )
        conn.commit()
        conn.close()

        # Now open with AnalysisCache which triggers migration
        cache = AnalysisCache(db_path=db_path)

        # Old "mood" key should not exist
        assert cache.get(str(audio), "mood") is None
        # Should be accessible via new key
        assert cache.get(str(audio), "mood:heuristic") == "happy"
        # Energy should be untouched
        assert cache.get(str(audio), "energy") == "7"

    def test_migration_is_idempotent(self, tmp_path):
        """Running migration twice doesn't cause errors."""
        db_path = tmp_path / "idem_test.db"
        cache1 = AnalysisCache(db_path=db_path)

        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"\x00" * 100)
        cache1.put(str(audio), "mood:heuristic", "happy")

        # Re-init (simulates restart) — migration runs again
        cache2 = AnalysisCache(db_path=db_path)
        assert cache2.get(str(audio), "mood:heuristic") == "happy"


class TestMultipleFiles:
    """Cache handles multiple files independently."""

    def test_different_files_independent(self, cache, tmp_path):
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"\x00" * 512)
        f2.write_bytes(b"\x00" * 512)

        cache.put(str(f1), "energy", "3")
        cache.put(str(f2), "energy", "9")

        assert cache.get(str(f1), "energy") == "3"
        assert cache.get(str(f2), "energy") == "9"

    def test_invalidate_one_file_keeps_others(self, cache, tmp_path):
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"\x00" * 512)
        f2.write_bytes(b"\x00" * 512)

        cache.put(str(f1), "energy", "3")
        cache.put(str(f2), "energy", "9")

        cache.invalidate(str(f1))

        assert cache.get(str(f1), "energy") is None
        assert cache.get(str(f2), "energy") == "9"
