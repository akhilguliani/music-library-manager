"""Normalization worker with checkpoint support."""

from typing import Any

from PySide6.QtCore import Signal

from vdj_manager.config import DEFAULT_LUFS_TARGET
from vdj_manager.normalize.processor import NormalizationProcessor, NormalizationResult
from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
from vdj_manager.ui.state.checkpoint_manager import CheckpointManager
from vdj_manager.ui.workers.base_worker import PausableWorker


class NormalizationWorker(PausableWorker):
    """Worker for measuring and normalizing audio loudness.

    This worker wraps the existing NormalizationProcessor and adds:
    - Pause/Resume capability via PausableWorker
    - Checkpoint persistence for task recovery
    - Qt signals for UI updates

    The worker processes files in batches, saving checkpoints after
    each batch to allow recovery after application restart.

    Signals (inherited from PausableWorker):
        progress: (current, total, percent)
        result_ready: (path, result_dict)
        batch_complete: (batch_num, total_batches)
        finished_work: (success, message)
        error: (error_message)
        status_changed: (new_status)

    Additional Signals:
        checkpoint_saved: Emitted after checkpoint is saved (task_id)
    """

    checkpoint_saved = Signal(str)  # task_id

    def __init__(
        self,
        task_state: TaskState,
        target_lufs: float = DEFAULT_LUFS_TARGET,
        checkpoint_manager: CheckpointManager | None = None,
        batch_size: int = 50,
        parent: Any = None,
    ) -> None:
        """Initialize the normalization worker.

        Args:
            task_state: TaskState with files to process.
            target_lufs: Target loudness in LUFS (default -14).
            checkpoint_manager: Manager for saving checkpoints.
            batch_size: Files per batch (checkpoint frequency).
            parent: Optional parent QObject.
        """
        super().__init__(task_state, batch_size=batch_size, parent=parent)

        self.target_lufs = target_lufs
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self._processor = NormalizationProcessor(
            target_lufs=target_lufs,
            max_workers=1,  # We process one at a time in the UI worker
        )

    def process_item(self, path: str) -> NormalizationResult:
        """Measure loudness for a single file.

        Args:
            path: Audio file path.

        Returns:
            NormalizationResult with measurement data.
        """
        # Use the processor's single-file measurement
        results = self._processor.measure_batch_parallel([path])
        if results:
            return results[0]

        # Fallback error
        return NormalizationResult(
            file_path=path,
            success=False,
            error="No result returned from processor",
        )

    def get_result_dict(
        self,
        path: str,
        result: NormalizationResult | None,
        error: str | None = None,
    ) -> dict:
        """Convert NormalizationResult to dictionary.

        Args:
            path: File path.
            result: NormalizationResult or None.
            error: Error message if failed.

        Returns:
            Dictionary with result data.
        """
        if error:
            return {
                "path": path,
                "success": False,
                "error": error,
            }

        if result is None:
            return {
                "path": path,
                "success": False,
                "error": "No result",
            }

        return {
            "path": result.file_path,
            "success": result.success,
            "current_lufs": result.current_lufs,
            "gain_db": result.gain_db,
            "error": result.error,
        }

    def run(self) -> None:
        """Main worker execution with checkpoint support.

        Overrides PausableWorker.run() to add checkpoint saving.
        """
        self.task_state.status = TaskStatus.RUNNING
        self.status_changed.emit(TaskStatus.RUNNING.value)

        pending = list(self.task_state.pending_paths)
        total = self.task_state.total_items

        # Calculate batches
        num_batches = (len(pending) + self.batch_size - 1) // self.batch_size
        current_batch = 0

        try:
            for i in range(0, len(pending), self.batch_size):
                # Check for pause/cancel before each batch
                if not self._wait_if_paused():
                    # Cancelled - save checkpoint before exit
                    self._save_checkpoint()
                    self.finished_work.emit(False, "Cancelled by user")
                    return

                batch = pending[i : i + self.batch_size]
                current_batch += 1

                for path in batch:
                    # Check for cancel between items
                    if self._check_cancelled():
                        self._save_checkpoint()
                        self.finished_work.emit(False, "Cancelled by user")
                        return

                    try:
                        result = self.process_item(path)
                        result_dict = self.get_result_dict(path, result)

                        if result.success:
                            self.task_state.mark_completed(path, result_dict)
                        else:
                            self.task_state.mark_failed(path, result.error or "Unknown error")

                        self.result_ready.emit(path, result_dict)

                    except Exception as e:
                        error_msg = str(e)
                        result_dict = self.get_result_dict(path, None, error=error_msg)
                        self.task_state.mark_failed(path, error_msg)
                        self.result_ready.emit(path, result_dict)

                    # Emit progress
                    processed = self.task_state.processed_count
                    percent = (processed / total) * 100 if total > 0 else 0
                    self.progress.emit(processed, total, percent)

                # Batch complete - save checkpoint
                self._save_checkpoint()
                self.batch_complete.emit(current_batch, num_batches)

                # Check for pause after batch (natural checkpoint)
                if self._is_paused:
                    if not self._wait_if_paused():
                        self.finished_work.emit(False, "Cancelled by user")
                        return

            # All done
            self.task_state.status = TaskStatus.COMPLETED
            self.status_changed.emit(TaskStatus.COMPLETED.value)
            self._save_checkpoint()

            failed_count = len(self.task_state.failed_paths)
            completed_count = len(self.task_state.completed_paths)

            if failed_count > 0:
                msg = f"Completed: {completed_count} measured, {failed_count} failed"
            else:
                msg = f"Successfully measured {completed_count} tracks"

            self.finished_work.emit(True, msg)

        except Exception as e:
            self.task_state.status = TaskStatus.FAILED
            self.status_changed.emit(TaskStatus.FAILED.value)
            self._save_checkpoint()
            self.error.emit(str(e))
            self.finished_work.emit(False, f"Error: {e}")

    def _save_checkpoint(self) -> None:
        """Save current task state to checkpoint."""
        try:
            self.checkpoint_manager.save(self.task_state)
            self.checkpoint_saved.emit(self.task_state.task_id)
        except Exception as e:
            # Log but don't fail the operation
            self.error.emit(f"Failed to save checkpoint: {e}")


class MeasureWorker(NormalizationWorker):
    """Worker for measuring loudness only (non-destructive)."""

    pass  # Same implementation as NormalizationWorker


class ApplyNormalizationWorker(PausableWorker):
    """Worker for applying normalization (destructive).

    This worker applies gain adjustments to audio files, either:
    - Destructive: Rewrites the audio file
    - Non-destructive: Updates VDJ database Volume field

    Note: For simplicity, this implementation only supports measurement.
    Destructive operations should be done carefully with the CLI.
    """

    checkpoint_saved = Signal(str)

    def __init__(
        self,
        task_state: TaskState,
        target_lufs: float = DEFAULT_LUFS_TARGET,
        destructive: bool = False,
        backup: bool = True,
        checkpoint_manager: CheckpointManager | None = None,
        batch_size: int = 10,  # Smaller batches for destructive ops
        parent: Any = None,
    ) -> None:
        """Initialize the apply worker.

        Args:
            task_state: TaskState with files to process.
            target_lufs: Target loudness in LUFS.
            destructive: Whether to modify audio files.
            backup: Whether to backup before modifying.
            checkpoint_manager: Manager for checkpoints.
            batch_size: Files per batch.
            parent: Optional parent QObject.
        """
        super().__init__(task_state, batch_size=batch_size, parent=parent)

        self.target_lufs = target_lufs
        self.destructive = destructive
        self.backup = backup
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self._processor = NormalizationProcessor(
            target_lufs=target_lufs,
            max_workers=1,
        )

    def process_item(self, path: str) -> NormalizationResult:
        """Apply normalization to a single file."""
        if self.destructive:
            results = self._processor.normalize_batch_parallel(
                [path], backup=self.backup
            )
        else:
            # Just measure for non-destructive (VDJ volume will be set separately)
            results = self._processor.measure_batch_parallel([path])

        if results:
            return results[0]

        return NormalizationResult(
            file_path=path,
            success=False,
            error="No result returned",
        )

    def get_result_dict(
        self,
        path: str,
        result: NormalizationResult | None,
        error: str | None = None,
    ) -> dict:
        """Convert result to dictionary."""
        if error:
            return {"path": path, "success": False, "error": error}

        if result is None:
            return {"path": path, "success": False, "error": "No result"}

        return {
            "path": result.file_path,
            "success": result.success,
            "current_lufs": result.current_lufs,
            "gain_db": result.gain_db,
            "error": result.error,
        }
