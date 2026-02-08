"""Tests for MeasurementCache SQLite backend."""

import os
import tempfile
import time
from pathlib import Path

import pytest

from vdj_manager.normalize.measurement_cache import MeasurementCache


@pytest.fixture
def cache(tmp_path):
    """Create a MeasurementCache backed by a temp directory."""
    return MeasurementCache(db_path=tmp_path / "test_measurements.db")


@pytest.fixture
def audio_file(tmp_path):
    """Create a fake audio file to cache measurements against."""
    p = tmp_path / "song.mp3"
    p.write_bytes(b"\x00" * 1024)
    return str(p)


def _sample_result(**overrides):
    """Return a measurement result dict with sensible defaults."""
    result = {
        "integrated_lufs": -18.5,
        "true_peak": -1.2,
        "lra": 7.3,
        "threshold": -28.0,
        "gain_db": 4.5,
    }
    result.update(overrides)
    return result


class TestCacheMissAndHit:
    """Basic get / put round-trip tests."""

    def test_get_returns_none_on_miss(self, cache, audio_file):
        assert cache.get(audio_file, -14.0) is None

    def test_put_then_get_returns_result(self, cache, audio_file):
        result = _sample_result()
        cache.put(audio_file, -14.0, result)

        cached = cache.get(audio_file, -14.0)
        assert cached is not None
        assert cached["integrated_lufs"] == -18.5
        assert cached["gain_db"] == 4.5
        assert cached["true_peak"] == -1.2
        assert cached["lra"] == 7.3
        assert cached["threshold"] == -28.0

    def test_different_target_lufs_is_separate_entry(self, cache, audio_file):
        cache.put(audio_file, -14.0, _sample_result(gain_db=4.5))
        cache.put(audio_file, -16.0, _sample_result(gain_db=2.5))

        cached_14 = cache.get(audio_file, -14.0)
        cached_16 = cache.get(audio_file, -16.0)
        assert cached_14["gain_db"] == 4.5
        assert cached_16["gain_db"] == 2.5

    def test_put_overwrites_existing(self, cache, audio_file):
        cache.put(audio_file, -14.0, _sample_result(gain_db=4.5))
        cache.put(audio_file, -14.0, _sample_result(gain_db=3.0))

        cached = cache.get(audio_file, -14.0)
        assert cached["gain_db"] == 3.0

    def test_get_nonexistent_file_returns_none(self, cache):
        assert cache.get("/no/such/file.mp3", -14.0) is None

    def test_put_nonexistent_file_is_noop(self, cache):
        cache.put("/no/such/file.mp3", -14.0, _sample_result())
        assert cache.stats()["count"] == 0


class TestInvalidation:
    """Cache entries are invalidated when file changes on disk."""

    def test_invalidated_when_mtime_changes(self, cache, audio_file):
        cache.put(audio_file, -14.0, _sample_result())

        # Touch the file to change mtime
        time.sleep(0.05)
        Path(audio_file).write_bytes(b"\x00" * 1024)

        assert cache.get(audio_file, -14.0) is None

    def test_invalidated_when_size_changes(self, cache, audio_file):
        cache.put(audio_file, -14.0, _sample_result())

        # Change file size (preserving mtime is hard, but changing size
        # with a different amount of data should invalidate)
        original_stat = os.stat(audio_file)
        Path(audio_file).write_bytes(b"\x00" * 2048)
        # Force mtime to match original to isolate size check
        os.utime(audio_file, (original_stat.st_atime, original_stat.st_mtime))

        assert cache.get(audio_file, -14.0) is None

    def test_invalidate_method_removes_entries(self, cache, audio_file):
        cache.put(audio_file, -14.0, _sample_result())
        cache.put(audio_file, -16.0, _sample_result())

        cache.invalidate(audio_file)

        assert cache.get(audio_file, -14.0) is None
        assert cache.get(audio_file, -16.0) is None

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

        # Cache only first two
        cache.put(files[0], -14.0, _sample_result(gain_db=1.0))
        cache.put(files[1], -14.0, _sample_result(gain_db=2.0))

        hits = cache.get_batch(files, -14.0)
        assert len(hits) == 2
        assert files[0] in hits
        assert files[1] in hits
        assert files[2] not in hits
        assert hits[files[0]]["gain_db"] == 1.0

    def test_batch_get_empty_list(self, cache):
        assert cache.get_batch([], -14.0) == {}


class TestClearAndStats:
    """Tests for clear() and stats()."""

    def test_clear_removes_all(self, cache, audio_file):
        cache.put(audio_file, -14.0, _sample_result())
        cache.put(audio_file, -16.0, _sample_result())
        assert cache.stats()["count"] == 2

        cache.clear()
        assert cache.stats()["count"] == 0

    def test_stats_empty(self, cache):
        s = cache.stats()
        assert s["count"] == 0
        assert s["db_size_bytes"] >= 0

    def test_stats_after_inserts(self, cache, audio_file):
        cache.put(audio_file, -14.0, _sample_result())
        s = cache.stats()
        assert s["count"] == 1
        assert s["db_size_bytes"] > 0


class TestPartialResult:
    """Cache handles results with missing optional fields."""

    def test_minimal_result(self, cache, audio_file):
        cache.put(audio_file, -14.0, {"integrated_lufs": -20.0, "gain_db": 6.0})
        cached = cache.get(audio_file, -14.0)
        assert cached["integrated_lufs"] == -20.0
        assert cached["gain_db"] == 6.0
        assert cached["true_peak"] is None
        assert cached["lra"] is None
        assert cached["threshold"] is None
