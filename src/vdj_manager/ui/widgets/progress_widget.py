"""Progress widget with pause/resume/cancel controls."""

from typing import Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QGroupBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, Slot

from vdj_manager.ui.models.task_state import TaskStatus


class ProgressWidget(QWidget):
    """Widget showing progress with pause/resume/cancel controls.

    This widget provides:
    - Progress bar with percentage
    - Current operation status
    - Pause/Resume button
    - Cancel button
    - Real-time results log

    Signals:
        pause_requested: Emitted when pause button clicked
        resume_requested: Emitted when resume button clicked
        cancel_requested: Emitted when cancel button clicked
    """

    pause_requested = Signal()
    resume_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the progress widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._is_paused = False
        self._is_running = False

        self._setup_ui()
        self.reset()

    @property
    def is_paused(self) -> bool:
        """Check if currently paused."""
        return self._is_paused

    @property
    def is_running(self) -> bool:
        """Check if operation is running."""
        return self._is_running

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        # Status section
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.progress_label = QLabel("0 / 0")
        status_layout.addWidget(self.progress_label)

        layout.addLayout(status_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        # Control buttons
        button_layout = QHBoxLayout()

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        button_layout.addWidget(self.pause_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        button_layout.addWidget(self.cancel_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Results log
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)

        self.results_log = QTextEdit()
        self.results_log.setReadOnly(True)
        self.results_log.setMaximumHeight(150)
        self.results_log.setPlaceholderText("Results will appear here...")
        results_layout.addWidget(self.results_log)

        layout.addWidget(results_group)

    def reset(self) -> None:
        """Reset the widget to initial state."""
        self._is_paused = False
        self._is_running = False

        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("font-weight: bold; color: black;")
        self.progress_label.setText("0 / 0")
        self.progress_bar.setValue(0)
        self.pause_btn.setText("Pause")
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.results_log.clear()

    def start(self, total_items: int) -> None:
        """Start a new operation.

        Args:
            total_items: Total number of items to process.
        """
        self._is_running = True
        self._is_paused = False

        self.status_label.setText("Processing...")
        self.status_label.setStyleSheet("font-weight: bold; color: blue;")
        self.progress_label.setText(f"0 / {total_items}")
        self.progress_bar.setValue(0)
        self.pause_btn.setText("Pause")
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.results_log.clear()

    @Slot(int, int, float)
    def update_progress(self, current: int, total: int, percent: float) -> None:
        """Update progress display.

        Args:
            current: Number of items processed.
            total: Total number of items.
            percent: Progress percentage (0-100).
        """
        self.progress_label.setText(f"{current} / {total}")
        self.progress_bar.setValue(int(percent))

    @Slot(str, dict)
    def add_result(self, path: str, result: dict) -> None:
        """Add a result to the log.

        Args:
            path: File path that was processed.
            result: Result dictionary.
        """
        # Extract filename from path
        from pathlib import Path

        filename = Path(path).name

        if result.get("success", True):
            # Format successful result
            if "lufs" in result:
                lufs = result.get("lufs") or result.get("current_lufs")
                if lufs is not None:
                    text = f"[OK] {filename}: {lufs:.1f} LUFS"
                else:
                    text = f"[OK] {filename}"
            else:
                text = f"[OK] {filename}"
        else:
            error = result.get("error", "Unknown error")
            text = f"[FAIL] {filename}: {error}"

        self.results_log.append(text)

        # Auto-scroll to bottom
        scrollbar = self.results_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot(str)
    def set_status(self, status: str) -> None:
        """Set the status text.

        Args:
            status: Status message.
        """
        self.status_label.setText(status)

        # Update colors based on status
        if status.lower() in ("completed", "done", "finished"):
            self.status_label.setStyleSheet("font-weight: bold; color: green;")
        elif status.lower() in ("paused", "waiting"):
            self.status_label.setStyleSheet("font-weight: bold; color: orange;")
        elif status.lower() in ("cancelled", "failed", "error"):
            self.status_label.setStyleSheet("font-weight: bold; color: red;")
        else:
            self.status_label.setStyleSheet("font-weight: bold; color: blue;")

    @Slot(str)
    def on_status_changed(self, status_str: str) -> None:
        """Handle worker status change.

        Args:
            status_str: Status value from TaskStatus enum.
        """
        try:
            status = TaskStatus(status_str)
        except ValueError:
            return

        if status == TaskStatus.RUNNING:
            self._is_paused = False
            self.pause_btn.setText("Pause")
            self.pause_btn.setEnabled(True)
            self.set_status("Processing...")

        elif status == TaskStatus.PAUSED:
            self._is_paused = True
            self.pause_btn.setText("Resume")
            self.pause_btn.setEnabled(True)
            self.set_status("Paused")

        elif status == TaskStatus.COMPLETED:
            self._is_running = False
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            self.set_status("Completed")

        elif status == TaskStatus.CANCELLED:
            self._is_running = False
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            self.set_status("Cancelled")

        elif status == TaskStatus.FAILED:
            self._is_running = False
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            self.set_status("Failed")

    @Slot(bool, str)
    def on_finished(self, success: bool, message: str) -> None:
        """Handle operation completion.

        Args:
            success: Whether operation succeeded.
            message: Completion message.
        """
        self._is_running = False
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

        if success:
            self.status_label.setStyleSheet("font-weight: bold; color: green;")
        else:
            self.status_label.setStyleSheet("font-weight: bold; color: red;")

        self.status_label.setText(message)

    def _on_pause_clicked(self) -> None:
        """Handle pause/resume button click."""
        if self._is_paused:
            self._is_paused = False
            self.pause_btn.setText("Pause")
            self.resume_requested.emit()
        else:
            self._is_paused = True
            self.pause_btn.setText("Resume")
            self.pause_requested.emit()

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        self.cancel_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.set_status("Cancelling...")
        self.cancel_requested.emit()

    def connect_worker(self, worker: Any) -> None:
        """Connect this widget to a PausableWorker.

        This connects all the worker's signals to the appropriate slots.

        Args:
            worker: PausableWorker instance.
        """
        worker.progress.connect(self.update_progress)
        worker.result_ready.connect(self.add_result)
        worker.status_changed.connect(self.on_status_changed)
        worker.finished_work.connect(self.on_finished)

        self.pause_requested.connect(worker.pause)
        self.resume_requested.connect(worker.resume)
        self.cancel_requested.connect(worker.cancel)
