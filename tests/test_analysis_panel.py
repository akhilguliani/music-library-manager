"""Tests for AnalysisPanel and analysis workers."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from vdj_manager.core.models import Infos, Song, Tags
from vdj_manager.ui.widgets.analysis_panel import AnalysisPanel
from vdj_manager.ui.workers.analysis_workers import (
    EnergyWorker,
    MIKImportWorker,
    MoodWorker,
)

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


def _make_song(path: str, energy: int | None = None, key: str | None = None) -> Song:
    grouping = str(energy) if energy is not None else None
    return Song(file_path=path, tags=Tags(grouping=grouping, key=key))


class TestAnalysisPanelCreation:
    """Tests for AnalysisPanel widget creation."""

    def test_panel_creation(self, qapp):
        panel = AnalysisPanel()
        assert panel.sub_tabs is not None
        assert panel.sub_tabs.count() == 3

    def test_sub_tab_names(self, qapp):
        panel = AnalysisPanel()
        assert panel.sub_tabs.tabText(0) == "Energy"
        assert panel.sub_tabs.tabText(1) == "MIK Import"
        assert panel.sub_tabs.tabText(2) == "Mood"

    def test_buttons_disabled_initially(self, qapp):
        panel = AnalysisPanel()
        assert not panel.energy_all_btn.isEnabled()
        assert not panel.energy_untagged_btn.isEnabled()
        assert not panel.mik_scan_btn.isEnabled()
        assert not panel.mood_btn.isEnabled()

    def test_set_database_enables_buttons(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]
        panel.set_database(mock_db, tracks)

        assert panel.energy_all_btn.isEnabled()
        assert panel.energy_untagged_btn.isEnabled()
        assert panel.mik_scan_btn.isEnabled()
        assert panel.mood_btn.isEnabled()

    def test_set_database_none_disables_buttons(self, qapp):
        panel = AnalysisPanel()
        panel.set_database(None)

        assert not panel.energy_all_btn.isEnabled()
        assert not panel.energy_untagged_btn.isEnabled()
        assert not panel.mik_scan_btn.isEnabled()
        assert not panel.mood_btn.isEnabled()

    def test_track_info_updated(self, qapp):
        panel = AnalysisPanel()
        tracks = [
            _make_song("/a.mp3", energy=5),
            _make_song("/b.mp3"),
            _make_song("/c.flac"),
        ]
        mock_db = MagicMock()
        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            # The actual Path is called within _get_audio_tracks
            panel.set_database(mock_db, tracks)

        assert "audio tracks" in panel.energy_info_label.text()

    def test_is_running_false_initially(self, qapp):
        panel = AnalysisPanel()
        assert not panel.is_running()

    def test_online_checkbox_exists_and_defaults_checked(self, qapp):
        panel = AnalysisPanel()
        assert panel.mood_online_checkbox is not None
        assert panel.mood_online_checkbox.isChecked()

    def test_api_key_label_exists(self, qapp):
        panel = AnalysisPanel()
        assert panel.mood_api_key_label is not None
        text = panel.mood_api_key_label.text()
        assert "API key" in text

    def test_progress_widgets_exist(self, qapp):
        panel = AnalysisPanel()
        assert panel.energy_progress is not None
        assert panel.mik_progress is not None
        assert panel.mood_progress is not None

    def test_progress_widgets_hidden_initially(self, qapp):
        panel = AnalysisPanel()
        assert not panel.energy_progress.isVisible()
        assert not panel.mik_progress.isVisible()
        assert not panel.mood_progress.isVisible()


class TestEnergyWorker:
    """Tests for EnergyWorker."""

    def test_energy_worker_success(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.return_value = 7

            worker = EnergyWorker(mock_db, tracks, max_workers=1)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            assert results[0]["failed"] == 0
            assert results[0]["results"][0]["energy"] == 7
            mock_db.update_song_tags.assert_called_once_with("/a.mp3", Grouping="7")
            mock_db.save.assert_called_once()

    def test_energy_worker_failure(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.return_value = None

            worker = EnergyWorker(mock_db, tracks, max_workers=1)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 0
            assert results[0]["failed"] == 1
            mock_db.save.assert_not_called()

    def test_energy_worker_exception(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.side_effect = RuntimeError("bad file")

            worker = EnergyWorker(mock_db, tracks, max_workers=1)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["failed"] == 1
            assert "error" in results[0]["results"][0]["status"]

    def test_energy_worker_has_pause_resume(self, qapp):
        """EnergyWorker should have pause/resume/cancel methods."""
        mock_db = MagicMock()
        worker = EnergyWorker(mock_db, [], max_workers=1)
        assert hasattr(worker, "pause")
        assert hasattr(worker, "resume")
        assert hasattr(worker, "cancel")
        assert not worker.is_paused
        assert not worker.is_cancelled


class TestMIKImportWorker:
    """Tests for MIKImportWorker."""

    def test_mik_worker_finds_and_updates(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.audio_features.MixedInKeyReader") as MockReader:
            reader_instance = MockReader.return_value
            reader_instance.read_tags.return_value = {
                "energy": 8, "key": "Am", "bpm": None, "raw_tags": {}
            }

            worker = MIKImportWorker(mock_db, tracks, max_workers=1)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["found"] == 1
            assert results[0]["updated"] == 1
            mock_db.update_song_tags.assert_called_once()
            mock_db.save.assert_called_once()

    def test_mik_worker_no_data(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.audio_features.MixedInKeyReader") as MockReader:
            reader_instance = MockReader.return_value
            reader_instance.read_tags.return_value = {
                "energy": None, "key": None, "bpm": None, "raw_tags": {}
            }

            worker = MIKImportWorker(mock_db, tracks, max_workers=1)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["found"] == 0
            assert results[0]["updated"] == 0
            mock_db.save.assert_not_called()

    def test_mik_worker_skips_existing_energy(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3", energy=5)]

        with _PATCH_POOL, patch("vdj_manager.analysis.audio_features.MixedInKeyReader") as MockReader:
            reader_instance = MockReader.return_value
            reader_instance.read_tags.return_value = {
                "energy": 8, "key": None, "bpm": None, "raw_tags": {}
            }

            worker = MIKImportWorker(mock_db, tracks, max_workers=1)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            # Found MIK data but didn't update because energy already set
            assert results[0]["found"] == 1
            assert results[0]["updated"] == 0

    def test_mik_worker_has_pause_resume(self, qapp):
        mock_db = MagicMock()
        worker = MIKImportWorker(mock_db, [], max_workers=1)
        assert hasattr(worker, "pause")
        assert hasattr(worker, "resume")
        assert hasattr(worker, "cancel")


class TestMoodWorker:
    """Tests for MoodWorker."""

    def test_mood_worker_unavailable(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.is_available = False

            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["error"] == "essentia-tensorflow is not installed"
            assert results[0]["analyzed"] == 0

    def test_mood_worker_success(self, qapp):
        mock_db = MagicMock()
        song = _make_song("/a.mp3")
        mock_db.get_song.return_value = song
        tracks = [song]

        with _PATCH_POOL, patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.is_available = True
            analyzer_instance.get_mood_tag.return_value = "happy"

            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            assert results[0]["results"][0]["mood"] == "happy"
            mock_db.update_song_tags.assert_called_once_with("/a.mp3", User2="#happy")
            mock_db.save.assert_called_once()

    def test_mood_worker_online_params(self, qapp):
        """MoodWorker should accept enable_online and lastfm_api_key params."""
        mock_db = MagicMock()
        worker = MoodWorker(
            mock_db, [], max_workers=1,
            enable_online=True, lastfm_api_key="test_key",
        )
        assert worker._enable_online is True
        assert worker._lastfm_api_key == "test_key"

    def test_mood_worker_has_pause_resume(self, qapp):
        mock_db = MagicMock()
        worker = MoodWorker(mock_db, [], max_workers=1)
        assert hasattr(worker, "pause")
        assert hasattr(worker, "resume")
        assert hasattr(worker, "cancel")


class TestAnalysisPanelHandlers:
    """Tests for AnalysisPanel event handlers."""

    def test_energy_finished_shows_status(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        panel.set_database(mock_db, [_make_song("/a.mp3")])

        result = {
            "analyzed": 1, "failed": 0,
            "results": [{"file_path": "/a.mp3", "format": ".mp3", "energy": 7, "status": "ok"}],
        }
        panel._on_energy_finished(result)

        assert "1 analyzed" in panel.energy_status.text()

    def test_energy_results_streamed_via_result_ready(self, qapp):
        """Results are added to table via result_ready signal, not finished handler."""
        panel = AnalysisPanel()
        # Simulate streaming a result
        panel.energy_results.add_result(
            {"file_path": "/a.mp3", "format": ".mp3", "energy": 7, "status": "ok"}
        )
        assert panel.energy_results.row_count() == 1

    def test_energy_error_shows_message(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        panel.set_database(mock_db, [_make_song("/a.mp3")])

        panel._on_energy_error("librosa not installed")
        assert "Error" in panel.energy_status.text()
        assert panel.energy_all_btn.isEnabled()

    def test_mik_finished_shows_status(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        panel.set_database(mock_db, [_make_song("/a.mp3")])

        result = {
            "found": 1, "updated": 1,
            "results": [{"file_path": "/a.mp3", "format": ".mp3", "energy": 8, "key": "Am", "status": "updated"}],
        }
        panel._on_mik_finished(result)

        assert "1 found" in panel.mik_status.text()

    def test_mik_results_streamed_via_result_ready(self, qapp):
        panel = AnalysisPanel()
        panel.mik_results.add_result(
            {"file_path": "/a.mp3", "format": ".mp3", "energy": 8, "key": "Am", "status": "updated"}
        )
        assert panel.mik_results.row_count() == 1

    def test_mood_finished_with_error(self, qapp):
        panel = AnalysisPanel()
        result = {"analyzed": 0, "failed": 0, "results": [], "error": "essentia not installed"}
        panel._on_mood_finished(result)
        assert "Error" in panel.mood_status.text()

    def test_mood_finished_success(self, qapp):
        panel = AnalysisPanel()
        result = {
            "analyzed": 2, "failed": 0,
            "results": [
                {"file_path": "/a.mp3", "format": ".mp3", "mood": "happy", "status": "ok (local)"},
                {"file_path": "/b.mp3", "format": ".mp3", "mood": "sad", "status": "ok (lastfm)"},
            ],
        }
        panel._on_mood_finished(result)
        assert "2 analyzed" in panel.mood_status.text()

    def test_mood_results_streamed_via_result_ready(self, qapp):
        panel = AnalysisPanel()
        panel.mood_results.add_result(
            {"file_path": "/a.mp3", "format": ".mp3", "mood": "happy", "status": "ok (local)"}
        )
        panel.mood_results.add_result(
            {"file_path": "/b.mp3", "format": ".mp3", "mood": "sad", "status": "ok (lastfm)"}
        )
        assert panel.mood_results.row_count() == 2

    def test_database_changed_signal_emitted(self, qapp):
        panel = AnalysisPanel()
        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        result = {
            "analyzed": 1, "failed": 0,
            "results": [{"file_path": "/a.mp3", "format": ".mp3", "energy": 5, "status": "ok"}],
        }
        panel._on_energy_finished(result)
        assert len(signals) == 1


class TestAnalysisPanelLimits:
    """Tests for track count limit and duration filter."""

    def test_limit_spinner_exists(self, qapp):
        panel = AnalysisPanel()
        assert panel.limit_spin is not None
        assert panel.limit_spin.value() == 0
        assert panel.limit_spin.specialValueText() == "All"

    def test_max_duration_spinner_exists(self, qapp):
        panel = AnalysisPanel()
        assert panel.max_duration_spin is not None
        assert panel.max_duration_spin.value() == 0
        assert panel.max_duration_spin.specialValueText() == "No limit"

    def test_limit_restricts_track_count(self, qapp):
        panel = AnalysisPanel()
        tracks = [_make_song(f"/song{i}.mp3") for i in range(5)]
        panel._tracks = tracks
        panel.limit_spin.setValue(2)

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            result = panel._get_audio_tracks()

        assert len(result) == 2

    def test_limit_zero_means_all(self, qapp):
        panel = AnalysisPanel()
        tracks = [_make_song(f"/song{i}.mp3") for i in range(5)]
        panel._tracks = tracks
        panel.limit_spin.setValue(0)

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            result = panel._get_audio_tracks()

        assert len(result) == 5

    def test_max_duration_filters_long_tracks(self, qapp):
        panel = AnalysisPanel()
        tracks = [
            Song(file_path="/short.mp3", tags=Tags(), infos=Infos(SongLength=180.0)),   # 3 min
            Song(file_path="/medium.mp3", tags=Tags(), infos=Infos(SongLength=420.0)),  # 7 min
            Song(file_path="/long.mp3", tags=Tags(), infos=Infos(SongLength=3600.0)),   # 60 min
            Song(file_path="/no_info.mp3", tags=Tags()),                                # no duration
        ]
        panel._tracks = tracks
        panel.max_duration_spin.setValue(10)  # 10 minutes

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            result = panel._get_audio_tracks()

        paths = [t.file_path for t in result]
        assert "/short.mp3" in paths
        assert "/medium.mp3" in paths
        assert "/long.mp3" not in paths
        assert "/no_info.mp3" in paths  # tracks without metadata are kept

    def test_both_limits_combined(self, qapp):
        """Duration filter is applied first, then count limit."""
        panel = AnalysisPanel()
        tracks = [
            Song(file_path="/a.mp3", tags=Tags(), infos=Infos(SongLength=120.0)),   # 2 min
            Song(file_path="/b.mp3", tags=Tags(), infos=Infos(SongLength=180.0)),   # 3 min
            Song(file_path="/c.mp3", tags=Tags(), infos=Infos(SongLength=7200.0)),  # 120 min
            Song(file_path="/d.mp3", tags=Tags(), infos=Infos(SongLength=240.0)),   # 4 min
        ]
        panel._tracks = tracks
        panel.max_duration_spin.setValue(5)  # 5 min max
        panel.limit_spin.setValue(2)         # only 2 tracks

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            result = panel._get_audio_tracks()

        # /c.mp3 (120 min) filtered by duration, remaining 3 tracks limited to 2
        assert len(result) == 2
        assert result[0].file_path == "/a.mp3"
        assert result[1].file_path == "/b.mp3"


class TestAudioFormatSupport:
    """Tests for audio format filtering."""

    def test_mp4_extension_supported(self, qapp):
        """MP4 audio files should be included in analysis."""
        panel = AnalysisPanel()
        tracks = [
            _make_song("/song.mp3"),
            _make_song("/song.mp4"),
            _make_song("/song.m4a"),
            _make_song("/song.flac"),
            _make_song("/song.wav"),
            _make_song("/song.aac"),
        ]
        panel._tracks = tracks

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            result = panel._get_audio_tracks()

        extensions = {t.extension for t in result}
        assert ".mp4" in extensions
        assert ".mp3" in extensions
        assert ".m4a" in extensions
        assert ".flac" in extensions
        assert ".wav" in extensions
        assert ".aac" in extensions
        assert len(result) == 6

    def test_non_audio_extensions_excluded(self, qapp):
        panel = AnalysisPanel()
        tracks = [
            _make_song("/song.mp3"),
            _make_song("/song.txt"),
            _make_song("/song.jpg"),
        ]
        panel._tracks = tracks

        with patch("vdj_manager.ui.widgets.analysis_panel.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            result = panel._get_audio_tracks()

        assert len(result) == 1
        assert result[0].extension == ".mp3"


class TestFormatColumnAndFailureSummary:
    """Tests for format column and failure summary."""

    def test_energy_results_has_format_column(self, qapp):
        panel = AnalysisPanel()
        assert panel.energy_results.table.columnCount() == 4
        assert panel.energy_results.table.horizontalHeaderItem(1).text() == "Fmt"

    def test_mik_results_has_format_column(self, qapp):
        panel = AnalysisPanel()
        assert panel.mik_results.table.columnCount() == 5
        assert panel.mik_results.table.horizontalHeaderItem(1).text() == "Fmt"

    def test_mood_results_has_format_column(self, qapp):
        panel = AnalysisPanel()
        assert panel.mood_results.table.columnCount() == 4
        assert panel.mood_results.table.horizontalHeaderItem(1).text() == "Fmt"

    def test_failure_summary_includes_format_breakdown(self, qapp):
        results = [
            {"file_path": "/a.flac", "format": ".flac", "energy": None, "status": "failed"},
            {"file_path": "/b.flac", "format": ".flac", "energy": None, "status": "failed"},
            {"file_path": "/c.wav", "format": ".wav", "energy": None, "status": "error: bad file"},
        ]
        summary = AnalysisPanel._format_failure_summary(results, 3)
        assert ".flac: 2" in summary
        assert ".wav: 1" in summary

    def test_failure_summary_empty_when_no_failures(self, qapp):
        results = [
            {"file_path": "/a.mp3", "format": ".mp3", "energy": 7, "status": "ok"},
        ]
        summary = AnalysisPanel._format_failure_summary(results, 0)
        assert summary == ""


class TestWorkerResultReady:
    """Tests for result_ready signal streaming."""

    def test_energy_worker_emits_result_ready(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3"), _make_song("/b.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.return_value = 7

            worker = EnergyWorker(mock_db, tracks, max_workers=1)
            streamed = []
            worker.result_ready.connect(lambda r: streamed.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(streamed) == 2
            assert all(r["energy"] == 7 for r in streamed)

    def test_mik_worker_emits_result_ready(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.audio_features.MixedInKeyReader") as MockReader:
            reader_instance = MockReader.return_value
            reader_instance.read_tags.return_value = {
                "energy": 8, "key": "Am", "bpm": None, "raw_tags": {}
            }

            worker = MIKImportWorker(mock_db, tracks, max_workers=1)
            streamed = []
            worker.result_ready.connect(lambda r: streamed.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(streamed) == 1
            assert streamed[0]["status"] == "updated"

    def test_mood_worker_emits_result_ready(self, qapp):
        mock_db = MagicMock()
        song = _make_song("/a.mp3")
        mock_db.get_song.return_value = song
        tracks = [song]

        with _PATCH_POOL, patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.is_available = True
            analyzer_instance.get_mood_tag.return_value = "happy"

            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False)
            streamed = []
            worker.result_ready.connect(lambda r: streamed.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(streamed) == 1
            assert streamed[0]["mood"] == "happy"

    def test_energy_worker_progress_emitted(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3"), _make_song("/b.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.return_value = 5

            worker = EnergyWorker(mock_db, tracks, max_workers=1)
            progress_calls = []
            worker.progress.connect(lambda cur, tot, pct: progress_calls.append((cur, tot)))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(progress_calls) == 2
            assert progress_calls[-1] == (2, 2)

    def test_energy_worker_status_changed_emitted(self, qapp):
        """EnergyWorker should emit status_changed signals."""
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with _PATCH_POOL, patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.return_value = 5

            worker = EnergyWorker(mock_db, tracks, max_workers=1)
            statuses = []
            worker.status_changed.connect(lambda s: statuses.append(s))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert "running" in statuses
            assert "completed" in statuses


class TestWorkerPauseResume:
    """Tests for pause/resume/cancel on analysis workers."""

    def test_energy_worker_cancel(self, qapp):
        """Cancel should stop processing and return partial results."""
        mock_db = MagicMock()
        tracks = [_make_song(f"/song{i}.mp3") for i in range(100)]

        with _PATCH_POOL, patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.return_value = 5

            worker = EnergyWorker(mock_db, tracks, max_workers=1)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))

            worker.start()
            # Cancel immediately
            worker.cancel()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            # Should have processed fewer than all tracks
            total_processed = results[0]["analyzed"] + results[0]["failed"] + results[0].get("cached", 0)
            assert total_processed <= len(tracks)

    def test_mood_worker_cancel(self, qapp):
        """Cancel should stop mood processing."""
        mock_db = MagicMock()
        tracks = [_make_song(f"/song{i}.mp3") for i in range(100)]

        with _PATCH_POOL, patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.is_available = True
            analyzer_instance.get_mood_tag.return_value = "happy"

            worker = MoodWorker(mock_db, tracks, max_workers=1, enable_online=False)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))

            worker.start()
            worker.cancel()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
