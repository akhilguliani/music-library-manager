"""Tests for AnalysisPanel and analysis workers."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.widgets.analysis_panel import AnalysisPanel
from vdj_manager.ui.workers.analysis_workers import (
    EnergyWorker,
    MIKImportWorker,
    MoodWorker,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_song(path: str, energy: int | None = None, key: str | None = None) -> Song:
    grouping = f"Energy {energy}" if energy is not None else None
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


class TestEnergyWorker:
    """Tests for EnergyWorker."""

    def test_energy_worker_success(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.return_value = 7

            worker = EnergyWorker(mock_db, tracks)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            assert results[0]["failed"] == 0
            assert results[0]["results"][0]["energy"] == 7
            mock_db.update_song_tags.assert_called_once_with("/a.mp3", Grouping="Energy 7")
            mock_db.save.assert_called_once()

    def test_energy_worker_failure(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.return_value = None

            worker = EnergyWorker(mock_db, tracks)
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

        with patch("vdj_manager.analysis.energy.EnergyAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.analyze.side_effect = RuntimeError("bad file")

            worker = EnergyWorker(mock_db, tracks)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["failed"] == 1
            assert "error" in results[0]["results"][0]["status"]


class TestMIKImportWorker:
    """Tests for MIKImportWorker."""

    def test_mik_worker_finds_and_updates(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.analysis.audio_features.MixedInKeyReader") as MockReader:
            reader_instance = MockReader.return_value
            reader_instance.read_tags.return_value = {
                "energy": 8, "key": "Am", "bpm": None, "raw_tags": {}
            }

            worker = MIKImportWorker(mock_db, tracks)
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

        with patch("vdj_manager.analysis.audio_features.MixedInKeyReader") as MockReader:
            reader_instance = MockReader.return_value
            reader_instance.read_tags.return_value = {
                "energy": None, "key": None, "bpm": None, "raw_tags": {}
            }

            worker = MIKImportWorker(mock_db, tracks)
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

        with patch("vdj_manager.analysis.audio_features.MixedInKeyReader") as MockReader:
            reader_instance = MockReader.return_value
            reader_instance.read_tags.return_value = {
                "energy": 8, "key": None, "bpm": None, "raw_tags": {}
            }

            worker = MIKImportWorker(mock_db, tracks)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            # Found MIK data but didn't update because energy already set
            assert results[0]["found"] == 1
            assert results[0]["updated"] == 0


class TestMoodWorker:
    """Tests for MoodWorker."""

    def test_mood_worker_unavailable(self, qapp):
        mock_db = MagicMock()
        tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.is_available = False

            worker = MoodWorker(mock_db, tracks)
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
        tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.analysis.mood.MoodAnalyzer") as MockAnalyzer:
            analyzer_instance = MockAnalyzer.return_value
            analyzer_instance.is_available = True
            analyzer_instance.get_mood_tag.return_value = "happy"

            worker = MoodWorker(mock_db, tracks)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["analyzed"] == 1
            assert results[0]["results"][0]["mood"] == "happy"
            mock_db.update_song_tags.assert_called_once_with("/a.mp3", Comment="happy")
            mock_db.save.assert_called_once()


class TestAnalysisPanelHandlers:
    """Tests for AnalysisPanel event handlers."""

    def test_energy_finished_populates_results(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        panel.set_database(mock_db, [_make_song("/a.mp3")])

        result = {
            "analyzed": 1, "failed": 0,
            "results": [{"file_path": "/a.mp3", "energy": 7, "status": "ok"}],
        }
        panel._on_energy_finished(result)

        assert "1 analyzed" in panel.energy_status.text()
        assert panel.energy_results.row_count() == 1

    def test_energy_error_shows_message(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        panel.set_database(mock_db, [_make_song("/a.mp3")])

        panel._on_energy_error("librosa not installed")
        assert "Error" in panel.energy_status.text()
        assert panel.energy_all_btn.isEnabled()

    def test_mik_finished_populates_results(self, qapp):
        panel = AnalysisPanel()
        mock_db = MagicMock()
        panel.set_database(mock_db, [_make_song("/a.mp3")])

        result = {
            "found": 1, "updated": 1,
            "results": [{"file_path": "/a.mp3", "energy": 8, "key": "Am", "status": "updated"}],
        }
        panel._on_mik_finished(result)

        assert "1 found" in panel.mik_status.text()
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
                {"file_path": "/a.mp3", "mood": "happy", "status": "ok"},
                {"file_path": "/b.mp3", "mood": "sad", "status": "ok"},
            ],
        }
        panel._on_mood_finished(result)
        assert "2 analyzed" in panel.mood_status.text()
        assert panel.mood_results.row_count() == 2

    def test_database_changed_signal_emitted(self, qapp):
        panel = AnalysisPanel()
        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        result = {
            "analyzed": 1, "failed": 0,
            "results": [{"file_path": "/a.mp3", "energy": 5, "status": "ok"}],
        }
        panel._on_energy_finished(result)
        assert len(signals) == 1
