"""Workflow dashboard panel for launching parallel analysis operations."""

from __future__ import annotations

import logging
import multiprocessing
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot

if TYPE_CHECKING:
    from vdj_manager.ui.workers.normalization_worker import NormalizationWorker

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.analysis.analysis_cache import DEFAULT_ANALYSIS_CACHE_PATH
from vdj_manager.config import AUDIO_EXTENSIONS, get_lastfm_api_key
from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.ui.widgets.progress_widget import ProgressWidget
from vdj_manager.ui.widgets.results_table import ConfigurableResultsTable
from vdj_manager.ui.workers.analysis_workers import EnergyWorker, MoodWorker

logger = logging.getLogger(__name__)


class WorkflowPanel(QWidget):
    """Unified launcher for parallel energy, mood, and normalization workflows.

    Allows the user to configure and launch multiple analysis operations
    simultaneously, with per-operation progress tracking.

    Signals:
        database_changed: Emitted when database has been modified.
    """

    database_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._database: VDJDatabase | None = None
        self._tracks: list[Song] = []
        self._energy_worker: EnergyWorker | None = None
        self._mood_worker: MoodWorker | None = None
        self._norm_worker: NormalizationWorker | None = None
        self._unsaved_count: int = 0
        self._workers_running: int = 0

        # Per-operation result counters
        self._energy_counts = {"analyzed": 0, "cached": 0, "failed": 0}
        self._mood_counts = {"analyzed": 0, "cached": 0, "failed": 0}
        self._norm_counts = {"measured": 0, "failed": 0}

        self._setup_ui()

    def set_database(self, database: VDJDatabase | None, tracks: list[Song] | None = None) -> None:
        """Set the database and tracks for workflow operations."""
        self._database = database
        if tracks is not None:
            self._tracks = tracks
        elif database is not None:
            self._tracks = list(database.iter_songs())
        else:
            self._tracks = []

        has_db = database is not None and len(self._tracks) > 0
        self.run_btn.setEnabled(has_db)
        self._update_info()

    def _setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)

        # Scroll area to handle tall content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # Config section
        config_group = QGroupBox("Workflow Configuration")
        config_layout = QVBoxLayout(config_group)

        # Energy row
        energy_row = QHBoxLayout()
        self.energy_check = QCheckBox("Energy Analysis")
        self.energy_check.setChecked(True)
        energy_row.addWidget(self.energy_check)
        energy_row.addWidget(QLabel("Workers:"))
        cpu_count = multiprocessing.cpu_count()
        self.energy_workers_spin = QSpinBox()
        self.energy_workers_spin.setRange(1, 20)
        self.energy_workers_spin.setValue(max(1, cpu_count - 1))
        energy_row.addWidget(self.energy_workers_spin)
        energy_row.addStretch()
        config_layout.addLayout(energy_row)

        # Mood row
        mood_row = QHBoxLayout()
        self.mood_check = QCheckBox("Mood Analysis")
        self.mood_check.setChecked(True)
        mood_row.addWidget(self.mood_check)
        mood_row.addWidget(QLabel("Model:"))
        self.mood_model_combo = QComboBox()
        self.mood_model_combo.addItem("MTG-Jamendo", "mtg-jamendo")
        self.mood_model_combo.addItem("Heuristic", "heuristic")
        mood_row.addWidget(self.mood_model_combo)
        mood_row.addWidget(QLabel("Workers:"))
        self.mood_workers_spin = QSpinBox()
        self.mood_workers_spin.setRange(1, 20)
        self.mood_workers_spin.setValue(max(1, cpu_count - 1))
        mood_row.addWidget(self.mood_workers_spin)
        mood_row.addStretch()
        config_layout.addLayout(mood_row)

        # Mood online sub-option
        mood_online_row = QHBoxLayout()
        mood_online_row.addSpacing(24)
        self.mood_online_check = QCheckBox("Online lookup (Last.fm / MusicBrainz)")
        self.mood_online_check.setChecked(True)
        mood_online_row.addWidget(self.mood_online_check)

        self.mood_threshold_spin = QDoubleSpinBox()
        self.mood_threshold_spin.setRange(0.01, 0.50)
        self.mood_threshold_spin.setSingleStep(0.01)
        self.mood_threshold_spin.setValue(0.10)
        self.mood_threshold_spin.setPrefix("Threshold: ")
        mood_online_row.addWidget(self.mood_threshold_spin)

        self.mood_max_tags_spin = QSpinBox()
        self.mood_max_tags_spin.setRange(1, 10)
        self.mood_max_tags_spin.setValue(5)
        self.mood_max_tags_spin.setPrefix("Max tags: ")
        mood_online_row.addWidget(self.mood_max_tags_spin)

        mood_online_row.addStretch()
        config_layout.addLayout(mood_online_row)

        # Normalization row
        norm_row = QHBoxLayout()
        self.norm_check = QCheckBox("Normalization (Measure)")
        self.norm_check.setChecked(False)
        norm_row.addWidget(self.norm_check)
        norm_row.addWidget(QLabel("Target LUFS:"))
        self.norm_lufs_spin = QDoubleSpinBox()
        self.norm_lufs_spin.setRange(-30.0, 0.0)
        self.norm_lufs_spin.setSingleStep(0.5)
        self.norm_lufs_spin.setValue(-14.0)
        norm_row.addWidget(self.norm_lufs_spin)
        norm_row.addWidget(QLabel("Workers:"))
        self.norm_workers_spin = QSpinBox()
        self.norm_workers_spin.setRange(1, 20)
        self.norm_workers_spin.setValue(max(1, cpu_count - 1))
        norm_row.addWidget(self.norm_workers_spin)
        norm_row.addStretch()
        config_layout.addLayout(norm_row)

        layout.addWidget(config_group)

        # Info label
        self.info_label = QLabel("No database loaded")
        self.info_label.setStyleSheet("color: gray; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(self.info_label)

        # Action buttons
        action_row = QHBoxLayout()
        self.run_btn = QPushButton("Run Selected")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._on_run_clicked)
        action_row.addWidget(self.run_btn)

        self.cancel_btn = QPushButton("Cancel All")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_all_clicked)
        action_row.addWidget(self.cancel_btn)

        action_row.addStretch()

        self.status_label = QLabel("")
        action_row.addWidget(self.status_label)

        layout.addLayout(action_row)

        # --- Energy progress + current file + results table ---
        self.energy_progress = ProgressWidget()
        self.energy_progress.setVisible(False)
        layout.addWidget(self.energy_progress)

        self.energy_current_file = QLabel("")
        self.energy_current_file.setStyleSheet("color: #555; font-size: 11px; padding-left: 4px;")
        self.energy_current_file.setVisible(False)
        layout.addWidget(self.energy_current_file)

        self.energy_results_table = ConfigurableResultsTable(
            columns=[
                {"name": "Track", "key": "file_path"},
                {"name": "Fmt", "key": "format", "width": 50},
                {"name": "Energy", "key": "energy", "width": 60},
                {"name": "Status", "key": "status", "width": 80},
            ]
        )
        self.energy_results_table.setMaximumHeight(200)
        self.energy_results_table.setVisible(False)
        layout.addWidget(self.energy_results_table)

        # --- Mood progress + current file + results table ---
        self.mood_progress = ProgressWidget()
        self.mood_progress.setVisible(False)
        layout.addWidget(self.mood_progress)

        self.mood_current_file = QLabel("")
        self.mood_current_file.setStyleSheet("color: #555; font-size: 11px; padding-left: 4px;")
        self.mood_current_file.setVisible(False)
        layout.addWidget(self.mood_current_file)

        self.mood_results_table = ConfigurableResultsTable(
            columns=[
                {"name": "Track", "key": "file_path"},
                {"name": "Fmt", "key": "format", "width": 50},
                {"name": "Mood", "key": "mood", "width": 150},
                {"name": "Status", "key": "status", "width": 80},
            ]
        )
        self.mood_results_table.setMaximumHeight(200)
        self.mood_results_table.setVisible(False)
        layout.addWidget(self.mood_results_table)

        # --- Norm progress + current file + results table ---
        self.norm_progress = ProgressWidget()
        self.norm_progress.setVisible(False)
        layout.addWidget(self.norm_progress)

        self.norm_current_file = QLabel("")
        self.norm_current_file.setStyleSheet("color: #555; font-size: 11px; padding-left: 4px;")
        self.norm_current_file.setVisible(False)
        layout.addWidget(self.norm_current_file)

        self.norm_results_table = ConfigurableResultsTable(
            columns=[
                {"name": "Track", "key": "file_path"},
                {"name": "LUFS", "key": "current_lufs", "width": 70},
                {"name": "Gain dB", "key": "gain_db", "width": 70},
                {"name": "Status", "key": "status", "width": 80},
            ]
        )
        self.norm_results_table.setMaximumHeight(200)
        self.norm_results_table.setVisible(False)
        layout.addWidget(self.norm_results_table)

        layout.addStretch()

        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll)

    def _update_info(self) -> None:
        """Update the info label with track counts."""
        if not self._tracks:
            self.info_label.setText("No database loaded")
            return

        audio = self._get_audio_tracks()
        local = [t for t in audio if not t.is_windows_path]
        remote = [t for t in audio if t.is_windows_path]
        untagged = [t for t in audio if t.energy is None]

        if remote:
            self.info_label.setText(
                f"{len(audio)} audio tracks ({len(local)} local, {len(remote)} remote), "
                f"{len(untagged)} without energy"
            )
        else:
            self.info_label.setText(f"{len(audio)} audio tracks, {len(untagged)} without energy")

    def _get_audio_tracks(self) -> list[Song]:
        """Get audio tracks eligible for analysis."""
        tracks = []
        for track in self._tracks:
            if track.is_netsearch:
                continue
            if track.extension not in AUDIO_EXTENSIONS:
                continue
            if not track.is_windows_path and not Path(track.file_path).exists():
                continue
            tracks.append(track)
        return tracks

    def _get_mood_tracks(self) -> list[Song]:
        """Get tracks eligible for mood analysis (includes Windows-path when online enabled)."""
        tracks = []
        for track in self._tracks:
            if track.is_netsearch:
                continue
            if track.extension not in AUDIO_EXTENSIONS:
                continue
            file_exists = not track.is_windows_path and Path(track.file_path).exists()
            has_metadata = track.tags and (track.tags.author or track.tags.title)
            if not file_exists and not has_metadata and not track.is_windows_path:
                continue
            tracks.append(track)
        return tracks

    def _on_run_clicked(self) -> None:
        """Launch selected operations in parallel."""
        if self._database is None:
            return

        checked = []
        if self.energy_check.isChecked():
            checked.append("energy")
        if self.mood_check.isChecked():
            checked.append("mood")
        if self.norm_check.isChecked():
            checked.append("norm")

        if not checked:
            QMessageBox.warning(self, "No Operations", "Select at least one operation to run.")
            return

        # Auto-backup ONCE
        try:
            from vdj_manager.core.backup import BackupManager

            BackupManager().create_backup(self._database.db_path, label="pre_workflow")
        except Exception:
            logger.warning("Auto-backup failed before workflow", exc_info=True)

        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._workers_running = 0

        if "energy" in checked:
            self._start_energy()

        if "mood" in checked:
            self._start_mood()

        if "norm" in checked:
            self._start_norm()

        # If no workers actually started (e.g. all checked ops have 0 eligible tracks),
        # reset UI immediately instead of leaving it stuck.
        if self._workers_running == 0:
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("No eligible tracks for selected operations")
            return

        self.status_label.setText(f"Running {self._workers_running} operation(s)...")

    def _start_energy(self) -> None:
        """Start energy analysis worker."""
        tracks = self._get_audio_tracks()
        if not tracks:
            return

        self._workers_running += 1
        self._energy_counts = {"analyzed": 0, "cached": 0, "failed": 0}
        self._energy_worker = EnergyWorker(
            tracks,
            max_workers=self.energy_workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
        )
        self._energy_worker.result_ready.connect(self._apply_result_to_db)
        self._energy_worker.result_ready.connect(self._on_energy_result)
        self._energy_worker.finished_work.connect(self._on_energy_finished)
        self._energy_worker.error.connect(lambda e: self.status_label.setText(f"Energy error: {e}"))

        self.energy_progress.reset()
        self.energy_progress.start(len(tracks))
        self.energy_progress.setVisible(True)
        self.energy_current_file.setText("")
        self.energy_current_file.setVisible(True)
        self.energy_results_table.clear()
        self.energy_results_table.setVisible(True)
        self._energy_worker.progress.connect(self.energy_progress.update_progress)
        self._energy_worker.status_changed.connect(self.energy_progress.on_status_changed)
        self.energy_progress.pause_requested.connect(self._energy_worker.pause)
        self.energy_progress.resume_requested.connect(self._energy_worker.resume)
        self.energy_progress.cancel_requested.connect(self._energy_worker.cancel)

        self._energy_worker.start()

    def _start_mood(self) -> None:
        """Start mood analysis worker."""
        tracks = self._get_mood_tracks()
        if not tracks:
            return

        enable_online = self.mood_online_check.isChecked()
        lastfm_api_key = get_lastfm_api_key() if enable_online else None

        self._workers_running += 1
        self._mood_counts = {"analyzed": 0, "cached": 0, "failed": 0}
        self._mood_worker = MoodWorker(
            tracks,
            max_workers=self.mood_workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
            enable_online=enable_online,
            lastfm_api_key=lastfm_api_key,
            model_name=self.mood_model_combo.currentData(),
            threshold=self.mood_threshold_spin.value(),
            max_tags=self.mood_max_tags_spin.value(),
        )
        self._mood_worker.result_ready.connect(self._apply_result_to_db)
        self._mood_worker.result_ready.connect(self._on_mood_result)
        self._mood_worker.finished_work.connect(self._on_mood_finished)
        self._mood_worker.error.connect(lambda e: self.status_label.setText(f"Mood error: {e}"))

        self.mood_progress.reset()
        self.mood_progress.start(len(tracks))
        self.mood_progress.setVisible(True)
        self.mood_current_file.setText("")
        self.mood_current_file.setVisible(True)
        self.mood_results_table.clear()
        self.mood_results_table.setVisible(True)
        self._mood_worker.progress.connect(self.mood_progress.update_progress)
        self._mood_worker.status_changed.connect(self.mood_progress.on_status_changed)
        self.mood_progress.pause_requested.connect(self._mood_worker.pause)
        self.mood_progress.resume_requested.connect(self._mood_worker.resume)
        self.mood_progress.cancel_requested.connect(self._mood_worker.cancel)

        self._mood_worker.start()

    def _start_norm(self) -> None:
        """Start normalization measurement worker."""
        tracks = self._get_audio_tracks()
        # Only local tracks (normalization needs the actual file)
        local_tracks = [t for t in tracks if not t.is_windows_path]
        if not local_tracks:
            return

        from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
        from vdj_manager.ui.workers.normalization_worker import NormalizationWorker

        file_paths = [t.file_path for t in local_tracks]
        task_state = TaskState(
            task_id="workflow_norm",
            task_type=TaskType.NORMALIZE,
            status=TaskStatus.RUNNING,
            total_items=len(file_paths),
            pending_paths=list(file_paths),
        )

        self._workers_running += 1
        self._norm_counts = {"measured": 0, "failed": 0}
        self._norm_worker = NormalizationWorker(
            task_state,
            target_lufs=self.norm_lufs_spin.value(),
            max_workers=self.norm_workers_spin.value(),
        )
        self._norm_worker.result_ready.connect(self._on_norm_result)
        self._norm_worker.finished_work.connect(self._on_norm_finished)
        self._norm_worker.error.connect(
            lambda e: self.status_label.setText(f"Normalization error: {e}")
        )

        self.norm_progress.reset()
        self.norm_progress.start(len(file_paths))
        self.norm_progress.setVisible(True)
        self.norm_current_file.setText("")
        self.norm_current_file.setVisible(True)
        self.norm_results_table.clear()
        self.norm_results_table.setVisible(True)
        self._norm_worker.progress.connect(self.norm_progress.update_progress)
        self._norm_worker.status_changed.connect(self.norm_progress.on_status_changed)
        self.norm_progress.pause_requested.connect(self._norm_worker.pause)
        self.norm_progress.resume_requested.connect(self._norm_worker.resume)
        self.norm_progress.cancel_requested.connect(self._norm_worker.cancel)

        self._norm_worker.start()

    @Slot(dict)
    def _apply_result_to_db(self, result: dict) -> None:
        """Apply tag updates from a worker result to the database."""
        tag_updates = result.get("tag_updates")
        if not tag_updates or self._database is None:
            return
        self._database.update_song_tags(result["file_path"], **tag_updates)
        self._unsaved_count += 1

    @Slot(dict)
    def _on_energy_result(self, result: dict) -> None:
        """Handle a single energy analysis result for UI display."""
        file_path = result.get("file_path", "")
        filename = Path(file_path).name if file_path else ""
        self.energy_current_file.setText(f"Processing: {filename}")

        status = result.get("status", "ok")
        if status == "cached":
            self._energy_counts["cached"] += 1
        elif status in ("failed", "error"):
            self._energy_counts["failed"] += 1
        else:
            self._energy_counts["analyzed"] += 1

        self.energy_results_table.add_result(result)

    @Slot(dict)
    def _on_mood_result(self, result: dict) -> None:
        """Handle a single mood analysis result for UI display."""
        file_path = result.get("file_path", "")
        filename = Path(file_path).name if file_path else ""
        self.mood_current_file.setText(f"Processing: {filename}")

        status = result.get("status", "ok")
        if status == "cached":
            self._mood_counts["cached"] += 1
        elif status in ("failed", "error"):
            self._mood_counts["failed"] += 1
        else:
            self._mood_counts["analyzed"] += 1

        self.mood_results_table.add_result(result)

    @Slot(str, dict)
    def _on_norm_result(self, file_path: str, result: dict) -> None:
        """Handle a single normalization result for UI display.

        NormalizationWorker emits result_ready(str, dict) — different from
        analysis workers which emit result_ready(dict).
        """
        filename = Path(file_path).name if file_path else ""
        self.norm_current_file.setText(f"Measuring: {filename}")

        # Inject file_path into result dict for ConfigurableResultsTable
        result["file_path"] = file_path
        success = result.get("success", True)
        if success:
            self._norm_counts["measured"] += 1
            result.setdefault("status", "ok")
        else:
            self._norm_counts["failed"] += 1
            result.setdefault("status", result.get("error", "failed"))

        # Format numeric values for display
        lufs = result.get("current_lufs")
        if lufs is not None:
            result["current_lufs"] = f"{lufs:.1f}"
        gain = result.get("gain_db")
        if gain is not None:
            result["gain_db"] = f"{gain:+.1f}"

        self.norm_results_table.add_result(result)

    def _on_energy_finished(self, result: dict) -> None:
        """Handle energy worker completion."""
        failed = result.get("failed", 0) if isinstance(result, dict) else 0
        c = self._energy_counts
        summary = f"Energy: {c['analyzed']} analyzed, {c['cached']} cached, {c['failed']} failed"
        self.energy_current_file.setText(summary)
        if failed > 0:
            self.energy_progress.on_finished(False, f"Energy: {failed} failed")
        else:
            self.energy_progress.on_finished(True, "Energy: Done")
        self._workers_running -= 1
        self._check_all_done()

    def _on_mood_finished(self, result: dict) -> None:
        """Handle mood worker completion."""
        failed = result.get("failed", 0) if isinstance(result, dict) else 0
        c = self._mood_counts
        summary = f"Mood: {c['analyzed']} analyzed, {c['cached']} cached, {c['failed']} failed"
        self.mood_current_file.setText(summary)
        if failed > 0:
            self.mood_progress.on_finished(False, f"Mood: {failed} failed")
        else:
            self.mood_progress.on_finished(True, "Mood: Done")
        self._workers_running -= 1
        self._check_all_done()

    def _on_norm_finished(self, success, message="") -> None:
        """Handle normalization worker completion."""
        c = self._norm_counts
        summary = f"Normalization: {c['measured']} measured, {c['failed']} failed"
        self.norm_current_file.setText(summary)
        if success:
            self.norm_progress.on_finished(True, "Normalization: Done")
        else:
            self.norm_progress.on_finished(False, f"Normalization: {message or 'Failed'}")
        self._workers_running -= 1
        self._check_all_done()

    def _check_all_done(self) -> None:
        """Save database when the last worker finishes."""
        if self._workers_running <= 0:
            self._workers_running = 0
            self._save_if_needed()
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("All operations complete")
            self.database_changed.emit()

    def _save_if_needed(self) -> None:
        """Save database if there are pending changes."""
        if self._unsaved_count > 0 and self._database is not None:
            try:
                self._database.save()
                self._unsaved_count = 0
            except Exception:
                logger.error("Failed to save database after workflow", exc_info=True)
                self.status_label.setText("Failed to save database!")

    def _on_cancel_all_clicked(self) -> None:
        """Cancel all running workers."""
        for worker in (self._energy_worker, self._mood_worker, self._norm_worker):
            if worker is not None and worker.isRunning():
                worker.cancel()
        self.status_label.setText("Cancelling...")
