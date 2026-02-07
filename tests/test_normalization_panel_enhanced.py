"""Tests for NormalizationPanel enhancements: apply, CSV export, limit."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import QCoreApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.widgets.normalization_panel import NormalizationPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestNormalizationPanelEnhanced:
    """Tests for normalization panel enhanced features."""

    def test_apply_button_exists(self, qapp):
        panel = NormalizationPanel()
        assert panel.apply_btn is not None
        assert panel.apply_btn.text() == "Apply Normalization"

    def test_apply_button_disabled_initially(self, qapp):
        panel = NormalizationPanel()
        assert not panel.apply_btn.isEnabled()

    def test_export_csv_button_exists(self, qapp):
        panel = NormalizationPanel()
        assert panel.export_csv_btn is not None
        assert panel.export_csv_btn.text() == "Export CSV"

    def test_export_csv_disabled_initially(self, qapp):
        panel = NormalizationPanel()
        assert not panel.export_csv_btn.isEnabled()

    def test_limit_spinner_exists(self, qapp):
        panel = NormalizationPanel()
        assert panel.limit_spin is not None
        assert panel.limit_spin.value() == 0  # All
        assert panel.limit_spin.specialValueText() == "All"

    def test_destructive_checkbox_exists(self, qapp):
        panel = NormalizationPanel()
        assert panel.destructive_check is not None
        assert not panel.destructive_check.isChecked()

    def test_buttons_enabled_after_measurement(self, qapp):
        panel = NormalizationPanel()
        # Simulate adding results
        panel.results_table.add_result("/music/song.mp3", {
            "success": True,
            "current_lufs": -14.0,
            "gain_db": 0.5,
        })

        panel._on_measurement_finished(True, "Done")

        assert panel.apply_btn.isEnabled()
        assert panel.export_csv_btn.isEnabled()

    def test_apply_no_results_shows_info(self, qapp):
        panel = NormalizationPanel()
        with patch.object(QMessageBox, "information") as mock_info:
            panel._on_apply_clicked()
            mock_info.assert_called_once()

    def test_destructive_shows_warning(self, qapp):
        panel = NormalizationPanel()
        panel.destructive_check.setChecked(True)
        # Add a result so it doesn't short-circuit on empty results
        panel.results_table.add_result("/music/song.mp3", {
            "success": True, "current_lufs": -14.0, "gain_db": 0.5,
        })

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No) as mock_warn:
            panel._on_apply_clicked()
            mock_warn.assert_called_once()

    def test_limit_respected_in_paths(self, qapp):
        panel = NormalizationPanel()
        songs = [
            Song(file_path=f"/music/song{i}.mp3", tags=Tags())
            for i in range(10)
        ]
        panel._tracks = songs
        panel.limit_spin.setValue(3)

        paths = panel._get_audio_paths()
        assert len(paths) == 3

    def test_limit_zero_means_all(self, qapp):
        panel = NormalizationPanel()
        songs = [
            Song(file_path=f"/music/song{i}.mp3", tags=Tags())
            for i in range(5)
        ]
        panel._tracks = songs
        panel.limit_spin.setValue(0)

        paths = panel._get_audio_paths()
        assert len(paths) == 5

    def test_export_csv_writes_file(self, qapp):
        panel = NormalizationPanel()
        panel.results_table.add_result("/music/song.mp3", {
            "success": True,
            "current_lufs": -14.0,
            "gain_db": 0.5,
        })

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = f.name

        with patch.object(QFileDialog, "getSaveFileName", return_value=(csv_path, "")):
            with patch.object(QMessageBox, "information"):
                panel._on_export_csv()

        # File should have been written
        content = Path(csv_path).read_text()
        assert "song.mp3" in content
        Path(csv_path).unlink()

    def test_on_apply_finished_re_enables_buttons(self, qapp):
        panel = NormalizationPanel()
        panel.results_table.add_result("/music/song.mp3", {
            "success": True, "current_lufs": -14.0, "gain_db": 0.5,
        })

        panel._on_apply_finished(True, "Done")

        assert panel.start_btn.isEnabled()
        assert panel.apply_btn.isEnabled()

    def test_is_running_checks_both_workers(self, qapp):
        panel = NormalizationPanel()
        assert not panel.is_running()

        # Mock running worker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        panel._worker = mock_worker
        assert panel.is_running()

        panel._worker = None
        panel._apply_worker = mock_worker
        assert panel.is_running()
