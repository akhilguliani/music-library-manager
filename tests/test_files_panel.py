"""Tests for FilesPanel and file workers."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.widgets.files_panel import FilesPanel
from vdj_manager.ui.workers.file_workers import (
    DuplicateWorker,
    ImportWorker,
    RemoveWorker,
    ScanWorker,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_song(path: str, author: str = "Artist", title: str = "Title") -> Song:
    return Song(file_path=path, tags=Tags(author=author, title=title))


class TestFilesPanelCreation:
    """Tests for FilesPanel widget creation."""

    def test_panel_creation(self, qapp):
        panel = FilesPanel()
        assert panel.sub_tabs is not None
        assert panel.sub_tabs.count() == 5

    def test_sub_tab_names(self, qapp):
        panel = FilesPanel()
        assert panel.sub_tabs.tabText(0) == "Scan"
        assert panel.sub_tabs.tabText(1) == "Import"
        assert panel.sub_tabs.tabText(2) == "Remove"
        assert panel.sub_tabs.tabText(3) == "Remap"
        assert panel.sub_tabs.tabText(4) == "Duplicates"

    def test_set_database(self, qapp):
        panel = FilesPanel()
        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([_make_song("/a.mp3")])
        panel.set_database(mock_db)
        assert panel._database is mock_db
        assert len(panel._tracks) == 1

    def test_set_database_none(self, qapp):
        panel = FilesPanel()
        panel.set_database(None)
        assert panel._database is None
        assert len(panel._tracks) == 0


class TestScanWorker:
    """Tests for ScanWorker."""

    def test_scan_empty_directory(self, qapp):
        with tempfile.TemporaryDirectory() as tmpdir:
            worker = ScanWorker(Path(tmpdir), set(), True)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0] == []

    def test_scan_finds_audio_files(self, qapp):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create audio files
            (Path(tmpdir) / "song1.mp3").write_bytes(b"fake mp3")
            (Path(tmpdir) / "song2.flac").write_bytes(b"fake flac")
            (Path(tmpdir) / "doc.pdf").write_bytes(b"fake pdf")

            worker = ScanWorker(Path(tmpdir), set(), True)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            found = results[0]
            names = {f["name"] for f in found}
            assert "song1" in names
            assert "song2" in names
            assert "doc" not in names

    def test_scan_excludes_existing(self, qapp):
        with tempfile.TemporaryDirectory() as tmpdir:
            song_path = str(Path(tmpdir) / "song1.mp3")
            Path(song_path).write_bytes(b"fake mp3")

            worker = ScanWorker(Path(tmpdir), {song_path}, True)
            results = []
            worker.finished_work.connect(lambda r: results.append(r))
            worker.start()
            worker.wait(5000)
            QCoreApplication.processEvents()

            assert len(results) == 1
            assert results[0] == []


class TestImportWorker:
    """Tests for ImportWorker."""

    def test_import_returns_paths_to_add(self, qapp):
        """ImportWorker should return paths without touching the database."""
        worker = ImportWorker(["/a.mp3", "/b.mp3"])
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        assert results[0]["paths_to_add"] == ["/a.mp3", "/b.mp3"]

    def test_import_does_not_mutate_database(self, qapp):
        """ImportWorker must not reference or mutate any database object."""
        worker = ImportWorker(["/a.mp3"])
        assert not hasattr(worker, "database")
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()
        assert results[0]["paths_to_add"] == ["/a.mp3"]


class TestRemoveWorker:
    """Tests for RemoveWorker."""

    def test_remove_returns_paths_to_remove(self, qapp):
        """RemoveWorker should return paths without touching the database."""
        worker = RemoveWorker(["/a.mp3", "/b.mp3"])
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        assert results[0]["paths_to_remove"] == ["/a.mp3", "/b.mp3"]

    def test_remove_does_not_mutate_database(self, qapp):
        """RemoveWorker must not reference or mutate any database object."""
        worker = RemoveWorker(["/a.mp3"])
        assert not hasattr(worker, "database")
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()
        assert results[0]["paths_to_remove"] == ["/a.mp3"]


class TestDuplicateWorker:
    """Tests for DuplicateWorker."""

    def test_finds_metadata_duplicates(self, qapp):
        tracks = [
            _make_song("/a/song.mp3", "Artist", "Title"),
            _make_song("/b/song.mp3", "Artist", "Title"),
            _make_song("/c/other.mp3", "Other", "Other"),
        ]

        worker = DuplicateWorker(tracks, by_metadata=True, by_filename=False, by_hash=False)
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        summary = results[0]["summary"]
        assert summary["metadata_groups"] == 1

    def test_finds_filename_duplicates(self, qapp):
        tracks = [
            _make_song("/a/song.mp3", "Artist1", "Title1"),
            _make_song("/b/song.mp3", "Artist2", "Title2"),
        ]

        worker = DuplicateWorker(tracks, by_metadata=False, by_filename=True, by_hash=False)
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        summary = results[0]["summary"]
        assert summary["filename_groups"] == 1


class TestFilesPanelHandlers:
    """Tests for FilesPanel event handlers."""

    def test_scan_finished_populates_results(self, qapp):
        panel = FilesPanel()
        files = [
            {
                "name": "song.mp3",
                "file_path": "/music/song.mp3",
                "file_size": 5000,
                "extension": ".mp3",
            },
        ]
        panel._on_scan_finished(files)

        assert panel.scan_results.row_count() == 1
        assert len(panel._scanned_files) == 1
        assert "1 new" in panel.scan_status.text()

    def test_import_finished_applies_mutations_on_main_thread(self, qapp):
        panel = FilesPanel()
        panel._database = MagicMock()
        panel._database.iter_songs.return_value = iter([])
        panel._scanned_files = [{"name": "a.mp3", "file_path": "/a.mp3"}]

        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        panel._on_import_finished({"paths_to_add": ["/a.mp3"]})

        assert len(signals) == 1
        assert "Imported 1" in panel.import_status.text()
        panel._database.add_song.assert_called_once_with("/a.mp3")
        panel._database.save.assert_called_once()

    def test_remove_finished_applies_mutations_on_main_thread(self, qapp):
        panel = FilesPanel()
        panel._database = MagicMock()
        panel._database.remove_song.return_value = True
        panel._database.iter_songs.return_value = iter([])

        signals = []
        panel.database_changed.connect(lambda: signals.append(True))

        panel._on_remove_finished({"paths_to_remove": ["/a.mp3", "/b.mp3", "/c.mp3"]})

        assert len(signals) == 1
        assert "Removed 3" in panel.remove_status.text()
        assert panel._database.remove_song.call_count == 3
        panel._database.save.assert_called_once()

    def test_remap_finished_applies_mutations_on_main_thread(self, qapp):
        panel = FilesPanel()
        panel._database = MagicMock()
        panel._database.remap_path.return_value = True
        panel._database.iter_songs.return_value = iter([])

        panel._on_remap_finished(
            {
                "remappings": [("D:/old.mp3", "/new.mp3")],
                "skipped": 5,
            }
        )

        assert "Remapped 1" in panel.remap_status.text()
        assert "skipped 5" in panel.remap_status.text()
        panel._database.remap_path.assert_called_once_with("D:/old.mp3", "/new.mp3")
        panel._database.save.assert_called_once()

    def test_dup_finished_shows_summary(self, qapp):
        panel = FilesPanel()
        result = {
            "by_metadata": {},
            "by_filename": {},
            "summary": {"metadata_groups": 3, "filename_groups": 2, "exact_duplicates": 0},
        }
        panel._on_dup_finished(result)

        assert "Metadata: 3" in panel.dup_status.text()
        assert "Filename: 2" in panel.dup_status.text()

    def test_scan_error(self, qapp):
        panel = FilesPanel()
        panel._on_scan_error("Permission denied")
        assert "Error" in panel.scan_status.text()
