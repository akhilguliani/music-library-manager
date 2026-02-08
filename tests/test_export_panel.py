"""Tests for ExportPanel and export workers."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QCoreApplication

from vdj_manager.core.models import Song, Tags, Playlist
from vdj_manager.ui.widgets.export_panel import ExportPanel
from vdj_manager.ui.workers.export_workers import SeratoExportWorker, CrateExportWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_song(path: str) -> Song:
    return Song(file_path=path, tags=Tags(author="Artist", title="Title"))


class TestExportPanelCreation:
    """Tests for ExportPanel widget creation."""

    def test_panel_creation(self, qapp):
        panel = ExportPanel()
        assert panel.export_all_btn is not None
        assert panel.export_playlist_btn is not None
        assert panel.cues_only_check is not None
        assert panel.playlist_list is not None
        assert panel.export_results is not None

    def test_buttons_disabled_initially(self, qapp):
        panel = ExportPanel()
        assert not panel.export_all_btn.isEnabled()
        assert not panel.export_playlist_btn.isEnabled()

    def test_set_database_enables_export_all(self, qapp):
        panel = ExportPanel()
        mock_db = MagicMock()
        mock_db.playlists = []
        tracks = [_make_song("/a.mp3")]
        panel.set_database(mock_db, tracks)

        assert panel.export_all_btn.isEnabled()
        assert not panel.export_playlist_btn.isEnabled()

    def test_set_database_none(self, qapp):
        panel = ExportPanel()
        panel.set_database(None)

        assert not panel.export_all_btn.isEnabled()
        assert panel.playlist_list.count() == 0

    def test_playlists_populated(self, qapp):
        panel = ExportPanel()
        mock_db = MagicMock()
        mock_db.playlists = [
            Playlist(Name="Rock", file_paths=["/a.mp3", "/b.mp3"]),
            Playlist(Name="EDM", file_paths=["/c.mp3"]),
        ]
        tracks = [_make_song("/a.mp3")]
        panel.set_database(mock_db, tracks)

        assert panel.playlist_list.count() == 2
        assert "Rock" in panel.playlist_list.item(0).text()
        assert "EDM" in panel.playlist_list.item(1).text()

    def test_info_label_updated(self, qapp):
        panel = ExportPanel()
        mock_db = MagicMock()
        mock_db.playlists = [Playlist(Name="Mix", file_paths=[])]
        tracks = [_make_song("/a.mp3"), _make_song("/b.flac")]
        panel.set_database(mock_db, tracks)

        assert "audio tracks" in panel.info_label.text()
        assert "1 playlists" in panel.info_label.text()

    def test_is_running_false_initially(self, qapp):
        panel = ExportPanel()
        assert not panel.is_running()


class TestSeratoExportWorker:
    """Tests for SeratoExportWorker."""

    def test_export_worker_success(self, qapp):
        tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.export.serato.SeratoExporter") as MockExporter:
            exporter_instance = MockExporter.return_value
            exporter_instance.export_song.return_value = True

            worker = SeratoExportWorker(tracks)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["exported"] == 1
            assert results[0]["failed"] == 0

    def test_export_worker_failure(self, qapp):
        tracks = [_make_song("/a.mp3")]

        with patch("vdj_manager.export.serato.SeratoExporter") as MockExporter:
            exporter_instance = MockExporter.return_value
            exporter_instance.export_song.return_value = False

            worker = SeratoExportWorker(tracks)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["exported"] == 0
            assert results[0]["failed"] == 1


class TestCrateExportWorker:
    """Tests for CrateExportWorker."""

    def test_crate_worker_creates_crate(self, qapp):
        with tempfile.TemporaryDirectory() as tmpdir:
            serato_dir = Path(tmpdir) / "_Serato_"
            worker = CrateExportWorker("TestCrate", ["/a.mp3", "/b.mp3"], serato_dir)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0]["crate_name"] == "TestCrate"
            assert results[0]["track_count"] == 2
            assert Path(results[0]["crate_path"]).exists()


class TestExportPanelHandlers:
    """Tests for ExportPanel event handlers."""

    def test_export_finished_populates_results(self, qapp):
        panel = ExportPanel()
        result = {
            "exported": 2, "failed": 1,
            "results": [
                {"file_path": "/a.mp3", "status": "exported"},
                {"file_path": "/b.mp3", "status": "exported"},
                {"file_path": "/c.mp3", "status": "error: mutagen"},
            ],
        }
        panel._on_export_finished(result)

        assert "2 exported" in panel.export_status.text()
        assert panel.export_results.row_count() == 3

    def test_crate_finished_shows_result(self, qapp):
        panel = ExportPanel()
        result = {
            "crate_name": "MyMix",
            "crate_path": "/serato/Subcrates/MyMix.crate",
            "track_count": 10,
        }
        panel._on_crate_finished(result)

        assert "MyMix" in panel.export_status.text()
        assert "10 tracks" in panel.export_status.text()
        assert panel.export_results.row_count() == 1

    def test_export_error_shows_message(self, qapp):
        panel = ExportPanel()
        panel._on_export_error("mutagen not installed")
        assert "Error" in panel.export_status.text()

    def test_export_completed_signal_emitted(self, qapp):
        panel = ExportPanel()
        signals = []
        panel.export_completed.connect(lambda: signals.append(True))

        result = {"exported": 1, "failed": 0, "results": [{"file_path": "/a.mp3", "status": "ok"}]}
        panel._on_export_finished(result)
        assert len(signals) == 1

    def test_playlist_selection_enables_button(self, qapp):
        panel = ExportPanel()
        mock_db = MagicMock()
        mock_db.playlists = [Playlist(Name="Mix", file_paths=["/a.mp3"])]
        tracks = [_make_song("/a.mp3")]
        panel.set_database(mock_db, tracks)

        # Select the playlist
        panel.playlist_list.setCurrentRow(0)
        assert panel.export_playlist_btn.isEnabled()
