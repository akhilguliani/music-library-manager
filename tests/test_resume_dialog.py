"""Tests for resume dialog."""

import pytest
from datetime import datetime

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
from vdj_manager.ui.widgets.resume_dialog import ResumeDialog


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
def sample_tasks():
    """Create sample incomplete tasks."""
    return [
        TaskState(
            task_id="task_001",
            task_type=TaskType.NORMALIZE,
            status=TaskStatus.PAUSED,
            total_items=100,
            completed_paths=[f"/path/to/file{i}.mp3" for i in range(50)],
            pending_paths=[f"/path/to/file{i}.mp3" for i in range(50, 100)],
            created_at=datetime(2024, 1, 15, 10, 30),
            updated_at=datetime(2024, 1, 15, 11, 45),
        ),
        TaskState(
            task_id="task_002",
            task_type=TaskType.MEASURE,
            status=TaskStatus.RUNNING,  # Interrupted
            total_items=50,
            completed_paths=[f"/path/to/file{i}.mp3" for i in range(20)],
            pending_paths=[f"/path/to/file{i}.mp3" for i in range(20, 50)],
            failed_paths={"/path/to/bad.mp3": "File not found"},
            created_at=datetime(2024, 1, 14, 9, 0),
            updated_at=datetime(2024, 1, 14, 9, 30),
        ),
    ]


class TestResumeDialog:
    """Tests for ResumeDialog."""

    def test_dialog_creation(self, app, sample_tasks):
        """Test dialog can be created."""
        dialog = ResumeDialog(sample_tasks)
        assert dialog is not None

    def test_dialog_title(self, app, sample_tasks):
        """Test dialog title."""
        dialog = ResumeDialog(sample_tasks)
        assert "Resume" in dialog.windowTitle()

    def test_task_list_populated(self, app, sample_tasks):
        """Test task list is populated."""
        dialog = ResumeDialog(sample_tasks)
        assert dialog.task_list.count() == 2

    def test_first_task_selected(self, app, sample_tasks):
        """Test first task is selected by default."""
        dialog = ResumeDialog(sample_tasks)
        assert dialog.task_list.currentRow() == 0
        assert dialog.selected_task is not None

    def test_resume_button_enabled_for_resumable(self, app, sample_tasks):
        """Test resume button enabled for resumable task."""
        dialog = ResumeDialog(sample_tasks)

        # First task is paused with pending items - should be resumable
        dialog.task_list.setCurrentRow(0)
        assert dialog.resume_btn.isEnabled()

    def test_resume_button_enabled_for_interrupted(self, app, sample_tasks):
        """Test resume button enabled for interrupted (running) task."""
        dialog = ResumeDialog(sample_tasks)

        # Second task is "running" (interrupted) with pending items
        dialog.task_list.setCurrentRow(1)
        assert dialog.resume_btn.isEnabled()

    def test_discard_button_enabled_when_selected(self, app, sample_tasks):
        """Test discard button enabled when task selected."""
        dialog = ResumeDialog(sample_tasks)

        dialog.task_list.setCurrentRow(0)
        assert dialog.discard_btn.isEnabled()

    def test_details_updated_on_selection(self, app, sample_tasks):
        """Test details are updated when selection changes."""
        dialog = ResumeDialog(sample_tasks)

        dialog.task_list.setCurrentRow(0)

        assert "Normalize" in dialog.type_label.text()
        assert "Paused" in dialog.status_label.text()
        assert "50" in dialog.progress_label.text()

        dialog.task_list.setCurrentRow(1)

        assert "Measure" in dialog.type_label.text()
        assert "Interrupt" in dialog.status_label.text()

    def test_progress_shows_failures(self, app, sample_tasks):
        """Test progress shows failure count."""
        dialog = ResumeDialog(sample_tasks)

        # Second task has 1 failure
        dialog.task_list.setCurrentRow(1)
        assert "1 failed" in dialog.progress_label.text()

    def test_resume_action(self, app, sample_tasks):
        """Test resume action is set correctly."""
        dialog = ResumeDialog(sample_tasks)

        dialog.task_list.setCurrentRow(0)
        dialog._on_resume()

        assert dialog.action == "resume"
        assert dialog.selected_task == sample_tasks[0]

    def test_discard_action(self, app, sample_tasks):
        """Test discard action is set correctly."""
        dialog = ResumeDialog(sample_tasks)

        dialog.task_list.setCurrentRow(0)
        dialog._on_discard()

        assert dialog.action == "discard"
        assert dialog.selected_task == sample_tasks[0]

    def test_discard_all_action(self, app, sample_tasks):
        """Test discard all action is set correctly."""
        dialog = ResumeDialog(sample_tasks)

        dialog._on_discard_all()

        assert dialog.action == "discard_all"

    def test_later_action(self, app, sample_tasks):
        """Test later action is set correctly."""
        dialog = ResumeDialog(sample_tasks)

        dialog._on_later()

        assert dialog.action == "later"

    def test_empty_task_list(self, app):
        """Test dialog with no tasks."""
        dialog = ResumeDialog([])

        assert dialog.task_list.count() == 0
        assert dialog.selected_task is None
        assert not dialog.resume_btn.isEnabled()
        assert not dialog.discard_btn.isEnabled()

    def test_completed_task_not_resumable(self, app):
        """Test completed task is not resumable."""
        task = TaskState(
            task_id="completed_task",
            task_type=TaskType.NORMALIZE,
            status=TaskStatus.COMPLETED,
            total_items=10,
            completed_paths=[f"/path/to/file{i}.mp3" for i in range(10)],
            pending_paths=[],
        )

        dialog = ResumeDialog([task])

        assert not dialog.resume_btn.isEnabled()

    def test_details_cleared_on_no_selection(self, app, sample_tasks):
        """Test details are cleared when nothing selected."""
        dialog = ResumeDialog(sample_tasks)

        # Simulate clearing selection
        dialog._on_selection_changed(-1)

        assert dialog.type_label.text() == "-"
        assert dialog.status_label.text() == "-"
        assert dialog.progress_label.text() == "-"


class TestCheckAndShowResumeDialog:
    """Tests for check_and_show_resume_dialog function."""

    def test_returns_none_when_no_incomplete(self, app):
        """Test returns 'none' when no incomplete tasks."""
        from unittest.mock import MagicMock
        from vdj_manager.ui.widgets.resume_dialog import check_and_show_resume_dialog

        mock_manager = MagicMock()
        mock_manager.list_incomplete.return_value = []

        action, task = check_and_show_resume_dialog(mock_manager)

        assert action == "none"
        assert task is None
