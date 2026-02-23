"""Tests for DatabasePanel operations: backup, validate, clean."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.widgets.database_panel import DatabasePanel
from vdj_manager.ui.workers.database_worker import BackupWorker, ValidateWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestDatabasePanelButtons:
    """Tests for database panel action buttons."""

    def test_backup_button_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.backup_btn is not None
        assert panel.backup_btn.text() == "Backup"

    def test_validate_button_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.validate_btn is not None
        assert panel.validate_btn.text() == "Validate"

    def test_clean_button_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.clean_btn is not None
        assert panel.clean_btn.text() == "Clean"

    def test_buttons_disabled_without_database(self, qapp):
        panel = DatabasePanel()
        assert not panel.backup_btn.isEnabled()
        assert not panel.validate_btn.isEnabled()
        assert not panel.clean_btn.isEnabled()

    def test_backup_no_database_does_nothing(self, qapp):
        panel = DatabasePanel()
        panel._on_backup_clicked()
        # Should not crash, should not create a worker
        assert panel._backup_worker is None


class TestBackupWorker:
    """Tests for BackupWorker."""

    def test_backup_worker_success(self, qapp):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            f.write(b"<VirtualDJ_Database></VirtualDJ_Database>")
            db_path = Path(f.name)

        try:
            with tempfile.TemporaryDirectory() as backup_dir:
                with patch("vdj_manager.core.backup.BACKUP_DIR", Path(backup_dir)):
                    worker = BackupWorker(db_path)
                    results = []
                    worker.finished_work.connect(lambda r: results.append(r))
                    worker.start()
                    worker.wait(5000)
                    QCoreApplication.processEvents()

                    assert len(results) == 1
                    assert Path(results[0]).exists()
                    assert Path(results[0]).suffix == ".xml"
        finally:
            db_path.unlink(missing_ok=True)

    def test_backup_worker_missing_file(self, qapp):
        worker = BackupWorker(Path("/nonexistent/database.xml"))
        errors = []
        worker.error.connect(lambda e: errors.append(e))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(errors) == 1
        assert "not found" in errors[0]


class TestDatabasePanelBackup:
    """Tests for backup operation in DatabasePanel."""

    def test_on_backup_finished(self, qapp):
        panel = DatabasePanel()
        panel._on_backup_finished(Path("/backups/database_local_20260101_120000.xml"))

        assert panel.backup_btn.isEnabled()
        assert "Backup created" in panel.status_label.text()
        assert "database_local_20260101_120000.xml" in panel.status_label.text()

    def test_on_backup_error(self, qapp):
        panel = DatabasePanel()
        panel._on_backup_error("File not found")

        assert panel.backup_btn.isEnabled()
        assert "Backup failed" in panel.status_label.text()
        assert "File not found" in panel.status_label.text()


def _make_song(path: str, is_netsearch: bool = False) -> Song:
    """Helper to create a Song for testing."""
    return Song(file_path=path, tags=Tags(author="Artist", title="Title"))


class TestValidateWorker:
    """Tests for ValidateWorker."""

    def test_validate_worker_runs(self, qapp):
        tracks = [_make_song("/music/song.mp3")]
        worker = ValidateWorker(tracks)
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        report = results[0]
        assert "total" in report
        assert report["total"] == 1

    def test_validate_worker_counts_categories(self, qapp):
        tracks = [
            _make_song("/music/song.mp3"),
            _make_song("/music/video.mkv"),
        ]
        worker = ValidateWorker(tracks)
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        report = results[0]
        assert report["total"] == 2
        assert report["non_audio"] >= 1  # mkv is non-audio


class TestDatabasePanelValidate:
    """Tests for validation in DatabasePanel."""

    def test_on_validate_finished_shows_summary(self, qapp):
        panel = DatabasePanel()
        report = {
            "total": 100,
            "audio_valid": 90,
            "audio_missing": 5,
            "non_audio": 3,
            "windows_paths": 2,
            "netsearch": 0,
            "unknown": 0,
        }

        with patch.object(QMessageBox, "information"):
            panel._on_validate_finished(report)

        assert panel.validate_btn.isEnabled()
        assert "90 valid" in panel.status_label.text()
        assert "5 missing" in panel.status_label.text()

    def test_on_validate_finished_green_when_no_missing(self, qapp):
        panel = DatabasePanel()
        report = {
            "total": 100,
            "audio_valid": 100,
            "audio_missing": 0,
            "non_audio": 0,
            "windows_paths": 0,
            "netsearch": 0,
        }

        with patch.object(QMessageBox, "information"):
            panel._on_validate_finished(report)

        # Status should use the success color from the theme
        from vdj_manager.ui.theme import DARK_THEME

        assert DARK_THEME.status_success in panel.status_label.styleSheet()

    def test_on_validate_error(self, qapp):
        panel = DatabasePanel()
        panel._on_validate_error("Something went wrong")

        assert panel.validate_btn.isEnabled()
        assert "Validation failed" in panel.status_label.text()

    def test_validate_no_tracks_does_nothing(self, qapp):
        panel = DatabasePanel()
        panel._on_validate_clicked()
        assert panel._validate_worker is None


class TestDatabasePanelClean:
    """Tests for clean operation in DatabasePanel."""

    def test_clean_nothing_to_clean(self, qapp):
        panel = DatabasePanel()
        panel._database = MagicMock()
        panel._tracks = [_make_song("/existing/song.mp3")]

        with patch("vdj_manager.files.validator.FileValidator.categorize_entries") as mock_cat:
            mock_cat.return_value = {
                "non_audio": [],
                "audio_missing": [],
                "audio_exists": [_make_song("/existing/song.mp3")],
                "windows_paths": [],
                "netsearch": [],
                "unknown": [],
            }
            with patch.object(QMessageBox, "information") as mock_info:
                panel._on_clean_clicked()
                mock_info.assert_called_once()

    def test_on_clean_finished(self, qapp):
        panel = DatabasePanel()
        panel._database = MagicMock()
        panel._database.iter_songs.return_value = iter([])
        panel._database.get_stats.return_value = None

        panel._on_clean_finished(5)

        assert panel.clean_btn.isEnabled()
        assert "Cleaned 5" in panel.status_label.text()

    def test_on_clean_error(self, qapp):
        panel = DatabasePanel()
        panel._on_clean_error("Remove failed")

        assert panel.clean_btn.isEnabled()
        assert "Clean failed" in panel.status_label.text()


class TestDatabasePanelTagEditing:
    """Tests for tag editing in DatabasePanel."""

    def test_tag_edit_group_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.tag_energy_spin is not None
        assert panel.tag_key_combo is not None
        assert panel.tag_comment_input is not None
        assert panel.tag_save_btn is not None

    def test_tag_save_disabled_initially(self, qapp):
        panel = DatabasePanel()
        assert not panel.tag_save_btn.isEnabled()

    def test_populate_tag_fields(self, qapp):
        panel = DatabasePanel()
        track = Song(
            file_path="/music/test.mp3",
            tags=Tags(
                author="Artist", title="Title", grouping="7", key="Am", comment="Mood: happy"
            ),
        )
        panel._populate_tag_fields(track)

        assert panel.tag_energy_spin.value() == 7
        assert panel.tag_key_combo.currentText() == "Am"
        assert panel.tag_comment_input.text() == "Mood: happy"
        assert panel.tag_save_btn.isEnabled()
        assert "Artist - Title" in panel.tag_track_label.text()

    def test_populate_tag_fields_no_tags(self, qapp):
        panel = DatabasePanel()
        track = Song(file_path="/music/test.mp3", tags=Tags())
        panel._populate_tag_fields(track)

        assert panel.tag_energy_spin.value() == 0  # "None"
        assert panel.tag_key_combo.currentText() == ""
        assert panel.tag_comment_input.text() == ""

    def test_tag_save_updates_database(self, qapp):
        panel = DatabasePanel()
        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([])
        panel._database = mock_db

        track = Song(file_path="/music/test.mp3", tags=Tags())
        panel._populate_tag_fields(track)
        panel.tag_energy_spin.setValue(5)
        panel.tag_key_combo.setCurrentText("Cm")
        panel.tag_comment_input.setText("energetic")

        # Track save_requested signal emission instead of direct save
        save_signals = []
        panel.save_requested.connect(lambda: save_signals.append(True))

        panel._on_tag_save_clicked()

        mock_db.update_song_tags.assert_called_once_with(
            "/music/test.mp3",
            Grouping="5",
            Key="Cm",
            Comment="energetic",
        )
        assert len(save_signals) == 1
        assert "Tags saved" in panel.status_label.text()

    def test_tag_save_clears_energy(self, qapp):
        panel = DatabasePanel()
        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([])
        panel._database = mock_db

        track = Song(
            file_path="/music/test.mp3",
            tags=Tags(grouping="7"),
        )
        panel._populate_tag_fields(track)
        panel.tag_energy_spin.setValue(0)  # Clear energy

        panel._on_tag_save_clicked()

        call_kwargs = mock_db.update_song_tags.call_args
        assert call_kwargs[1]["Grouping"] is None

    def test_tag_save_no_database_does_nothing(self, qapp):
        panel = DatabasePanel()
        panel._on_tag_save_clicked()
        # Should not crash

    def test_tag_tabs_count(self, qapp):
        """Tag editor should have 3 tabs: Common, Extended, File Tags."""
        panel = DatabasePanel()
        assert panel.tag_tabs.count() == 3
        assert panel.tag_tabs.tabText(0) == "Common"
        assert panel.tag_tabs.tabText(1) == "Extended"
        assert panel.tag_tabs.tabText(2) == "File Tags"

    def test_common_tab_has_all_widgets(self, qapp):
        """Common tab should have title, artist, album, genre, year, bpm, key, energy, rating, comment."""
        panel = DatabasePanel()
        assert hasattr(panel, "tag_title_input")
        assert hasattr(panel, "tag_artist_input")
        assert hasattr(panel, "tag_album_input")
        assert hasattr(panel, "tag_genre_combo")
        assert hasattr(panel, "tag_year_spin")
        assert hasattr(panel, "tag_bpm_spin")
        assert hasattr(panel, "tag_key_combo")
        assert hasattr(panel, "tag_rating_spin")

    def test_extended_tab_has_all_widgets(self, qapp):
        """Extended tab should have mood, composer, remix, label, track_number, color, flag."""
        panel = DatabasePanel()
        assert hasattr(panel, "tag_mood_input")
        assert hasattr(panel, "tag_composer_input")
        assert hasattr(panel, "tag_remix_input")
        assert hasattr(panel, "tag_label_input")
        assert hasattr(panel, "tag_track_number_spin")
        assert hasattr(panel, "tag_color_input")
        assert hasattr(panel, "tag_flag_spin")

    def test_populate_all_fields(self, qapp):
        """_populate_tag_fields should fill all Common + Extended widgets."""
        panel = DatabasePanel()
        track = Song(
            file_path="/music/test.mp3",
            tags=Tags(
                title="My Track",
                author="DJ Test",
                album="Album",
                genre="House",
                year=2024,
                bpm=128.0,
                key="Am",
                grouping="7",
                rating=4,
                comment="Nice",
                user2="#happy #uplifting",
                composer="Comp",
                remix="Extended Mix",
                label="Records",
                track_number=5,
                color="0xFF0000",
                flag=1,
            ),
        )
        panel._populate_tag_fields(track)

        assert panel.tag_title_input.text() == "My Track"
        assert panel.tag_artist_input.text() == "DJ Test"
        assert panel.tag_album_input.text() == "Album"
        assert panel.tag_genre_combo.currentText() == "House"
        assert panel.tag_year_spin.value() == 2024
        assert panel.tag_bpm_spin.value() == 128.0
        assert panel.tag_key_combo.currentText() == "Am"
        assert panel.tag_energy_spin.value() == 7
        assert panel.tag_rating_spin.value() == 4
        assert panel.tag_comment_input.text() == "Nice"
        assert panel.tag_mood_input.text() == "#happy #uplifting"
        assert panel.tag_composer_input.text() == "Comp"
        assert panel.tag_remix_input.text() == "Extended Mix"
        assert panel.tag_label_input.text() == "Records"
        assert panel.tag_track_number_spin.value() == 5
        assert panel.tag_color_input.text() == "0xFF0000"
        assert panel.tag_flag_spin.value() == 1

    def test_key_combo_has_standard_keys(self, qapp):
        """Key combo should contain standard musical keys and Camelot notation."""
        panel = DatabasePanel()
        items = [panel.tag_key_combo.itemText(i) for i in range(panel.tag_key_combo.count())]
        assert "Am" in items
        assert "8A" in items
        assert "12B" in items

    def test_genre_combo_has_common_genres(self, qapp):
        """Genre combo should contain common DJ genres."""
        panel = DatabasePanel()
        items = [panel.tag_genre_combo.itemText(i) for i in range(panel.tag_genre_combo.count())]
        assert "House" in items
        assert "Techno" in items
        assert "Trance" in items

    def test_revert_button_restores_values(self, qapp):
        """Revert button should restore fields to the original track values."""
        panel = DatabasePanel()
        track = Song(
            file_path="/music/test.mp3",
            tags=Tags(title="Original", author="Artist", grouping="5"),
        )
        panel._populate_tag_fields(track)
        panel.tag_title_input.setText("Changed")
        panel.tag_energy_spin.setValue(9)

        panel._on_tag_revert_clicked()

        assert panel.tag_title_input.text() == "Original"
        assert panel.tag_energy_spin.value() == 5

    def test_tag_save_sends_correct_xml_aliases(self, qapp):
        """Tag save should send correct XML alias names to update_song_tags."""
        panel = DatabasePanel()
        mock_db = MagicMock()
        mock_db.iter_songs.return_value = iter([])
        panel._database = mock_db

        track = Song(file_path="/music/test.mp3", tags=Tags())
        panel._populate_tag_fields(track)
        panel.tag_title_input.setText("New Title")
        panel.tag_artist_input.setText("New Artist")
        panel.tag_mood_input.setText("#chill")

        panel._on_tag_save_clicked()

        kwargs = mock_db.update_song_tags.call_args[1]
        assert kwargs.get("Title") == "New Title"
        assert kwargs.get("Author") == "New Artist"
        assert kwargs.get("User2") == "#chill"


class TestDatabasePanelFileTags:
    """Tests for File Tags tab in DatabasePanel."""

    def test_file_tags_tab_exists(self, qapp):
        """File Tags tab should be the 3rd tab."""
        panel = DatabasePanel()
        assert panel.tag_tabs.tabText(2) == "File Tags"

    def test_file_tag_widgets_exist(self, qapp):
        """File Tags tab should have all field widgets."""
        panel = DatabasePanel()
        assert hasattr(panel, "file_tag_title")
        assert hasattr(panel, "file_tag_artist")
        assert hasattr(panel, "file_tag_album")
        assert hasattr(panel, "file_tag_genre")
        assert hasattr(panel, "file_tag_year")
        assert hasattr(panel, "file_tag_bpm")
        assert hasattr(panel, "file_tag_key")
        assert hasattr(panel, "file_tag_composer")
        assert hasattr(panel, "file_tag_comment")

    def test_file_tag_buttons_exist(self, qapp):
        """File Tags tab should have read/write/sync buttons."""
        panel = DatabasePanel()
        assert hasattr(panel, "file_tag_read_btn")
        assert hasattr(panel, "file_tag_save_btn")
        assert hasattr(panel, "file_tag_sync_vdj_btn")
        assert hasattr(panel, "file_tag_import_btn")

    def test_file_tag_buttons_disabled_for_windows_path(self, qapp):
        """File tag buttons should be disabled for Windows-path tracks."""
        panel = DatabasePanel()
        track = Song(
            file_path="D:\\Music\\song.mp3",
            tags=Tags(title="Song"),
        )
        panel._populate_tag_fields(track)

        assert not panel.file_tag_read_btn.isEnabled()
        assert not panel.file_tag_save_btn.isEnabled()
        assert not panel.file_tag_sync_vdj_btn.isEnabled()
        assert not panel.file_tag_import_btn.isEnabled()

    def test_file_tag_read_windows_path_shows_message(self, qapp):
        """Reading file tags from a Windows-path track shows info message."""
        panel = DatabasePanel()
        track = Song(
            file_path="D:\\Music\\song.mp3",
            tags=Tags(title="Song"),
        )
        panel._editing_track = track

        with patch.object(QMessageBox, "information") as mock_info:
            panel._on_file_tag_read()
            mock_info.assert_called_once()


class TestDatabasePanelOperationLog:
    """Tests for operation log."""

    def test_operation_log_exists(self, qapp):
        panel = DatabasePanel()
        assert panel.operation_log is not None

    def test_log_operation_adds_entry(self, qapp):
        panel = DatabasePanel()
        panel._log_operation("Test operation")
        assert panel.operation_log.count() == 1
        assert "Test operation" in panel.operation_log.item(0).text()

    def test_log_operation_prepends(self, qapp):
        panel = DatabasePanel()
        panel._log_operation("First")
        panel._log_operation("Second")
        assert panel.operation_log.count() == 2
        assert "Second" in panel.operation_log.item(0).text()
        assert "First" in panel.operation_log.item(1).text()

    def test_log_operation_max_20(self, qapp):
        panel = DatabasePanel()
        for i in range(25):
            panel._log_operation(f"Operation {i}")
        assert panel.operation_log.count() == 20

    def test_backup_logs_operation(self, qapp):
        panel = DatabasePanel()
        panel._on_backup_finished(Path("/backups/db_backup.xml"))
        assert panel.operation_log.count() == 1
        assert "Backup" in panel.operation_log.item(0).text()

    def test_clean_logs_operation(self, qapp):
        panel = DatabasePanel()
        panel._database = MagicMock()
        panel._database.iter_songs.return_value = iter([])
        panel._database.get_stats.return_value = None
        panel._on_clean_finished(5)
        assert panel.operation_log.count() == 1
        assert "Cleaned 5" in panel.operation_log.item(0).text()

    def test_validate_logs_operation(self, qapp):
        panel = DatabasePanel()
        report = {
            "total": 10,
            "audio_valid": 8,
            "audio_missing": 2,
            "non_audio": 0,
            "windows_paths": 0,
            "netsearch": 0,
        }
        with patch.object(QMessageBox, "information"):
            panel._on_validate_finished(report)
        assert panel.operation_log.count() == 1
        assert "Validation" in panel.operation_log.item(0).text()
