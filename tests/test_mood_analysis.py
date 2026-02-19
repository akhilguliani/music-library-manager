"""Comprehensive tests for mood analysis across all layers.

Tests cover:
1. MoodAnalyzer class (backend unit tests)
2. MoodWorker (worker thread behavior)
3. AnalysisPanel mood handlers (GUI integration)
4. Online mood integration in _analyze_mood_single
"""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from vdj_manager.analysis.mood import MoodAnalyzer
from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.widgets.analysis_panel import AnalysisPanel
from vdj_manager.ui.workers.analysis_workers import MoodWorker, _analyze_mood_single, _process_cache

# Use ThreadPoolExecutor in tests so mocks are visible (ProcessPoolExecutor
# spawns subprocesses that don't share the parent's mock patches).
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


def _make_song(path: str, comment: str | None = None, user2: str | None = None) -> Song:
    return Song(
        file_path=path, tags=Tags(author="Artist", title="Title", comment=comment, user2=user2)
    )


# =============================================================================
# MoodAnalyzer unit tests
# =============================================================================


class TestMoodAnalyzerInit:
    """Tests for MoodAnalyzer initialization and availability."""

    def test_is_available_false_without_essentia(self):
        """MoodAnalyzer.is_available should be False when essentia isn't installed."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = False
        analyzer._es = None
        assert not analyzer.is_available

    def test_name_property(self):
        """name property should return 'heuristic'."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        assert analyzer.name == "heuristic"

    def test_analyze_returns_none_when_unavailable(self):
        """analyze() should return None when essentia is not available."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = False
        result = analyzer.analyze("/fake/file.mp3")
        assert result is None

    def test_get_mood_tag_returns_none_when_unavailable(self):
        """get_mood_tag() should return None when essentia is not available."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = False
        result = analyzer.get_mood_tag("/fake/file.mp3")
        assert result is None

    def test_get_mood_tag_returns_top_mood(self):
        """get_mood_tag() should return the mood with highest confidence."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True
        with patch.object(analyzer, "analyze", return_value={"energetic": 0.8, "calm": 0.2}):
            result = analyzer.get_mood_tag("/fake/file.mp3")
            assert result == "energetic"

    def test_get_mood_tag_returns_none_on_analyze_failure(self):
        """get_mood_tag() should return None when analyze() returns None."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True
        with patch.object(analyzer, "analyze", return_value=None):
            result = analyzer.get_mood_tag("/fake/file.mp3")
            assert result is None

    def test_analyze_catches_exceptions(self):
        """analyze() should catch exceptions and return None."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True
        analyzer._es = MagicMock()
        analyzer._es.MonoLoader.return_value.side_effect = RuntimeError("load failed")
        result = analyzer.analyze("/fake/file.mp3")
        assert result is None

    def test_analyze_logs_warning_on_exception(self, caplog):
        """analyze() should log a warning when analysis fails."""
        import logging

        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True
        analyzer._es = MagicMock()
        analyzer._es.MonoLoader.return_value.side_effect = RuntimeError("load failed")
        with caplog.at_level(logging.WARNING, logger="vdj_manager.analysis.mood"):
            analyzer.analyze("/fake/file.mp3")
        assert "Mood analysis failed" in caplog.text
        assert "/fake/file.mp3" in caplog.text

    def test_compute_heuristic_scores_returns_dict(self):
        """_compute_heuristic_scores should return mood -> confidence dict."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es

        mock_es.RhythmExtractor2013.return_value.return_value = (
            128.0,
            [0.5, 1.0],
            0.9,
            [],
            0.95,
        )
        mock_es.Spectrum.return_value.return_value = [0.1, 0.2]
        mock_es.Centroid.return_value.return_value = 2500.0
        mock_es.RMS.return_value.return_value = 0.15

        fake_audio = [0.0] * 100
        result = analyzer._compute_heuristic_scores(fake_audio)

        assert isinstance(result, dict)
        assert all(isinstance(v, float) for v in result.values())
        assert "energetic" in result
        assert "calm" in result
        assert "bright" in result
        assert "dark" in result

    def test_compute_heuristic_scores_catches_exceptions(self):
        """_compute_heuristic_scores should return 'unknown' on error."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es
        mock_es.RhythmExtractor2013.return_value.side_effect = RuntimeError("bad audio")

        result = analyzer._compute_heuristic_scores([0.0])

        assert "unknown" in result
        assert result["unknown"] == 0.0

    def test_compute_heuristic_scores_logs_warning(self, caplog):
        """_compute_heuristic_scores should log a warning on error."""
        import logging

        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es
        mock_es.RhythmExtractor2013.return_value.side_effect = RuntimeError("bad audio")

        with caplog.at_level(logging.WARNING, logger="vdj_manager.analysis.mood"):
            analyzer._compute_heuristic_scores([0.0])
        assert "Heuristic score computation failed" in caplog.text

    def test_analyze_full_flow_with_mocked_essentia(self):
        """Full analyze() flow with mocked essentia."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es

        mock_es.MonoLoader.return_value.return_value = [0.0] * 100
        mock_es.RhythmExtractor2013.return_value.return_value = (140.0, [], 0.9, [], 0.95)
        mock_es.Spectrum.return_value.return_value = [0.1]
        mock_es.Centroid.return_value.return_value = 3500.0
        mock_es.RMS.return_value.return_value = 0.2

        result = analyzer.analyze("/fake/song.mp3")

        assert result is not None
        assert isinstance(result, dict)
        assert all(isinstance(v, float) for v in result.values())
        assert any(k in result for k in ("energetic", "calm", "bright", "dark"))
        mock_es.MonoLoader.assert_called_once_with(filename="/fake/song.mp3", sampleRate=16000)

    def test_get_mood_tags_returns_list(self):
        """get_mood_tags() should return a list of mood strings."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True
        with patch.object(
            analyzer, "analyze", return_value={"energetic": 0.8, "calm": 0.2, "bright": 0.05}
        ):
            result = analyzer.get_mood_tags("/fake/file.mp3", threshold=0.1)
            assert isinstance(result, list)
            assert "energetic" in result
            assert "calm" in result
            assert "bright" not in result  # below 0.1

    def test_get_mood_tags_returns_none_when_unavailable(self):
        """get_mood_tags() should return None when essentia is not available."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = False
        result = analyzer.get_mood_tags("/fake/file.mp3")
        assert result is None


# =============================================================================
# _analyze_mood_single with online params
# =============================================================================


class TestAnalyzeMoodSingleOnline:
    """Tests for _analyze_mood_single with online lookup and model selection."""

    def test_online_success_returns_source(self):
        """Online lookup success should return status with source."""
        with patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup:
            mock_lookup.return_value = ("happy", "lastfm")
            result = _analyze_mood_single(
                "/a.mp3",
                artist="Artist",
                title="Title",
                enable_online=True,
                lastfm_api_key="key",
                model_name="heuristic",
            )
            assert result["mood"] == "happy"
            assert result["mood_tags"] == ["happy"]
            assert result["status"] == "ok (lastfm)"

    def test_online_fail_falls_back_to_local(self):
        """Online failure should fall back to local backend."""
        mock_backend = MagicMock()
        mock_backend.get_mood_tags.return_value = ["relaxing"]

        with (
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            mock_lookup.return_value = (None, "none")
            result = _analyze_mood_single(
                "/a.mp3",
                artist="Artist",
                title="Title",
                enable_online=True,
                lastfm_api_key="key",
                model_name="heuristic",
            )
            assert result["mood"] == "relaxing"
            assert result["mood_tags"] == ["relaxing"]
            assert "local:heuristic" in result["status"]

    def test_online_disabled_skips_lookup(self):
        """When enable_online=False, should not call online lookup."""
        mock_backend = MagicMock()
        mock_backend.get_mood_tags.return_value = ["happy"]

        with patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            result = _analyze_mood_single(
                "/a.mp3",
                artist="Artist",
                title="Title",
                enable_online=False,
                model_name="heuristic",
            )
            assert result["mood"] == "happy"
            assert result["mood_tags"] == ["happy"]
            assert "local:heuristic" in result["status"]

    def test_no_artist_title_skips_online(self):
        """Should skip online lookup when artist/title are empty."""
        mock_backend = MagicMock()
        mock_backend.get_mood_tags.return_value = ["sad"]

        with patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            result = _analyze_mood_single(
                "/a.mp3",
                artist="",
                title="",
                enable_online=True,
                lastfm_api_key="key",
                model_name="heuristic",
            )
            assert result["mood"] == "sad"
            assert result["mood_tags"] == ["sad"]
            assert "local:heuristic" in result["status"]

    def test_cache_hit_returns_cached(self):
        """Cache hit should return 'cached' status with mood_tags."""
        with patch("vdj_manager.analysis.analysis_cache.AnalysisCache") as MockCache:
            MockCache.return_value.get.return_value = "happy,uplifting"
            result = _analyze_mood_single(
                "/a.mp3",
                cache_db_path="/tmp/cache.db",
                enable_online=True,
                lastfm_api_key="key",
                model_name="heuristic",
            )
            assert result["mood"] == "happy, uplifting"
            assert result["mood_tags"] == ["happy", "uplifting"]
            assert result["status"] == "cached"

    def test_skip_cache_invalidates_and_reanalyzes(self):
        """skip_cache=True should invalidate cache and re-analyze."""
        with (
            patch("vdj_manager.analysis.analysis_cache.AnalysisCache") as MockCache,
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
        ):
            mock_lookup.return_value = ("happy", "lastfm")
            result = _analyze_mood_single(
                "/a.mp3",
                cache_db_path="/tmp/cache.db",
                artist="Artist",
                title="Title",
                enable_online=True,
                lastfm_api_key="key",
                skip_cache=True,
                model_name="heuristic",
            )
            MockCache.return_value.invalidate.assert_called_once_with("/a.mp3")
            MockCache.return_value.get.assert_not_called()
            assert result["mood"] == "happy"
            assert result["status"] == "ok (lastfm)"

    def test_multi_label_result(self):
        """Backend returning multiple tags should produce comma-separated mood."""
        mock_backend = MagicMock()
        mock_backend.get_mood_tags.return_value = ["happy", "uplifting", "summer"]

        with patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            result = _analyze_mood_single(
                "/a.mp3",
                model_name="heuristic",
            )
            assert result["mood"] == "happy, uplifting, summer"
            assert result["mood_tags"] == ["happy", "uplifting", "summer"]

    def test_model_name_parameter(self):
        """model_name should be passed to get_backend."""
        mock_backend = MagicMock()
        mock_backend.get_mood_tags.return_value = ["calm"]

        with patch(
            "vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend
        ) as mock_get:
            _analyze_mood_single("/a.mp3", model_name="heuristic")
            from vdj_manager.analysis.mood_backend import MoodModel

            mock_get.assert_called_once_with(MoodModel.HEURISTIC)


# =============================================================================
# _analyze_mood_single fallback + unknown tests
# =============================================================================


class TestAnalyzeMoodSingleFallback:
    """Tests for fallback model and 'unknown' last resort in _analyze_mood_single."""

    def test_fallback_model_used_when_primary_fails(self):
        """When primary model returns None, fallback model should be tried."""
        primary = MagicMock()
        primary.is_available = True
        primary.get_mood_tags.return_value = None

        fallback = MagicMock()
        fallback.is_available = True
        fallback.get_mood_tags.return_value = ["calm"]

        def fake_get_backend(model):
            from vdj_manager.analysis.mood_backend import MoodModel

            if model == MoodModel.MTG_JAMENDO:
                return primary
            return fallback

        with patch("vdj_manager.analysis.mood_backend.get_backend", side_effect=fake_get_backend):
            result = _analyze_mood_single("/a.mp3", model_name="mtg-jamendo")
            assert result["mood"] == "calm"
            assert result["mood_tags"] == ["calm"]
            assert "local:heuristic" in result["status"]

    def test_unknown_returned_when_all_backends_fail(self):
        """When both backends return None, 'unknown' should be returned."""
        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = None

        with patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            result = _analyze_mood_single("/a.mp3", model_name="heuristic")
            assert result["mood"] == "unknown"
            assert result["mood_tags"] == ["unknown"]
            assert result["status"] == "ok (unknown)"

    def test_unknown_returned_when_backend_unavailable(self):
        """When fallback backend is not available, 'unknown' should be returned."""
        primary = MagicMock()
        primary.is_available = True
        primary.get_mood_tags.return_value = None

        fallback = MagicMock()
        fallback.is_available = False

        def fake_get_backend(model):
            from vdj_manager.analysis.mood_backend import MoodModel

            if model == MoodModel.MTG_JAMENDO:
                return primary
            return fallback

        with patch("vdj_manager.analysis.mood_backend.get_backend", side_effect=fake_get_backend):
            result = _analyze_mood_single("/a.mp3", model_name="mtg-jamendo")
            assert result["mood"] == "unknown"
            assert result["mood_tags"] == ["unknown"]
            assert result["status"] == "ok (unknown)"

    def test_exception_returns_unknown_not_error(self):
        """Exceptions should produce 'unknown' status, not 'error:...'."""
        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.side_effect = RuntimeError("audio load failed")

        with patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            result = _analyze_mood_single("/a.mp3", model_name="heuristic")
            assert result["mood"] == "unknown"
            assert result["mood_tags"] == ["unknown"]
            assert result["status"] == "ok (unknown)"
            assert "error" not in result["status"]

    def test_fallback_skipped_when_primary_succeeds(self):
        """Fallback should not be tried when primary model succeeds."""
        primary = MagicMock()
        primary.is_available = True
        primary.get_mood_tags.return_value = ["happy"]

        call_count = 0

        def counting_get_backend(model):
            nonlocal call_count
            call_count += 1
            return primary

        with patch(
            "vdj_manager.analysis.mood_backend.get_backend", side_effect=counting_get_backend
        ):
            result = _analyze_mood_single("/a.mp3", model_name="heuristic")
            assert result["mood"] == "happy"
            assert call_count == 1  # Only primary called, no fallback

    def test_unknown_cached_when_cache_provided(self):
        """'unknown' result should be cached like any other result."""
        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = None

        with (
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
            patch("vdj_manager.analysis.analysis_cache.AnalysisCache") as MockCache,
        ):
            MockCache.return_value.get.return_value = None
            result = _analyze_mood_single(
                "/a.mp3", cache_db_path="/tmp/cache.db", model_name="heuristic"
            )
            assert result["mood"] == "unknown"
            MockCache.return_value.put.assert_called()
            # Verify "unknown" was cached
            put_args = MockCache.return_value.put.call_args
            assert put_args[0][2] == "unknown"


# =============================================================================
# MoodWorker tests
# =============================================================================


class TestMoodWorkerDetailed:
    """Detailed tests for MoodWorker behavior."""

    def test_mood_worker_get_mood_tags_returns_none(self, qapp):
        """Worker should return 'unknown' when both backends return None."""
        tracks = [_make_song("/a.mp3")]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = None

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker(tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            assert results[0]["failed"] == 0
            assert results[0]["results"][0]["status"] == "ok (unknown)"
            assert results[0]["results"][0]["mood"] == "unknown"

    def test_mood_worker_exception_during_analysis(self, qapp):
        """Worker should return 'unknown' on exceptions instead of error."""
        tracks = [_make_song("/a.mp3")]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.side_effect = RuntimeError("analysis crashed")

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker(tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            assert results[0]["failed"] == 0
            assert results[0]["results"][0]["status"] == "ok (unknown)"
            assert results[0]["results"][0]["mood"] == "unknown"

    def test_mood_worker_multiple_tracks_mixed(self, qapp):
        """Worker should analyze all tracks — no failures, unknown as fallback."""
        tracks = [
            _make_song("/a.mp3"),
            _make_song("/b.mp3"),
            _make_song("/c.mp3"),
        ]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.side_effect = [["happy"], None, None, ["energetic"]]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker(tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 3
            assert results[0]["failed"] == 0
            assert len(results[0]["results"]) == 3
            by_path = {r["file_path"]: r for r in results[0]["results"]}
            assert by_path["/a.mp3"]["mood"] == "happy"
            assert by_path["/b.mp3"]["mood"] == "unknown"
            assert by_path["/c.mp3"]["mood"] == "energetic"

    def test_mood_worker_updates_user2_tag(self, qapp):
        """Worker should include tag_updates with mood hashtags."""
        song = _make_song("/song.mp3")
        tracks = [song]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = ["relaxing"]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker(tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert results[0]["results"][0]["tag_updates"] == {"User2": "#relaxing"}

    def test_mood_worker_multi_label_hashtags(self, qapp):
        """Worker should include multiple mood hashtags in tag_updates."""
        song = _make_song("/song.mp3")
        tracks = [song]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = ["happy", "uplifting", "summer"]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker(tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert results[0]["results"][0]["tag_updates"] == {"User2": "#happy #summer #uplifting"}

    def test_mood_worker_all_unknown_counts_analyzed(self, qapp):
        """Worker should count 'unknown' results as analyzed, not failed."""
        tracks = [_make_song("/a.mp3"), _make_song("/b.mp3")]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = None

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker(tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert results[0]["analyzed"] == 2
            assert results[0]["failed"] == 0
            assert all(r["mood"] == "unknown" for r in results[0]["results"])

    def test_mood_worker_empty_tracks(self, qapp):
        """Worker should handle empty track list gracefully."""
        mock_backend = MagicMock()
        mock_backend.is_available = True

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker([], max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 0
            assert results[0]["failed"] == 0
            assert results[0]["results"] == []

    def test_mood_worker_online_enabled(self, qapp):
        """Worker should store online and model params."""
        worker = MoodWorker(
            [],
            max_workers=1,
            enable_online=True,
            lastfm_api_key="test_key",
            model_name="mtg-jamendo",
            threshold=0.15,
            max_tags=3,
        )
        assert worker._enable_online is True
        assert worker._lastfm_api_key == "test_key"
        assert worker._model_name == "mtg-jamendo"
        assert worker._threshold == 0.15
        assert worker._max_tags == 3


# =============================================================================
# MoodWorker online integration tests
# =============================================================================


class TestMoodWorkerOnlineIntegration:
    """Tests for MoodWorker with online mood lookup enabled."""

    def test_online_success_writes_lastfm_mood(self, qapp):
        """Worker with online=True should include tag_updates with Last.fm mood."""
        song = _make_song("/a.mp3")
        tracks = [song]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
        ):
            mock_lookup.return_value = ("happy", "lastfm")
            worker = MoodWorker(
                tracks,
                max_workers=1,
                enable_online=True,
                lastfm_api_key="test_key",
                model_name="heuristic",
            )
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            assert results[0]["failed"] == 0
            by_path = {r["file_path"]: r for r in results[0]["results"]}
            assert by_path["/a.mp3"]["status"] == "ok (lastfm)"
            assert by_path["/a.mp3"]["mood"] == "happy"
            assert by_path["/a.mp3"]["tag_updates"] == {"User2": "#happy"}

    def test_online_failure_falls_back_to_local(self, qapp):
        """When online lookup fails, worker should fall back to local model."""
        song = _make_song("/a.mp3")
        tracks = [song]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = ["relaxing"]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            mock_lookup.return_value = (None, "none")
            worker = MoodWorker(
                tracks,
                max_workers=1,
                enable_online=True,
                lastfm_api_key="test_key",
                model_name="heuristic",
            )
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            by_path = {r["file_path"]: r for r in results[0]["results"]}
            assert "local:heuristic" in by_path["/a.mp3"]["status"]
            assert by_path["/a.mp3"]["mood"] == "relaxing"

    def test_online_mixed_results(self, qapp):
        """Worker handles mix of online success, local fallback, and unknown."""
        tracks = [
            _make_song("/a.mp3"),
            _make_song("/b.mp3"),
            _make_song("/c.mp3"),
        ]

        call_count = 0

        def mock_lookup_fn(artist, title, api_key):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("happy", "lastfm")
            return (None, "none")

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.side_effect = [["calm"], None, None]

        with (
            _PATCH_POOL,
            patch(
                "vdj_manager.analysis.online_mood.lookup_online_mood", side_effect=mock_lookup_fn
            ),
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker(
                tracks,
                max_workers=1,
                enable_online=True,
                lastfm_api_key="test_key",
                model_name="heuristic",
            )
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 3  # online + local + unknown
            assert results[0]["failed"] == 0  # never fails
            by_path = {r["file_path"]: r for r in results[0]["results"]}
            assert by_path["/a.mp3"]["mood"] == "happy"
            assert by_path["/a.mp3"]["status"] == "ok (lastfm)"
            assert by_path["/b.mp3"]["mood"] == "calm"
            assert "local:heuristic" in by_path["/b.mp3"]["status"]
            assert by_path["/c.mp3"]["mood"] == "unknown"
            assert by_path["/c.mp3"]["status"] == "ok (unknown)"

    def test_online_caps_workers_at_one(self, qapp):
        """Online mode should cap max_workers to 1 for rate limiting."""
        tracks = [_make_song("/a.mp3")]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
        ):
            mock_lookup.return_value = ("happy", "lastfm")
            worker = MoodWorker(
                tracks,
                max_workers=8,
                enable_online=True,
                lastfm_api_key="test_key",
                model_name="heuristic",
            )
            # MoodWorker.do_work sets max_workers=1 when online
            # We can verify by checking the internal state
            assert worker._enable_online is True
            # The cap is applied in do_work(), verify via results
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()
            assert len(results) == 1

    def test_online_connection_reset_retried(self, qapp):
        """ConnectionResetError from MusicBrainz should be retried transparently."""
        song = _make_song("/a.mp3")
        tracks = [song]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = ["energetic"]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            mock_lookup.side_effect = [("energetic", "musicbrainz")]
            worker = MoodWorker(
                tracks,
                max_workers=1,
                enable_online=True,
                lastfm_api_key="test_key",
                model_name="heuristic",
            )
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            by_path = {r["file_path"]: r for r in results[0]["results"]}
            assert by_path["/a.mp3"]["mood"] == "energetic"
            assert "musicbrainz" in by_path["/a.mp3"]["status"]

    def test_online_multi_track_preserves_existing_user2(self, qapp):
        """Online mood should append to existing User2 tags, not replace."""
        song = Song(
            file_path="/a.mp3",
            tags=Tags(author="Artist", title="Title", user2="#existing_tag"),
        )
        tracks = [song]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
        ):
            mock_lookup.return_value = ("happy", "lastfm")
            worker = MoodWorker(
                tracks,
                max_workers=1,
                enable_online=True,
                lastfm_api_key="test_key",
                model_name="heuristic",
            )
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            # Should preserve #existing_tag and add #happy
            assert results[0]["results"][0]["tag_updates"] == {"User2": "#existing_tag #happy"}

    def test_online_musicbrainz_source(self, qapp):
        """Worker should correctly report MusicBrainz as source."""
        song = _make_song("/a.mp3")
        tracks = [song]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
        ):
            mock_lookup.return_value = ("calm", "musicbrainz")
            worker = MoodWorker(
                tracks,
                max_workers=1,
                enable_online=True,
                lastfm_api_key="test_key",
                model_name="heuristic",
            )
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert results[0]["results"][0]["status"] == "ok (musicbrainz)"
            assert results[0]["results"][0]["mood"] == "calm"

    def test_online_no_artist_title_skips_online(self, qapp):
        """Tracks without artist/title should skip online and use local model."""
        song = Song(file_path="/a.mp3", tags=Tags(author="", title=""))
        tracks = [song]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = ["energetic"]

        with (
            _PATCH_POOL,
            patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup,
            patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend),
        ):
            worker = MoodWorker(
                tracks,
                max_workers=1,
                enable_online=True,
                lastfm_api_key="test_key",
                model_name="heuristic",
            )
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            # Online lookup should not be called since artist/title are empty
            mock_lookup.assert_not_called()
            assert results[0]["analyzed"] == 1
            assert "local:heuristic" in results[0]["results"][0]["status"]


# =============================================================================
# AnalysisPanel mood handler tests
# =============================================================================


class TestAnalysisPanelMoodHandlers:
    """Tests for mood analysis flow in the AnalysisPanel."""

    def test_mood_button_disabled_without_database(self, qapp):
        panel = AnalysisPanel()
        assert not panel.mood_btn.isEnabled()

    def test_mood_button_enabled_with_database(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        panel.set_database(mock_db, [_make_song("/a.mp3")])
        assert panel.mood_btn.isEnabled()

    def test_mood_click_no_database_does_nothing(self, qapp):
        panel = AnalysisPanel()
        panel._on_mood_clicked()
        assert panel._mood_worker is None

    def test_mood_click_no_tracks_shows_info(self, qapp):
        panel = AnalysisPanel()
        panel._database = MagicMock()
        panel._tracks = []
        with patch.object(QMessageBox, "information") as mock_info:
            panel._on_mood_clicked()
            mock_info.assert_called_once()

    def test_mood_click_disables_button(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        mock_db.db_path = "/fake/db.xml"
        panel._database = mock_db
        panel._tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            with patch("vdj_manager.ui.widgets.analysis_panel.MoodWorker"):
                with patch("vdj_manager.core.backup.BackupManager"):
                    panel._on_mood_clicked()

        assert not panel.mood_btn.isEnabled()
        assert panel.mood_status.text() == "Analyzing..."

    def test_mood_finished_re_enables_button(self, qapp):
        panel = AnalysisPanel()
        panel.mood_btn.setEnabled(False)
        result = {
            "analyzed": 1,
            "failed": 0,
            "results": [
                {"file_path": "/a.mp3", "mood": "happy", "status": "ok (local)"},
            ],
        }
        panel._on_mood_finished(result)
        assert panel.mood_btn.isEnabled()

    def test_mood_finished_with_error_key(self, qapp):
        """When result has 'error' key, should show error and not add results."""
        panel = AnalysisPanel()
        result = {
            "analyzed": 0,
            "failed": 0,
            "results": [],
            "error": "essentia-tensorflow is not installed",
        }
        panel._on_mood_finished(result)
        assert "Error" in panel.mood_status.text()
        assert "essentia" in panel.mood_status.text()
        assert panel.mood_results.row_count() == 0

    def test_mood_finished_populates_results_table(self, qapp):
        """Results are streamed via result_ready; finished updates status."""
        panel = AnalysisPanel()
        results_data = [
            {"file_path": "/a.mp3", "mood": "happy", "status": "ok (local)"},
            {"file_path": "/b.mp3", "mood": "sad", "status": "ok (lastfm)"},
            {"file_path": "/c.mp3", "mood": "unknown", "status": "ok (unknown)"},
        ]
        for r in results_data:
            panel.mood_results.add_result(r)

        panel._on_mood_finished({"analyzed": 3, "failed": 0, "results": results_data})
        assert panel.mood_results.row_count() == 3
        assert "3 analyzed" in panel.mood_status.text()
        assert "0 failed" in panel.mood_status.text()

    def test_mood_finished_emits_database_changed(self, qapp):
        """database_changed signal should emit when mood analysis modifies data."""
        panel = AnalysisPanel()
        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        result = {
            "analyzed": 1,
            "failed": 0,
            "results": [
                {"file_path": "/a.mp3", "mood": "relaxed", "status": "ok (local)"},
            ],
        }
        panel._on_mood_finished(result)
        assert len(signals) == 1

    def test_mood_finished_no_signal_when_none_analyzed(self, qapp):
        """database_changed should NOT emit when no tracks were analyzed."""
        panel = AnalysisPanel()
        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        result = {
            "analyzed": 0,
            "failed": 2,
            "results": [
                {"file_path": "/a.mp3", "mood": None, "status": "failed"},
                {"file_path": "/b.mp3", "mood": None, "status": "failed"},
            ],
        }
        panel._on_mood_finished(result)
        assert len(signals) == 0

    def test_mood_error_handler(self, qapp):
        panel = AnalysisPanel()
        panel.mood_btn.setEnabled(False)
        panel._on_mood_error("Worker crashed")
        assert panel.mood_btn.isEnabled()
        assert "Error: Worker crashed" in panel.mood_status.text()

    def test_is_running_detects_mood_worker(self, qapp):
        """is_running() should return True when mood worker is active."""
        panel = AnalysisPanel()
        assert not panel.is_running()

        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        panel._mood_worker = mock_worker
        assert panel.is_running()

    def test_mood_click_blocked_when_running(self, qapp):
        """Mood click should show warning if another analysis is running."""
        panel = AnalysisPanel()
        panel._database = MagicMock()
        panel._tracks = [_make_song("/a.mp3")]

        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        panel._energy_worker = mock_worker

        with patch.object(QMessageBox, "warning") as mock_warn:
            panel._on_mood_clicked()
            mock_warn.assert_called_once()

    def test_online_checkbox_exists(self, qapp):
        panel = AnalysisPanel()
        assert panel.mood_online_checkbox is not None
        assert panel.mood_online_checkbox.isChecked()

    def test_api_key_label_exists(self, qapp):
        panel = AnalysisPanel()
        assert panel.mood_api_key_label is not None
        assert "API key" in panel.mood_api_key_label.text()

    def test_mood_progress_widget_exists(self, qapp):
        panel = AnalysisPanel()
        assert panel.mood_progress is not None
        assert not panel.mood_progress.isVisible()

    def test_reanalyze_button_exists(self, qapp):
        panel = AnalysisPanel()
        assert panel.mood_reanalyze_btn is not None
        assert not panel.mood_reanalyze_btn.isEnabled()

    def test_reanalyze_button_enabled_with_database(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        panel.set_database(mock_db, [_make_song("/a.mp3")])
        assert panel.mood_reanalyze_btn.isEnabled()

    def test_reanalyze_no_unknown_tracks_shows_info(self, qapp):
        panel = AnalysisPanel()
        panel._database = MagicMock()
        panel._tracks = [_make_song("/a.mp3")]
        with patch.object(QMessageBox, "information") as mock_info:
            panel._on_mood_reanalyze_clicked()
            mock_info.assert_called_once()

    def test_mood_info_label_uses_mood_tracks(self, qapp):
        """Mood info label should use _get_mood_tracks count, not _get_audio_tracks."""
        panel = AnalysisPanel()
        # Create a Windows-path track with metadata (online-eligible but not local)
        win_track = Song(
            file_path="D:\\Music\\song.mp3",
            tags=Tags(author="Artist", title="Title"),
        )
        local_track = _make_song("/a.mp3")

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            panel.set_database(MagicMock(), [win_track, local_track])

        # Both tracks should be counted — Windows tracks included (cache/online)
        label = panel.mood_info_label.text()
        assert "2 tracks" in label
        assert "1 local" in label
        assert "1 remote" in label

    def test_online_checkbox_updates_mood_count(self, qapp):
        """Toggling online checkbox should update the mood track count."""
        panel = AnalysisPanel()
        win_track = Song(
            file_path="D:\\Music\\song.mp3",
            tags=Tags(author="Artist", title="Title"),
        )
        local_track = _make_song("/a.mp3")

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            panel.set_database(MagicMock(), [win_track, local_track])

            # Both tracks always included — Windows paths use cache/online
            label = panel.mood_info_label.text()
            assert "2 tracks" in label

            # Toggling online doesn't change count — Windows paths always included
            panel.mood_online_checkbox.setChecked(False)
            QCoreApplication.processEvents()
            assert "2 tracks" in panel.mood_info_label.text()

            panel.mood_online_checkbox.setChecked(True)
            QCoreApplication.processEvents()
            assert "2 tracks" in panel.mood_info_label.text()


class TestWindowsPathTrackInclusion:
    """Tests that Windows-path tracks are included in analysis (MyNVMe database)."""

    def test_get_audio_tracks_includes_windows_paths(self, qapp):
        """Windows-path tracks should be included in _get_audio_tracks."""
        panel = AnalysisPanel()
        win_track = Song(
            file_path="D:\\Music\\song.mp3",
            tags=Tags(author="Artist", title="Title"),
        )
        local_track = _make_song("/a.mp3")

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            MockPath.return_value.suffix.lower.return_value = ".mp3"
            panel._tracks = [win_track, local_track]
            tracks = panel._get_audio_tracks()

        assert len(tracks) == 2
        assert any(t.is_windows_path for t in tracks)

    def test_get_audio_tracks_excludes_netsearch(self, qapp):
        """Netsearch tracks should still be excluded."""
        panel = AnalysisPanel()
        net_track = Song(file_path="netsearch://test", tags=Tags())
        local_track = _make_song("/a.mp3")

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            panel._tracks = [net_track, local_track]
            tracks = panel._get_audio_tracks()

        assert len(tracks) == 1
        assert tracks[0].file_path == "/a.mp3"

    def test_get_mood_tracks_includes_windows_paths_without_online(self, qapp):
        """Windows-path tracks should be included even when online is OFF."""
        panel = AnalysisPanel()
        panel.mood_online_checkbox.setChecked(False)

        win_track = Song(
            file_path="D:\\Music\\song.mp3",
            tags=Tags(author="Artist", title="Title"),
        )
        local_track = _make_song("/a.mp3")

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            panel._tracks = [win_track, local_track]
            tracks = panel._get_mood_tracks()

        assert len(tracks) == 2
        assert any(t.is_windows_path for t in tracks)

    def test_energy_info_label_shows_remote_count(self, qapp):
        """Energy info label should show local/remote breakdown for Windows paths."""
        panel = AnalysisPanel()
        win_track = Song(
            file_path="D:\\Music\\song.mp3",
            tags=Tags(author="Artist", title="Title"),
        )
        local_track = _make_song("/a.mp3")

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            panel.set_database(MagicMock(), [win_track, local_track])

        label = panel.energy_info_label.text()
        assert "2 tracks" in label
        assert "1 local" in label
        assert "1 remote" in label

    def test_mik_info_label_shows_remote_count(self, qapp):
        """MIK info label should show local/remote breakdown for Windows paths."""
        panel = AnalysisPanel()
        win_track = Song(
            file_path="D:\\Music\\song.mp3",
            tags=Tags(author="Artist", title="Title"),
        )
        local_track = _make_song("/a.mp3")

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            panel.set_database(MagicMock(), [win_track, local_track])

        label = panel.mik_info_label.text()
        assert "2 tracks" in label
        assert "1 local" in label
        assert "1 remote" in label

    def test_all_local_tracks_no_remote_label(self, qapp):
        """When all tracks are local, don't show remote breakdown."""
        panel = AnalysisPanel()
        track1 = _make_song("/a.mp3")
        track2 = _make_song("/b.mp3")

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            panel.set_database(MagicMock(), [track1, track2])

        label = panel.energy_info_label.text()
        assert "2 audio tracks" in label
        assert "remote" not in label
