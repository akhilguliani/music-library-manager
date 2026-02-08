"""Normalization worker with checkpoint support and parallel processing."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal

from vdj_manager.config import DEFAULT_LUFS_TARGET
from vdj_manager.normalize.measurement_cache import MeasurementCache
from vdj_manager.normalize.processor import (
    NormalizationProcessor,
    NormalizationResult,
    _measure_single_file,
    _normalize_single_file,
)
from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
from vdj_manager.ui.state.checkpoint_manager import CheckpointManager
from vdj_manager.ui.workers.base_worker import PausableWorker


class NormalizationWorker(PausableWorker):
    """Worker for measuring and normalizing audio loudness with parallel processing.

    This worker uses ProcessPoolExecutor for true parallel processing:
    - Multiple files are measured simultaneously using multiple CPU cores
    - Pause/Resume works at batch boundaries
    - Checkpoint persistence for task recovery
    - Qt signals for real-time UI updates

    The worker processes files in batches, with each batch processed in
    parallel. Checkpoints are saved after each batch completes.

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
        max_workers: int | None = None,
        measurement_cache: MeasurementCache | None = None,
        parent: Any = None,
    ) -> None:
        """Initialize the normalization worker.

        Args:
            task_state: TaskState with files to process.
            target_lufs: Target loudness in LUFS (default -14).
            checkpoint_manager: Manager for saving checkpoints.
            batch_size: Files per batch (checkpoint frequency).
            max_workers: Number of parallel workers (default: CPU count - 1).
            measurement_cache: Optional cache for skipping already-measured files.
            parent: Optional parent QObject.
        """
        super().__init__(task_state, batch_size=batch_size, parent=parent)

        self.target_lufs = target_lufs
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self.ffmpeg_path = "ffmpeg"
        self._cache_db_path: str | None = (
            str(measurement_cache.db_path) if measurement_cache else None
        )

        # Keep processor for single-file fallback operations
        self._processor = NormalizationProcessor(
            target_lufs=target_lufs,
            max_workers=self.max_workers,
        )

    def process_item(self, path: str) -> NormalizationResult:
        """Measure loudness for a single file (used for fallback only).

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
        """Main worker execution with parallel processing and checkpoint support.

        Processes files in parallel batches using ProcessPoolExecutor.
        Each batch is processed with multiple workers, then results are
        collected and a checkpoint is saved before the next batch.
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

                # Process entire batch in parallel
                self._process_batch_parallel(batch, total)

                # Check for cancel after batch processing
                if self._check_cancelled():
                    self._save_checkpoint()
                    self.finished_work.emit(False, "Cancelled by user")
                    return

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

    def _process_batch_parallel(self, batch: list[str], total: int) -> None:
        """Process a batch of files in parallel.

        Args:
            batch: List of file paths to process.
            total: Total number of files (for progress calculation).
        """
        # Prepare arguments for parallel processing (cache DB path included)
        args_list = [
            (path, self.target_lufs, self.ffmpeg_path, self._cache_db_path)
            for path in batch
        ]

        # Process batch in parallel using ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs
            futures = {
                executor.submit(_measure_single_file, args): args[0]
                for args in args_list
            }

            # Collect results as they complete
            for future in as_completed(futures):
                path = futures[future]

                try:
                    result = future.result()
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

                # Emit progress after each file completes
                processed = self.task_state.processed_count
                percent = (processed / total) * 100 if total > 0 else 0
                self.progress.emit(processed, total, percent)

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
    """Worker for applying normalization with parallel processing.

    This worker applies gain adjustments to audio files, either:
    - Destructive: Rewrites the audio file with loudnorm filter
    - Non-destructive: Uses cached measurements for VDJ Volume updates

    Uses ProcessPoolExecutor for parallel processing and can leverage
    the measurement cache to skip redundant ffmpeg passes.
    """

    checkpoint_saved = Signal(str)

    def __init__(
        self,
        task_state: TaskState,
        target_lufs: float = DEFAULT_LUFS_TARGET,
        destructive: bool = False,
        backup: bool = True,
        checkpoint_manager: CheckpointManager | None = None,
        batch_size: int = 10,
        max_workers: int | None = None,
        measurement_cache: MeasurementCache | None = None,
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
            max_workers: Number of parallel workers.
            measurement_cache: Optional cache for skipping measurements.
            parent: Optional parent QObject.
        """
        super().__init__(task_state, batch_size=batch_size, parent=parent)

        self.target_lufs = target_lufs
        self.destructive = destructive
        self.backup = backup
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self._cache_db_path: str | None = (
            str(measurement_cache.db_path) if measurement_cache else None
        )
        self._processor = NormalizationProcessor(
            target_lufs=target_lufs,
            max_workers=self.max_workers,
        )

    def process_item(self, path: str) -> NormalizationResult:
        """Apply normalization to a single file (fallback only)."""
        if self.destructive:
            results = self._processor.normalize_batch_parallel(
                [path], backup=self.backup
            )
        else:
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

    def run(self) -> None:
        """Main execution with parallel processing.

        Non-destructive mode uses the measurement cache to return results
        instantly for already-measured files. Destructive mode uses
        ProcessPoolExecutor for parallel encoding.
        """
        self.task_state.status = TaskStatus.RUNNING
        self.status_changed.emit(TaskStatus.RUNNING.value)

        pending = list(self.task_state.pending_paths)
        total = self.task_state.total_items

        num_batches = (len(pending) + self.batch_size - 1) // self.batch_size
        current_batch = 0

        try:
            for i in range(0, len(pending), self.batch_size):
                if not self._wait_if_paused():
                    self._save_checkpoint()
                    self.finished_work.emit(False, "Cancelled by user")
                    return

                batch = pending[i : i + self.batch_size]
                current_batch += 1

                if self.destructive:
                    self._process_batch_destructive(batch, total)
                else:
                    self._process_batch_nondestruct(batch, total)

                if self._check_cancelled():
                    self._save_checkpoint()
                    self.finished_work.emit(False, "Cancelled by user")
                    return

                self._save_checkpoint()
                self.batch_complete.emit(current_batch, num_batches)

                if self._is_paused:
                    if not self._wait_if_paused():
                        self.finished_work.emit(False, "Cancelled by user")
                        return

            self.task_state.status = TaskStatus.COMPLETED
            self.status_changed.emit(TaskStatus.COMPLETED.value)
            self._save_checkpoint()

            failed_count = len(self.task_state.failed_paths)
            completed_count = len(self.task_state.completed_paths)

            if failed_count > 0:
                msg = f"Completed: {completed_count} applied, {failed_count} failed"
            else:
                msg = f"Successfully applied normalization to {completed_count} tracks"

            self.finished_work.emit(True, msg)

        except Exception as e:
            self.task_state.status = TaskStatus.FAILED
            self.status_changed.emit(TaskStatus.FAILED.value)
            self._save_checkpoint()
            self.error.emit(str(e))
            self.finished_work.emit(False, f"Error: {e}")

    def _process_batch_nondestruct(self, batch: list[str], total: int) -> None:
        """Process a non-destructive batch using cache + parallel measurement.

        Files with cached measurements are returned immediately.
        Only uncached files are sent to ffmpeg.
        """
        # Check cache for all files in the batch
        cache_hits: dict[str, dict] = {}
        uncached: list[str] = []
        if self._cache_db_path:
            cache = MeasurementCache(db_path=Path(self._cache_db_path))
            cache_hits = cache.get_batch(batch, self.target_lufs)

        for path in batch:
            if path in cache_hits:
                cached = cache_hits[path]
                result = NormalizationResult(
                    file_path=path,
                    success=True,
                    current_lufs=cached["integrated_lufs"],
                    gain_db=cached["gain_db"],
                )
                result_dict = self.get_result_dict(path, result)
                self.task_state.mark_completed(path, result_dict)
                self.result_ready.emit(path, result_dict)

                processed = self.task_state.processed_count
                percent = (processed / total) * 100 if total > 0 else 0
                self.progress.emit(processed, total, percent)
            else:
                uncached.append(path)

        # Measure uncached files in parallel
        if uncached:
            args_list = [
                (p, self.target_lufs, "ffmpeg", self._cache_db_path)
                for p in uncached
            ]
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(_measure_single_file, args): args[0]
                    for args in args_list
                }
                for future in as_completed(futures):
                    path = futures[future]
                    try:
                        result = future.result()
                        result_dict = self.get_result_dict(path, result)
                        if result.success:
                            self.task_state.mark_completed(path, result_dict)
                        else:
                            self.task_state.mark_failed(
                                path, result.error or "Unknown error"
                            )
                        self.result_ready.emit(path, result_dict)
                    except Exception as e:
                        error_msg = str(e)
                        result_dict = self.get_result_dict(path, None, error=error_msg)
                        self.task_state.mark_failed(path, error_msg)
                        self.result_ready.emit(path, result_dict)

                    processed = self.task_state.processed_count
                    percent = (processed / total) * 100 if total > 0 else 0
                    self.progress.emit(processed, total, percent)

    def _process_batch_destructive(self, batch: list[str], total: int) -> None:
        """Process a destructive batch in parallel."""
        args_list = [
            (p, self.target_lufs, "ffmpeg", self.backup, self._cache_db_path)
            for p in batch
        ]
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_normalize_single_file, args): args[0]
                for args in args_list
            }
            for future in as_completed(futures):
                path = futures[future]
                try:
                    result = future.result()
                    result_dict = self.get_result_dict(path, result)
                    if result.success:
                        self.task_state.mark_completed(path, result_dict)
                    else:
                        self.task_state.mark_failed(
                            path, result.error or "Unknown error"
                        )
                    self.result_ready.emit(path, result_dict)
                except Exception as e:
                    error_msg = str(e)
                    result_dict = self.get_result_dict(path, None, error=error_msg)
                    self.task_state.mark_failed(path, error_msg)
                    self.result_ready.emit(path, result_dict)

                processed = self.task_state.processed_count
                percent = (processed / total) * 100 if total > 0 else 0
                self.progress.emit(processed, total, percent)

    def _save_checkpoint(self) -> None:
        """Save current task state to checkpoint."""
        try:
            self.checkpoint_manager.save(self.task_state)
            self.checkpoint_saved.emit(self.task_state.task_id)
        except Exception as e:
            self.error.emit(f"Failed to save checkpoint: {e}")
