"""Dialog for resuming incomplete tasks."""

from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QFormLayout,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt

from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
from vdj_manager.ui.state.checkpoint_manager import CheckpointManager


class ResumeDialog(QDialog):
    """Dialog shown on startup when incomplete tasks exist.

    This dialog shows a list of incomplete/paused tasks and allows
    the user to:
    - Resume a selected task
    - Discard selected/all incomplete tasks
    - Dismiss and handle later
    """

    def __init__(
        self,
        incomplete_tasks: list[TaskState],
        parent: Any = None,
    ) -> None:
        """Initialize the resume dialog.

        Args:
            incomplete_tasks: List of incomplete TaskState objects.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._tasks = incomplete_tasks
        self._selected_task: TaskState | None = None
        self._action: str = "later"  # "resume", "discard", "discard_all", "later"

        self._setup_ui()
        self._populate_list()

    @property
    def selected_task(self) -> TaskState | None:
        """Get the selected task to resume."""
        return self._selected_task

    @property
    def action(self) -> str:
        """Get the action chosen by the user."""
        return self._action

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setWindowTitle("Resume Incomplete Tasks")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "The following tasks were interrupted or paused.\n"
            "Would you like to resume one of them?"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Task list
        self.task_list = QListWidget()
        self.task_list.setAlternatingRowColors(True)
        self.task_list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self.task_list)

        # Task details
        details_group = QGroupBox("Task Details")
        details_layout = QFormLayout(details_group)

        self.type_label = QLabel("-")
        details_layout.addRow("Type:", self.type_label)

        self.status_label = QLabel("-")
        details_layout.addRow("Status:", self.status_label)

        self.progress_label = QLabel("-")
        details_layout.addRow("Progress:", self.progress_label)

        self.created_label = QLabel("-")
        details_layout.addRow("Created:", self.created_label)

        layout.addWidget(details_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.resume_btn = QPushButton("Resume")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self._on_resume)
        button_layout.addWidget(self.resume_btn)

        self.discard_btn = QPushButton("Discard Selected")
        self.discard_btn.setEnabled(False)
        self.discard_btn.clicked.connect(self._on_discard)
        button_layout.addWidget(self.discard_btn)

        self.discard_all_btn = QPushButton("Discard All")
        self.discard_all_btn.clicked.connect(self._on_discard_all)
        button_layout.addWidget(self.discard_all_btn)

        button_layout.addStretch()

        self.later_btn = QPushButton("Later")
        self.later_btn.clicked.connect(self._on_later)
        button_layout.addWidget(self.later_btn)

        layout.addLayout(button_layout)

    def _populate_list(self) -> None:
        """Populate the task list."""
        self.task_list.clear()

        for task in self._tasks:
            # Format task type
            type_name = task.task_type.value.replace("_", " ").title()

            # Format progress
            progress = f"{task.processed_count}/{task.total_items}"

            # Format status
            status = task.status.value.title()

            text = f"{type_name} - {progress} ({status})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, task)
            self.task_list.addItem(item)

        # Select first item if any
        if self.task_list.count() > 0:
            self.task_list.setCurrentRow(0)

    def _on_selection_changed(self, row: int) -> None:
        """Handle selection change."""
        if row < 0:
            self._selected_task = None
            self.resume_btn.setEnabled(False)
            self.discard_btn.setEnabled(False)
            self._clear_details()
            return

        item = self.task_list.item(row)
        task = item.data(Qt.ItemDataRole.UserRole)
        self._selected_task = task

        self.resume_btn.setEnabled(task.is_resumable)
        self.discard_btn.setEnabled(True)

        self._update_details(task)

    def _update_details(self, task: TaskState) -> None:
        """Update the details display.

        Args:
            task: Selected TaskState.
        """
        # Type
        type_name = task.task_type.value.replace("_", " ").title()
        self.type_label.setText(type_name)

        # Status
        status_text = task.status.value.title()
        if task.status == TaskStatus.PAUSED:
            self.status_label.setStyleSheet("color: orange;")
        elif task.status == TaskStatus.RUNNING:
            self.status_label.setStyleSheet("color: blue;")
            status_text = "Interrupted"
        else:
            self.status_label.setStyleSheet("")

        self.status_label.setText(status_text)

        # Progress
        completed = len(task.completed_paths)
        failed = len(task.failed_paths)
        total = task.total_items
        progress_text = f"{task.processed_count} of {total} processed"
        if failed > 0:
            progress_text += f" ({failed} failed)"
        progress_text += f" - {task.progress_percent:.1f}%"
        self.progress_label.setText(progress_text)

        # Created
        created = task.created_at.strftime("%Y-%m-%d %H:%M")
        updated = task.updated_at.strftime("%Y-%m-%d %H:%M")
        self.created_label.setText(f"{created} (last: {updated})")

    def _clear_details(self) -> None:
        """Clear the details display."""
        self.type_label.setText("-")
        self.status_label.setText("-")
        self.status_label.setStyleSheet("")
        self.progress_label.setText("-")
        self.created_label.setText("-")

    def _on_resume(self) -> None:
        """Handle resume button click."""
        if self._selected_task:
            self._action = "resume"
            self.accept()

    def _on_discard(self) -> None:
        """Handle discard button click."""
        if self._selected_task:
            self._action = "discard"
            self.accept()

    def _on_discard_all(self) -> None:
        """Handle discard all button click."""
        self._action = "discard_all"
        self.accept()

    def _on_later(self) -> None:
        """Handle later button click."""
        self._action = "later"
        self.reject()


def check_and_show_resume_dialog(
    checkpoint_manager: CheckpointManager,
    parent: Any = None,
) -> tuple[str, TaskState | None]:
    """Check for incomplete tasks and show resume dialog if any exist.

    Args:
        checkpoint_manager: CheckpointManager to check.
        parent: Parent widget for dialog.

    Returns:
        Tuple of (action, selected_task).
        action is one of: "resume", "discard", "discard_all", "later", "none"
        selected_task is the task to resume (if action is "resume") or discard.
    """
    incomplete = checkpoint_manager.list_incomplete()

    if not incomplete:
        return ("none", None)

    dialog = ResumeDialog(incomplete, parent)
    result = dialog.exec()

    action = dialog.action
    selected_task = dialog.selected_task

    return (action, selected_task)
