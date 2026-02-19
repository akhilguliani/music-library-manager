"""Tests for album art delegate and cache."""

from unittest.mock import patch

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from vdj_manager.ui.delegates.album_art_delegate import (
    _THUMB_SIZE,
    AlbumArtCache,
    AlbumArtDelegate,
    _ArtLoadRunnable,
)


@pytest.fixture(scope="module")
def app():
    """Create a QApplication for testing."""
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        app = QApplication(["test"])
        yield app


class TestAlbumArtCache:
    """Tests for AlbumArtCache."""

    def test_cache_creation(self, app):
        """Test cache can be created."""
        cache = AlbumArtCache()
        assert cache is not None

    def test_get_uncached_returns_none_and_triggers_load(self, app):
        """Test get() returns None for uncached path and triggers async load."""
        cache = AlbumArtCache()
        result = cache.get("/path/to/track.mp3")
        assert result is None
        # Path should now be pending
        assert "/path/to/track.mp3" in cache._pending

    def test_get_does_not_double_load(self, app):
        """Test get() doesn't trigger a second load for the same path."""
        cache = AlbumArtCache()
        cache.get("/path/to/track.mp3")
        pending_count = len(cache._pending)
        cache.get("/path/to/track.mp3")
        assert len(cache._pending) == pending_count

    def test_on_art_loaded_caches_pixmap(self, app):
        """Test _on_art_loaded stores pixmap in cache."""
        cache = AlbumArtCache()
        cache._pending.add("/path/to/track.mp3")

        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.red)

        signals_received = []
        cache.art_ready.connect(lambda fp: signals_received.append(fp))

        cache._on_art_loaded("/path/to/track.mp3", pixmap)

        # Should be cached
        assert "/path/to/track.mp3" in cache._cache
        cached = cache._cache["/path/to/track.mp3"]
        assert cached is not None
        assert not cached.isNull()

        # Should have emitted art_ready
        assert len(signals_received) == 1
        assert signals_received[0] == "/path/to/track.mp3"

        # Should no longer be pending
        assert "/path/to/track.mp3" not in cache._pending

    def test_on_art_loaded_stores_none_for_empty(self, app):
        """Test _on_art_loaded stores None for empty pixmap (no art found)."""
        cache = AlbumArtCache()
        cache._pending.add("/path/to/track.mp3")

        cache._on_art_loaded("/path/to/track.mp3", QPixmap())

        assert "/path/to/track.mp3" in cache._cache
        assert cache._cache["/path/to/track.mp3"] is None

    def test_get_cached_returns_pixmap(self, app):
        """Test get() returns cached pixmap."""
        cache = AlbumArtCache()
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.blue)
        cache._cache["/path/to/track.mp3"] = pixmap

        result = cache.get("/path/to/track.mp3")
        assert result is not None
        assert not result.isNull()

    def test_get_cached_none_returns_none(self, app):
        """Test get() returns None for cached no-art entry."""
        cache = AlbumArtCache()
        cache._cache["/path/to/track.mp3"] = None

        result = cache.get("/path/to/track.mp3")
        assert result is None
        # Should NOT be added to pending (already resolved)
        assert "/path/to/track.mp3" not in cache._pending

    def test_clear(self, app):
        """Test clear() empties cache and pending."""
        cache = AlbumArtCache()
        cache._cache["a"] = QPixmap(10, 10)
        cache._pending.add("b")

        cache.clear()
        assert len(cache._cache) == 0
        assert len(cache._pending) == 0

    def test_eviction_at_max_size(self, app):
        """Test oldest entry evicted when cache reaches max_size."""
        cache = AlbumArtCache(max_size=3)

        # Fill cache
        for i in range(3):
            cache._cache[f"track{i}"] = QPixmap(10, 10)

        # Add one more via _on_art_loaded
        cache._pending.add("track3")
        cache._on_art_loaded("track3", QPixmap(10, 10))

        assert len(cache._cache) == 3
        assert "track0" not in cache._cache  # oldest evicted
        assert "track3" in cache._cache

    def test_get_placeholder(self, app):
        """Test placeholder pixmap creation."""
        cache = AlbumArtCache()
        placeholder = cache.get_placeholder()

        assert placeholder is not None
        assert not placeholder.isNull()
        assert placeholder.width() == _THUMB_SIZE
        assert placeholder.height() == _THUMB_SIZE

        # Second call returns same object (cached)
        placeholder2 = cache.get_placeholder()
        assert placeholder is placeholder2


class TestArtLoadRunnable:
    """Tests for _ArtLoadRunnable."""

    def test_runnable_creation(self, app):
        """Test runnable can be created."""
        runnable = _ArtLoadRunnable("/path/to/track.mp3")
        assert runnable.file_path == "/path/to/track.mp3"
        assert runnable.size == _THUMB_SIZE

    @patch("vdj_manager.player.album_art.extract_album_art")
    def test_run_with_art(self, mock_extract, app):
        """Test run() emits pixmap when art is found."""
        import struct
        import zlib

        def make_png():
            signature = b"\x89PNG\r\n\x1a\n"
            ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
            ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
            raw = b"\x00\xff\x00\x00"  # filter byte + RGB
            idat_data = zlib.compress(raw)
            idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
            idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + idat_crc
            iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
            iend = struct.pack(">I", 0) + b"IEND" + iend_crc
            return signature + ihdr + idat + iend

        mock_extract.return_value = make_png()

        runnable = _ArtLoadRunnable("/path/to/track.mp3")
        results = []
        runnable.signals.art_loaded.connect(lambda fp, px: results.append((fp, px)))

        runnable.run()

        assert len(results) == 1
        assert results[0][0] == "/path/to/track.mp3"
        assert not results[0][1].isNull()

    @patch("vdj_manager.player.album_art.extract_album_art")
    def test_run_without_art(self, mock_extract, app):
        """Test run() emits empty pixmap when no art found."""
        mock_extract.return_value = None

        runnable = _ArtLoadRunnable("/path/to/track.mp3")
        results = []
        runnable.signals.art_loaded.connect(lambda fp, px: results.append((fp, px)))

        runnable.run()

        assert len(results) == 1
        assert results[0][0] == "/path/to/track.mp3"
        assert results[0][1].isNull()

    @patch("vdj_manager.player.album_art.extract_album_art")
    def test_run_with_exception(self, mock_extract, app):
        """Test run() emits empty pixmap on exception."""
        mock_extract.side_effect = Exception("file not found")

        runnable = _ArtLoadRunnable("/path/to/track.mp3")
        results = []
        runnable.signals.art_loaded.connect(lambda fp, px: results.append((fp, px)))

        runnable.run()

        assert len(results) == 1
        assert results[0][1].isNull()


class TestAlbumArtDelegate:
    """Tests for AlbumArtDelegate."""

    def test_delegate_creation(self, app):
        """Test delegate can be created."""
        cache = AlbumArtCache()
        delegate = AlbumArtDelegate(cache)
        assert delegate is not None

    def test_size_hint(self, app):
        """Test sizeHint returns correct size."""
        cache = AlbumArtCache()
        delegate = AlbumArtDelegate(cache)
        option = QStyleOptionViewItem()
        index = QModelIndex()

        size = delegate.sizeHint(option, index)
        assert size.width() == _THUMB_SIZE + 4
        assert size.height() == _THUMB_SIZE + 4
