"""Tests for genre detection worker and subprocess function."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.workers.analysis_workers import (
    GenreWorker,
    _fetch_genre_single,
    _process_cache,
)

# Use ThreadPoolExecutor in tests so mocks are visible in same process
_PATCH_POOL = patch(
    "vdj_manager.ui.workers.analysis_workers.ProcessPoolExecutor",
    ThreadPoolExecutor,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _clear_process_cache():
    """Clear module-level _process_cache before each test."""
    _process_cache.clear()
    yield
    _process_cache.clear()


def _make_song(
    path: str, genre: str | None = None, artist: str = "Artist", title: str = "Title"
) -> Song:
    return Song(
        file_path=path,
        tags=Tags(author=artist, title=title, genre=genre),
    )


# =============================================================================
# _fetch_genre_single tests
# =============================================================================


class TestFetchGenreSingle:
    """Tests for the subprocess genre detection function."""

    def test_cached_result(self):
        """Should return cached genre without reading file."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = "House"
        _process_cache["analysis_cache"] = mock_cache

        result = _fetch_genre_single("/music/track.mp3", cache_db_path="/tmp/cache.db")
        assert result["genre"] == "House"
        assert result["status"] == "cached"
        assert result["source"] == "cache"

    @patch("vdj_manager.ui.workers.analysis_workers.os.path.isfile", return_value=True)
    def test_file_tag_pass(self, mock_isfile):
        """Pass 1: should read genre from embedded file tags."""
        mock_editor = MagicMock()
        mock_editor.read_tags.return_value = {"genre": "Hip-Hop", "title": None}
        _process_cache["file_tag_editor"] = mock_editor

        result = _fetch_genre_single("/music/track.mp3")

        assert result["genre"] == "Hip-Hop"
        assert result["status"] == "ok (file-tag)"
        assert result["source"] == "file-tag"

    @patch("vdj_manager.ui.workers.analysis_workers.os.path.isfile", return_value=True)
    def test_file_tag_normalized(self, mock_isfile):
        """File tag genre should be normalized through TAG_TO_GENRE."""
        mock_editor = MagicMock()
        mock_editor.read_tags.return_value = {"genre": "drum and bass", "title": None}
        _process_cache["file_tag_editor"] = mock_editor

        result = _fetch_genre_single("/music/track.mp3")

        assert result["genre"] == "Drum & Bass"

    @patch("vdj_manager.ui.workers.analysis_workers.os.path.isfile", return_value=False)
    def test_online_pass_when_no_file(self, mock_isfile):
        """Pass 2: should try online when file doesn't exist locally."""
        with patch(
            "vdj_manager.analysis.online_genre.lookup_online_genre",
            return_value=("Techno", "lastfm"),
        ):
            result = _fetch_genre_single(
                "/music/track.mp3",
                artist="Artist",
                title="Title",
                enable_online=True,
            )

        assert result["genre"] == "Techno"
        assert result["status"] == "ok (lastfm)"

    @patch("vdj_manager.ui.workers.analysis_workers.os.path.isfile", return_value=True)
    def test_online_fallback_when_file_tag_empty(self, mock_isfile):
        """Should fall back to online when file tag is empty."""
        mock_editor = MagicMock()
        mock_editor.read_tags.return_value = {"genre": None, "title": None}
        _process_cache["file_tag_editor"] = mock_editor

        with patch(
            "vdj_manager.analysis.online_genre.lookup_online_genre",
            return_value=("Pop", "musicbrainz"),
        ):
            result = _fetch_genre_single(
                "/music/track.mp3",
                artist="Artist",
                title="Title",
                enable_online=True,
            )

        assert result["genre"] == "Pop"
        assert result["status"] == "ok (musicbrainz)"

    @patch("vdj_manager.ui.workers.analysis_workers.os.path.isfile", return_value=True)
    def test_no_genre_found(self, mock_isfile):
        """Should return None when no genre found from any source."""
        mock_editor = MagicMock()
        mock_editor.read_tags.return_value = {"genre": None, "title": None}
        _process_cache["file_tag_editor"] = mock_editor

        result = _fetch_genre_single("/music/track.mp3")

        assert result["genre"] is None
        assert result["status"] == "none"

    def test_skip_cache_invalidates_genre_only(self):
        """skip_cache=True should invalidate only genre type, not all types."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        _process_cache["analysis_cache"] = mock_cache

        with patch("vdj_manager.ui.workers.analysis_workers.os.path.isfile", return_value=False):
            _fetch_genre_single("/music/track.mp3", cache_db_path="/tmp/c.db", skip_cache=True)

        mock_cache.invalidate.assert_called_once_with("/music/track.mp3", "genre")

    @patch("vdj_manager.ui.workers.analysis_workers.os.path.isfile", return_value=True)
    def test_caches_result(self, mock_isfile):
        """Should cache genre after successful detection."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        _process_cache["analysis_cache"] = mock_cache

        mock_editor = MagicMock()
        mock_editor.read_tags.return_value = {"genre": "jazz", "title": None}
        _process_cache["file_tag_editor"] = mock_editor

        _fetch_genre_single("/music/track.mp3", cache_db_path="/tmp/c.db")

        mock_cache.put.assert_called_once_with("/music/track.mp3", "genre", "Jazz")


# =============================================================================
# GenreWorker tests
# =============================================================================


class TestGenreWorker:
    """Tests for the GenreWorker class."""

    def test_worker_processes_tracks(self, qapp):
        """Worker should process tracks and emit results."""
        tracks = [_make_song("/music/a.mp3"), _make_song("/music/b.mp3")]
        results_received = []

        with (
            _PATCH_POOL,
            patch(
                "vdj_manager.ui.workers.analysis_workers._fetch_genre_single",
                side_effect=[
                    {
                        "file_path": "/music/a.mp3",
                        "format": ".mp3",
                        "genre": "House",
                        "source": "file-tag",
                        "status": "ok (file-tag)",
                    },
                    {
                        "file_path": "/music/b.mp3",
                        "format": ".mp3",
                        "genre": "Techno",
                        "source": "lastfm",
                        "status": "ok (lastfm)",
                    },
                ],
            ),
        ):
            worker = GenreWorker(tracks)
            worker.result_ready.connect(results_received.append)
            worker.start()
            worker.wait()
            QCoreApplication.processEvents()

        assert len(results_received) == 2
        assert results_received[0]["tag_updates"] == {"Genre": "House"}
        assert results_received[1]["tag_updates"] == {"Genre": "Techno"}

    def test_worker_counts_cached(self, qapp):
        """Cached results should increment cached counter."""
        tracks = [_make_song("/music/a.mp3")]

        with (
            _PATCH_POOL,
            patch(
                "vdj_manager.ui.workers.analysis_workers._fetch_genre_single",
                return_value={
                    "file_path": "/music/a.mp3",
                    "format": ".mp3",
                    "genre": "Pop",
                    "source": "cache",
                    "status": "cached",
                },
            ),
        ):
            worker = GenreWorker(tracks)
            result = worker.do_work()

        assert result["cached"] == 1
        assert result["analyzed"] == 0

    def test_worker_counts_failed(self, qapp):
        """Tracks with no genre should count as failed."""
        tracks = [_make_song("/music/a.mp3")]

        with (
            _PATCH_POOL,
            patch(
                "vdj_manager.ui.workers.analysis_workers._fetch_genre_single",
                return_value={
                    "file_path": "/music/a.mp3",
                    "format": ".mp3",
                    "genre": None,
                    "source": "none",
                    "status": "none",
                },
            ),
        ):
            worker = GenreWorker(tracks)
            result = worker.do_work()

        assert result["failed"] == 1
        assert result["analyzed"] == 0

    def test_worker_tag_updates_format(self, qapp):
        """tag_updates should use Genre key (not User2 or Grouping)."""
        tracks = [_make_song("/music/a.mp3")]

        with (
            _PATCH_POOL,
            patch(
                "vdj_manager.ui.workers.analysis_workers._fetch_genre_single",
                return_value={
                    "file_path": "/music/a.mp3",
                    "format": ".mp3",
                    "genre": "Drum & Bass",
                    "source": "file-tag",
                    "status": "ok (file-tag)",
                },
            ),
        ):
            worker = GenreWorker(tracks)
            result = worker.do_work()

        assert result["results"][0]["tag_updates"] == {"Genre": "Drum & Bass"}

    def test_worker_online_caps_workers(self, qapp):
        """Online mode should cap max_workers to 1."""
        tracks = [_make_song("/music/a.mp3")]

        with (
            patch(
                "vdj_manager.ui.workers.analysis_workers.ProcessPoolExecutor",
                MagicMock(wraps=ThreadPoolExecutor),
            ) as mock_pool_cls,
            patch(
                "vdj_manager.ui.workers.analysis_workers._fetch_genre_single",
                return_value={
                    "file_path": "/music/a.mp3",
                    "format": ".mp3",
                    "genre": None,
                    "source": "none",
                    "status": "none",
                },
            ),
        ):
            worker = GenreWorker(tracks, enable_online=True, max_workers=4)
            worker.do_work()
            mock_pool_cls.assert_called_with(max_workers=1)

    def test_worker_passes_online_params(self, qapp):
        """Worker should pass enable_online and lastfm_api_key to subprocess fn."""
        tracks = [_make_song("/music/a.mp3")]

        with (
            _PATCH_POOL,
            patch(
                "vdj_manager.ui.workers.analysis_workers._fetch_genre_single",
                return_value={
                    "file_path": "/music/a.mp3",
                    "format": ".mp3",
                    "genre": "Rock",
                    "source": "lastfm",
                    "status": "ok (lastfm)",
                },
            ) as mock_fn,
        ):
            worker = GenreWorker(
                tracks,
                enable_online=True,
                lastfm_api_key="my_key",
            )
            worker.do_work()

        call_kwargs = mock_fn.call_args
        assert call_kwargs.kwargs["enable_online"] is True
        assert call_kwargs.kwargs["lastfm_api_key"] == "my_key"
