"""Comprehensive tests for mood analysis across all layers.

Tests cover:
1. MoodAnalyzer class (backend unit tests)
2. MoodWorker (worker thread behavior)
3. AnalysisPanel mood handlers (GUI integration)
4. Online mood integration in _analyze_mood_single
"""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QCoreApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.analysis.mood import MoodAnalyzer
from vdj_manager.ui.widgets.analysis_panel import AnalysisPanel
from vdj_manager.ui.workers.analysis_workers import MoodWorker, _analyze_mood_single

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


def _make_song(path: str, comment: str | None = None, user2: str | None = None) -> Song:
    return Song(file_path=path, tags=Tags(author="Artist", title="Title", comment=comment, user2=user2))


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

    def test_compute_heuristic_scores_returns_dict(self):
        """_compute_heuristic_scores should return mood -> confidence dict."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es

        mock_es.RhythmExtractor2013.return_value.return_value = (
            128.0, [0.5, 1.0], 0.9, [], 0.95,
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

    def test_analyze_full_flow_with_mocked_essentia(self):
        """Full analyze() flow with mocked essentia."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es

        mock_es.MonoLoader.return_value.return_value = [0.0] * 100
        mock_es.RhythmExtractor2013.return_value.return_value = (
            140.0, [], 0.9, [], 0.95
        )
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
        with patch.object(analyzer, "analyze", return_value={"energetic": 0.8, "calm": 0.2, "bright": 0.05}):
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
                "/a.mp3", artist="Artist", title="Title",
                enable_online=True, lastfm_api_key="key",
                model_name="heuristic",
            )
            assert result["mood"] == "happy"
            assert result["mood_tags"] == ["happy"]
            assert result["status"] == "ok (lastfm)"

    def test_online_fail_falls_back_to_local(self):
        """Online failure should fall back to local backend."""
        mock_backend = MagicMock()
        mock_backend.get_mood_tags.return_value = ["relaxing"]

        with patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup, \
             patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            mock_lookup.return_value = (None, "none")
            result = _analyze_mood_single(
                "/a.mp3", artist="Artist", title="Title",
                enable_online=True, lastfm_api_key="key",
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
                "/a.mp3", artist="Artist", title="Title",
                enable_online=False, model_name="heuristic",
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
                "/a.mp3", artist="", title="",
                enable_online=True, lastfm_api_key="key",
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
                "/a.mp3", cache_db_path="/tmp/cache.db",
                enable_online=True, lastfm_api_key="key",
                model_name="heuristic",
            )
            assert result["mood"] == "happy, uplifting"
            assert result["mood_tags"] == ["happy", "uplifting"]
            assert result["status"] == "cached"

    def test_skip_cache_invalidates_and_reanalyzes(self):
        """skip_cache=True should invalidate cache and re-analyze."""
        with patch("vdj_manager.analysis.analysis_cache.AnalysisCache") as MockCache, \
             patch("vdj_manager.analysis.online_mood.lookup_online_mood") as mock_lookup:
            mock_lookup.return_value = ("happy", "lastfm")
            result = _analyze_mood_single(
                "/a.mp3", cache_db_path="/tmp/cache.db",
                artist="Artist", title="Title",
                enable_online=True, lastfm_api_key="key",
                skip_cache=True, model_name="heuristic",
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
                "/a.mp3", model_name="heuristic",
            )
            assert result["mood"] == "happy, uplifting, summer"
            assert result["mood_tags"] == ["happy", "uplifting", "summer"]

    def test_model_name_parameter(self):
        """model_name should be passed to get_backend."""
        mock_backend = MagicMock()
        mock_backend.get_mood_tags.return_value = ["calm"]

        with patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend) as mock_get:
            _analyze_mood_single("/a.mp3", model_name="heuristic")
            from vdj_manager.analysis.mood_backend import MoodModel
            mock_get.assert_called_once_with(MoodModel.HEURISTIC)


# =============================================================================
# MoodWorker tests
# =============================================================================


class TestMoodWorkerDetailed:
    """Detailed tests for MoodWorker behavior."""

    def test_mood_worker_get_mood_tags_returns_none(self, qapp):
        """Worker should count as failed when backend returns None/empty."""
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = None

        with _PATCH_POOL, patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 0
            assert results[0]["failed"] == 1
            assert results[0]["results"][0]["status"] == "failed"
            mock_db.save.assert_not_called()

    def test_mood_worker_exception_during_analysis(self, qapp):
        """Worker should handle exceptions during individual track analysis."""
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.side_effect = RuntimeError("analysis crashed")

        with _PATCH_POOL, patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 0
            assert results[0]["failed"] == 1
            assert "error" in results[0]["results"][0]["status"]
            mock_db.save.assert_not_called()

    def test_mood_worker_multiple_tracks_mixed(self, qapp):
        """Worker should handle a mix of successful and failed analyses."""
        mock_db = MagicMock()
        tracks = [
            _make_song("/a.mp3"),
            _make_song("/b.mp3"),
            _make_song("/c.mp3"),
        ]
        mock_db.get_song.side_effect = lambda fp: next(
            (t for t in tracks if t.file_path == fp), None
        )

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.side_effect = [["happy"], None, ["energetic"]]

        with _PATCH_POOL, patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 2
            assert results[0]["failed"] == 1
            assert len(results[0]["results"]) == 3
            by_path = {r["file_path"]: r for r in results[0]["results"]}
            assert by_path["/a.mp3"]["mood"] == "happy"
            assert by_path["/b.mp3"]["mood"] is None
            assert by_path["/c.mp3"]["mood"] == "energetic"
            mock_db.save.assert_called_once()

    def test_mood_worker_updates_user2_tag(self, qapp):
        """Worker should append mood hashtags to User2 tag."""
        mock_db = MagicMock()
        song = _make_song("/song.mp3")
        mock_db.get_song.return_value = song
        tracks = [song]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = ["relaxing"]

        with _PATCH_POOL, patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            mock_db.update_song_tags.assert_called_once_with("/song.mp3", User2="#relaxing")

    def test_mood_worker_multi_label_hashtags(self, qapp):
        """Worker should write multiple mood hashtags to User2."""
        mock_db = MagicMock()
        song = _make_song("/song.mp3")
        mock_db.get_song.return_value = song
        tracks = [song]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = ["happy", "uplifting", "summer"]

        with _PATCH_POOL, patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            mock_db.update_song_tags.assert_called_once_with(
                "/song.mp3", User2="#happy #summer #uplifting"
            )

    def test_mood_worker_no_save_when_all_fail(self, qapp):
        """Worker should not save database if nothing was analyzed."""
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3"), _make_song("/b.mp3")]

        mock_backend = MagicMock()
        mock_backend.is_available = True
        mock_backend.get_mood_tags.return_value = None

        with _PATCH_POOL, patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert results[0]["analyzed"] == 0
            assert results[0]["failed"] == 2
            mock_db.save.assert_not_called()

    def test_mood_worker_empty_tracks(self, qapp):
        """Worker should handle empty track list gracefully."""
        mock_db = MagicMock()

        mock_backend = MagicMock()
        mock_backend.is_available = True

        with _PATCH_POOL, patch("vdj_manager.analysis.mood_backend.get_backend", return_value=mock_backend):
            worker = MoodWorker(mock_db, [], max_workers=1, enable_online=False, model_name="heuristic")
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 0
            assert results[0]["failed"] == 0
            assert results[0]["results"] == []
            mock_db.save.assert_not_called()

    def test_mood_worker_online_enabled(self, qapp):
        """Worker should store online and model params."""
        mock_db = MagicMock()
        worker = MoodWorker(
            mock_db, [], max_workers=1,
            enable_online=True, lastfm_api_key="test_key",
            model_name="mtg-jamendo", threshold=0.15, max_tags=3,
        )
        assert worker._enable_online is True
        assert worker._lastfm_api_key == "test_key"
        assert worker._model_name == "mtg-jamendo"
        assert worker._threshold == 0.15
        assert worker._max_tags == 3


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
        result = {"analyzed": 1, "failed": 0, "results": [
            {"file_path": "/a.mp3", "mood": "happy", "status": "ok (local)"},
        ]}
        panel._on_mood_finished(result)
        assert panel.mood_btn.isEnabled()

    def test_mood_finished_with_error_key(self, qapp):
        """When result has 'error' key, should show error and not add results."""
        panel = AnalysisPanel()
        result = {
            "analyzed": 0, "failed": 0, "results": [],
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
            {"file_path": "/c.mp3", "mood": None, "status": "failed"},
        ]
        for r in results_data:
            panel.mood_results.add_result(r)

        panel._on_mood_finished({"analyzed": 2, "failed": 1, "results": results_data})
        assert panel.mood_results.row_count() == 3
        assert "2 analyzed" in panel.mood_status.text()
        assert "1 failed" in panel.mood_status.text()

    def test_mood_finished_emits_database_changed(self, qapp):
        """database_changed signal should emit when mood analysis modifies data."""
        panel = AnalysisPanel()
        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        result = {"analyzed": 1, "failed": 0, "results": [
            {"file_path": "/a.mp3", "mood": "relaxed", "status": "ok (local)"},
        ]}
        panel._on_mood_finished(result)
        assert len(signals) == 1

    def test_mood_finished_no_signal_when_none_analyzed(self, qapp):
        """database_changed should NOT emit when no tracks were analyzed."""
        panel = AnalysisPanel()
        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        result = {"analyzed": 0, "failed": 2, "results": [
            {"file_path": "/a.mp3", "mood": None, "status": "failed"},
            {"file_path": "/b.mp3", "mood": None, "status": "failed"},
        ]}
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
