"""Comprehensive tests for mood analysis across all layers.

Tests cover:
1. MoodAnalyzer class (backend unit tests)
2. MoodWorker (worker thread behavior)
3. AnalysisPanel mood handlers (GUI integration)
"""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QCoreApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.analysis.mood import MoodAnalyzer
from vdj_manager.ui.widgets.analysis_panel import AnalysisPanel
from vdj_manager.ui.workers.analysis_workers import MoodWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_song(path: str, comment: str | None = None) -> Song:
    return Song(file_path=path, tags=Tags(author="Artist", title="Title", comment=comment))


# =============================================================================
# MoodAnalyzer unit tests
# =============================================================================


class TestMoodAnalyzerInit:
    """Tests for MoodAnalyzer initialization and availability."""

    def test_is_available_false_without_essentia(self):
        """MoodAnalyzer.is_available should be False when essentia isn't installed."""
        with patch.dict("sys.modules", {"essentia": None, "essentia.standard": None}):
            # Force reimport
            analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
            analyzer._model = None
            analyzer._model_path = None
            analyzer._essentia_available = False
            assert not analyzer.is_available

    def test_moods_constant_defined(self):
        """MOODS list should contain expected mood tags."""
        assert "happy" in MoodAnalyzer.MOODS
        assert "sad" in MoodAnalyzer.MOODS
        assert "aggressive" in MoodAnalyzer.MOODS
        assert "relaxed" in MoodAnalyzer.MOODS
        assert len(MoodAnalyzer.MOODS) == 7

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

    def test_get_mood_tag_returns_primary_mood(self):
        """get_mood_tag() should return the primary_mood from analyze()."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True
        with patch.object(analyzer, "analyze", return_value={"primary_mood": "energetic"}):
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

    def test_analyze_mood_features_returns_dict(self):
        """_analyze_mood_features should return mood dict with expected structure."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es

        # Mock Essentia extractors
        mock_es.RhythmExtractor2013.return_value.return_value = (
            128.0,  # bpm
            [0.5, 1.0],  # beats
            0.9,  # beats_confidence
            [],  # ticks
            0.95,  # ticks_confidence
        )
        mock_es.Spectrum.return_value.return_value = [0.1, 0.2]  # spectrum
        mock_es.Centroid.return_value.return_value = 2500.0  # centroid
        mock_es.Energy.return_value.return_value = 0.5  # energy
        mock_es.RMS.return_value.return_value = 0.15  # rms

        fake_audio = [0.0] * 100
        result = analyzer._analyze_mood_features(fake_audio)

        assert "primary_mood" in result
        assert "moods" in result
        assert "features" in result
        assert result["features"]["bpm"] == 128.0
        assert result["features"]["rms"] == 0.15
        assert result["primary_mood"] in result["moods"]

    def test_analyze_mood_features_catches_exceptions(self):
        """_analyze_mood_features should return 'unknown' on error."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es
        mock_es.RhythmExtractor2013.return_value.side_effect = RuntimeError("bad audio")

        result = analyzer._analyze_mood_features([0.0])

        assert result["primary_mood"] == "unknown"
        assert result["moods"] == {}

    def test_analyze_full_flow_with_mocked_essentia(self):
        """Full analyze() flow with mocked essentia."""
        analyzer = MoodAnalyzer.__new__(MoodAnalyzer)
        analyzer._essentia_available = True

        mock_es = MagicMock()
        analyzer._es = mock_es

        # Mock MonoLoader
        mock_es.MonoLoader.return_value.return_value = [0.0] * 100

        # Mock extractors
        mock_es.RhythmExtractor2013.return_value.return_value = (
            140.0, [], 0.9, [], 0.95
        )
        mock_es.Spectrum.return_value.return_value = [0.1]
        mock_es.Centroid.return_value.return_value = 3500.0
        mock_es.Energy.return_value.return_value = 0.7
        mock_es.RMS.return_value.return_value = 0.2

        result = analyzer.analyze("/fake/song.mp3")

        assert result is not None
        assert "primary_mood" in result
        assert result["primary_mood"] in ("energetic", "chill", "bright", "dark")
        mock_es.MonoLoader.assert_called_once_with(filename="/fake/song.mp3", sampleRate=16000)


# =============================================================================
# MoodWorker tests
# =============================================================================


class TestMoodWorkerDetailed:
    """Detailed tests for MoodWorker behavior."""

    def test_mood_worker_get_mood_tag_returns_none(self, qapp):
        """Worker should count as failed when get_mood_tag returns None."""
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            instance = MockAnalyzer.return_value
            instance.is_available = True
            instance.get_mood_tag.return_value = None

            worker = MoodWorker(mock_db, tracks)
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

        with patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            instance = MockAnalyzer.return_value
            instance.is_available = True
            instance.get_mood_tag.side_effect = RuntimeError("analysis crashed")

            worker = MoodWorker(mock_db, tracks)
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

        with patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            instance = MockAnalyzer.return_value
            instance.is_available = True
            instance.get_mood_tag.side_effect = ["happy", None, "aggressive"]

            worker = MoodWorker(mock_db, tracks)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 2
            assert results[0]["failed"] == 1
            assert len(results[0]["results"]) == 3
            assert results[0]["results"][0]["mood"] == "happy"
            assert results[0]["results"][1]["mood"] is None
            assert results[0]["results"][2]["mood"] == "aggressive"
            mock_db.save.assert_called_once()

    def test_mood_worker_updates_comment_tag(self, qapp):
        """Worker should update Comment tag with mood string."""
        mock_db = MagicMock()
        tracks = [_make_song("/song.mp3")]

        with patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            instance = MockAnalyzer.return_value
            instance.is_available = True
            instance.get_mood_tag.return_value = "relaxed"

            worker = MoodWorker(mock_db, tracks)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            mock_db.update_song_tags.assert_called_once_with("/song.mp3", Comment="relaxed")

    def test_mood_worker_no_save_when_all_fail(self, qapp):
        """Worker should not save database if nothing was analyzed."""
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3"), _make_song("/b.mp3")]

        with patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            instance = MockAnalyzer.return_value
            instance.is_available = True
            instance.get_mood_tag.return_value = None

            worker = MoodWorker(mock_db, tracks)
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

        with patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            instance = MockAnalyzer.return_value
            instance.is_available = True

            worker = MoodWorker(mock_db, [])
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
            {"file_path": "/a.mp3", "mood": "happy", "status": "ok"},
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
        panel = AnalysisPanel()
        result = {
            "analyzed": 2, "failed": 1, "results": [
                {"file_path": "/a.mp3", "mood": "happy", "status": "ok"},
                {"file_path": "/b.mp3", "mood": "sad", "status": "ok"},
                {"file_path": "/c.mp3", "mood": None, "status": "failed"},
            ],
        }
        panel._on_mood_finished(result)
        assert panel.mood_results.row_count() == 3
        assert "2 analyzed" in panel.mood_status.text()
        assert "1 failed" in panel.mood_status.text()

    def test_mood_finished_emits_database_changed(self, qapp):
        """database_changed signal should emit when mood analysis modifies data."""
        panel = AnalysisPanel()
        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        result = {"analyzed": 1, "failed": 0, "results": [
            {"file_path": "/a.mp3", "mood": "relaxed", "status": "ok"},
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
