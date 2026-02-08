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
