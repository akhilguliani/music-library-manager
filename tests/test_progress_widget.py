"""Tests for progress widget."""

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from vdj_manager.ui.models.task_state import TaskStatus
from vdj_manager.ui.widgets.progress_widget import ProgressWidget


@pytest.fixture(scope="module")
def app():
    """Create a QApplication for testing."""
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        app = QApplication(["test"])
        yield app


@pytest.fixture
def progress_widget(app):
    """Create a ProgressWidget instance."""
    widget = ProgressWidget()
    yield widget


class TestProgressWidget:
    """Tests for ProgressWidget."""

    def test_widget_creation(self, progress_widget):
        """Test widget can be created."""
        assert progress_widget is not None
        assert progress_widget.progress_bar is not None
        assert progress_widget.pause_btn is not None
        assert progress_widget.cancel_btn is not None

    def test_initial_state(self, progress_widget):
        """Test initial widget state."""
        assert not progress_widget.is_running
        assert not progress_widget.is_paused
        assert not progress_widget.pause_btn.isEnabled()
        assert not progress_widget.cancel_btn.isEnabled()
        assert progress_widget.progress_bar.value() == 0

    def test_reset(self, progress_widget):
        """Test reset clears state."""
        # Modify state
        progress_widget.start(100)
        progress_widget.update_progress(50, 100, 50.0)

        # Reset
        progress_widget.reset()

        assert not progress_widget.is_running
        assert not progress_widget.is_paused
        assert progress_widget.progress_bar.value() == 0
        assert not progress_widget.pause_btn.isEnabled()
        assert not progress_widget.cancel_btn.isEnabled()

    def test_start(self, progress_widget):
        """Test starting an operation."""
        progress_widget.start(100)

        assert progress_widget.is_running
        assert not progress_widget.is_paused
        assert progress_widget.pause_btn.isEnabled()
        assert progress_widget.cancel_btn.isEnabled()
        assert progress_widget.pause_btn.text() == "Pause"

    def test_update_progress(self, progress_widget):
        """Test progress updates."""
        progress_widget.start(100)

        progress_widget.update_progress(25, 100, 25.0)
        assert progress_widget.progress_bar.value() == 25
        assert "25" in progress_widget.progress_label.text()
        assert "100" in progress_widget.progress_label.text()

        progress_widget.update_progress(75, 100, 75.0)
        assert progress_widget.progress_bar.value() == 75

    def test_add_result_success(self, progress_widget):
        """Test adding successful results."""
        progress_widget.start(10)

        progress_widget.add_result(
            "/path/to/track.mp3",
            {"success": True, "lufs": -14.0},
        )

        log_text = progress_widget.results_log.toPlainText()
        assert "[OK]" in log_text
        assert "track.mp3" in log_text
        assert "-14.0" in log_text

    def test_add_result_failure(self, progress_widget):
        """Test adding failed results."""
        progress_widget.start(10)

        progress_widget.add_result(
            "/path/to/failed.mp3",
            {"success": False, "error": "File not found"},
        )

        log_text = progress_widget.results_log.toPlainText()
        assert "[FAIL]" in log_text
        assert "failed.mp3" in log_text
        assert "File not found" in log_text

    def test_set_status(self, progress_widget):
        """Test setting status text."""
        progress_widget.set_status("Processing")
        assert progress_widget.status_label.text() == "Processing"

        progress_widget.set_status("Completed")
        assert progress_widget.status_label.text() == "Completed"

    def test_pause_button_toggles(self, progress_widget):
        """Test pause button toggles between pause/resume."""
        progress_widget.start(100)

        # Initially shows "Pause"
        assert progress_widget.pause_btn.text() == "Pause"

        # Click to pause
        progress_widget._on_pause_clicked()
        assert progress_widget.is_paused
        assert progress_widget.pause_btn.text() == "Resume"

        # Click to resume
        progress_widget._on_pause_clicked()
        assert not progress_widget.is_paused
        assert progress_widget.pause_btn.text() == "Pause"

    def test_pause_signal_emitted(self, progress_widget):
        """Test pause signal is emitted."""
        progress_widget.start(100)

        signals_received = []
        progress_widget.pause_requested.connect(lambda: signals_received.append("pause"))

        progress_widget._on_pause_clicked()
        assert "pause" in signals_received

    def test_resume_signal_emitted(self, progress_widget):
        """Test resume signal is emitted."""
        progress_widget.start(100)
        progress_widget._is_paused = True

        signals_received = []
        progress_widget.resume_requested.connect(lambda: signals_received.append("resume"))

        progress_widget._on_pause_clicked()
        assert "resume" in signals_received

    def test_cancel_signal_emitted(self, progress_widget):
        """Test cancel signal is emitted."""
        progress_widget.start(100)

        signals_received = []
        progress_widget.cancel_requested.connect(lambda: signals_received.append("cancel"))

        progress_widget._on_cancel_clicked()
        assert "cancel" in signals_received
        assert not progress_widget.cancel_btn.isEnabled()

    def test_on_status_changed_running(self, progress_widget):
        """Test status change to running."""
        progress_widget.start(100)
        progress_widget._is_paused = True

        progress_widget.on_status_changed(TaskStatus.RUNNING.value)

        assert not progress_widget.is_paused
        assert progress_widget.pause_btn.text() == "Pause"
        assert progress_widget.pause_btn.isEnabled()

    def test_on_status_changed_paused(self, progress_widget):
        """Test status change to paused."""
        progress_widget.start(100)

        progress_widget.on_status_changed(TaskStatus.PAUSED.value)

        assert progress_widget.is_paused
        assert progress_widget.pause_btn.text() == "Resume"
        assert "Paused" in progress_widget.status_label.text()

    def test_on_status_changed_completed(self, progress_widget):
        """Test status change to completed."""
        progress_widget.start(100)

        progress_widget.on_status_changed(TaskStatus.COMPLETED.value)

        assert not progress_widget.is_running
        assert not progress_widget.pause_btn.isEnabled()
        assert not progress_widget.cancel_btn.isEnabled()
        assert "Completed" in progress_widget.status_label.text()

    def test_on_status_changed_cancelled(self, progress_widget):
        """Test status change to cancelled."""
        progress_widget.start(100)

        progress_widget.on_status_changed(TaskStatus.CANCELLED.value)

        assert not progress_widget.is_running
        assert not progress_widget.pause_btn.isEnabled()
        assert not progress_widget.cancel_btn.isEnabled()
        assert "Cancelled" in progress_widget.status_label.text()

    def test_on_finished_success(self, progress_widget):
        """Test handling successful completion."""
        progress_widget.start(100)

        progress_widget.on_finished(True, "All done!")

        assert not progress_widget.is_running
        assert not progress_widget.pause_btn.isEnabled()
        assert not progress_widget.cancel_btn.isEnabled()
        assert "All done!" in progress_widget.status_label.text()

    def test_on_finished_failure(self, progress_widget):
        """Test handling failed completion."""
        progress_widget.start(100)

        progress_widget.on_finished(False, "Failed with errors")

        assert not progress_widget.is_running
        assert "Failed" in progress_widget.status_label.text()

    def test_multiple_results(self, progress_widget):
        """Test adding multiple results."""
        progress_widget.start(5)

        for i in range(5):
            progress_widget.add_result(
                f"/path/to/track{i}.mp3",
                {"success": True, "lufs": -14.0 + i},
            )

        log_text = progress_widget.results_log.toPlainText()
        assert log_text.count("[OK]") == 5
        assert "track0.mp3" in log_text
        assert "track4.mp3" in log_text

    def test_invalid_status_string(self, progress_widget):
        """Test handling invalid status string."""
        progress_widget.start(100)

        # Should not raise exception
        progress_widget.on_status_changed("invalid_status")

        # State should be unchanged
        assert progress_widget.pause_btn.isEnabled()
