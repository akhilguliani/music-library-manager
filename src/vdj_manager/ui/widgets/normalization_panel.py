"""Normalization panel with workflow controls."""

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QSplitter,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from vdj_manager.config import DEFAULT_LUFS_TARGET, LOCAL_VDJ_DB, MYNVME_VDJ_DB
from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
from vdj_manager.ui.state.checkpoint_manager import CheckpointManager
from vdj_manager.ui.widgets.progress_widget import ProgressWidget
from vdj_manager.ui.widgets.results_table import ResultsTable
from vdj_manager.ui.workers.normalization_worker import NormalizationWorker


class NormalizationPanel(QWidget):
    """Panel for measuring and normalizing audio loudness.

    This panel provides:
    - Configuration for target LUFS and batch size
    - Start/Stop controls for measurement
    - Progress display with pause/resume
    - Results table showing LUFS values

    Signals:
        measurement_started: Emitted when measurement starts
        measurement_completed: Emitted when measurement completes (results)
    """

    measurement_started = Signal()
    measurement_completed = Signal(list)  # List of result dicts

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the normalization panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._database: VDJDatabase | None = None
        self._tracks: list[Song] = []
        self._worker: NormalizationWorker | None = None
        self._checkpoint_manager = CheckpointManager()
        self._task_state: TaskState | None = None

        self._setup_ui()

    @property
    def database(self) -> VDJDatabase | None:
        """Get the current database."""
        return self._database

    def set_database(self, database: VDJDatabase | None, tracks: list[Song] | None = None) -> None:
        """Set the database to use for normalization.

        Args:
            database: VDJDatabase instance.
            tracks: Optional list of tracks (if already loaded).
        """
        self._database = database
        if tracks is not None:
            self._tracks = tracks
        elif database is not None:
            self._tracks = list(database.iter_songs())
        else:
            self._tracks = []

        self._update_track_count()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)

        # Configuration section
        config_group = self._create_config_group()
        layout.addWidget(config_group)

        # Create splitter for progress and results
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        self.progress_widget = ProgressWidget()
        progress_layout.addWidget(self.progress_widget)
        splitter.addWidget(progress_group)

        # Results section
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)
        self.results_table = ResultsTable()
        results_layout.addWidget(self.results_table)
        splitter.addWidget(results_group)

        # Set stretch factors
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def _create_config_group(self) -> QGroupBox:
        """Create the configuration group box."""
        group = QGroupBox("Configuration")
        layout = QVBoxLayout(group)

        # Form layout for settings
        form_layout = QFormLayout()

        # Target LUFS
        self.lufs_spin = QDoubleSpinBox()
        self.lufs_spin.setRange(-30.0, 0.0)
        self.lufs_spin.setValue(DEFAULT_LUFS_TARGET)
        self.lufs_spin.setSuffix(" LUFS")
        self.lufs_spin.setDecimals(1)
        self.lufs_spin.setToolTip("Target integrated loudness (streaming standard: -14 LUFS)")
        form_layout.addRow("Target:", self.lufs_spin)

        # Batch size
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(10, 500)
        self.batch_spin.setValue(50)
        self.batch_spin.setToolTip("Files per batch (checkpoint frequency)")
        form_layout.addRow("Batch Size:", self.batch_spin)

        # Track count info
        self.track_count_label = QLabel("No database loaded")
        form_layout.addRow("Tracks:", self.track_count_label)

        layout.addLayout(form_layout)

        # Control buttons
        button_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Measurement")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start_clicked)
        button_layout.addWidget(self.start_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        return group

    def _update_track_count(self) -> None:
        """Update the track count label."""
        if not self._tracks:
            self.track_count_label.setText("No database loaded")
            self.start_btn.setEnabled(False)
        else:
            # Count audio files only
            audio_count = sum(
                1 for t in self._tracks
                if not t.is_netsearch and t.extension in {
                    ".mp3", ".m4a", ".aac", ".flac", ".wav",
                    ".aiff", ".aif", ".ogg", ".opus"
                }
            )
            self.track_count_label.setText(f"{audio_count} audio files")
            self.start_btn.setEnabled(audio_count > 0)

    def _get_audio_paths(self) -> list[str]:
        """Get list of audio file paths to process.

        Returns:
            List of file paths.
        """
        paths = []
        audio_extensions = {
            ".mp3", ".m4a", ".aac", ".flac", ".wav",
            ".aiff", ".aif", ".ogg", ".opus"
        }

        for track in self._tracks:
            if track.is_netsearch:
                continue
            if track.extension not in audio_extensions:
                continue
            # Skip Windows paths on macOS
            if track.is_windows_path:
                continue
            paths.append(track.file_path)

        return paths

    def _on_start_clicked(self) -> None:
        """Handle start button click."""
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(
                self,
                "Already Running",
                "A measurement is already in progress.",
            )
            return

        paths = self._get_audio_paths()
        if not paths:
            QMessageBox.information(
                self,
                "No Tracks",
                "No audio tracks available for measurement.",
            )
            return

        # Create task state
        self._task_state = self._checkpoint_manager.create_task(
            TaskType.MEASURE,
            paths,
            config={
                "target_lufs": self.lufs_spin.value(),
                "batch_size": self.batch_spin.value(),
            },
        )

        # Create worker
        self._worker = NormalizationWorker(
            self._task_state,
            target_lufs=self.lufs_spin.value(),
            checkpoint_manager=self._checkpoint_manager,
            batch_size=self.batch_spin.value(),
        )

        # Connect signals
        self.progress_widget.connect_worker(self._worker)
        self._worker.result_ready.connect(self.results_table.add_result)
        self._worker.finished_work.connect(self._on_measurement_finished)

        # Clear previous results
        self.results_table.clear()

        # Start
        self.progress_widget.start(len(paths))
        self.start_btn.setEnabled(False)
        self._worker.start()

        self.measurement_started.emit()

    @Slot(bool, str)
    def _on_measurement_finished(self, success: bool, message: str) -> None:
        """Handle measurement completion."""
        self.start_btn.setEnabled(True)

        # Collect results
        results = self.results_table.get_all_results()
        self.measurement_completed.emit(results)

        # Clean up completed checkpoint
        if self._task_state and self._task_state.status == TaskStatus.COMPLETED:
            self._checkpoint_manager.delete(self._task_state.task_id)

    def resume_task(self, task_state: TaskState) -> None:
        """Resume a paused or interrupted task.

        Args:
            task_state: TaskState to resume.
        """
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(
                self,
                "Already Running",
                "A measurement is already in progress.",
            )
            return

        self._task_state = task_state

        # Create worker with existing state
        self._worker = NormalizationWorker(
            task_state,
            target_lufs=task_state.config.get("target_lufs", DEFAULT_LUFS_TARGET),
            checkpoint_manager=self._checkpoint_manager,
            batch_size=task_state.config.get("batch_size", 50),
        )

        # Connect signals
        self.progress_widget.connect_worker(self._worker)
        self._worker.result_ready.connect(self.results_table.add_result)
        self._worker.finished_work.connect(self._on_measurement_finished)

        # Add existing results to table
        self.results_table.clear()
        for result in task_state.results:
            path = result.get("path", "")
            self.results_table.add_result(path, result)

        # Update progress to show existing progress
        self.progress_widget.start(task_state.total_items)
        self.progress_widget.update_progress(
            task_state.processed_count,
            task_state.total_items,
            task_state.progress_percent,
        )

        self.start_btn.setEnabled(False)
        self._worker.start()

        self.measurement_started.emit()

    def is_running(self) -> bool:
        """Check if a measurement is currently running.

        Returns:
            True if running.
        """
        return self._worker is not None and self._worker.isRunning()
