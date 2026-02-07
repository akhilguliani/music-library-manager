"""Base worker class with pause/resume/cancel support."""

import threading
from abc import abstractmethod
from typing import Any, Generic, TypeVar

from PySide6.QtCore import QThread, Signal, QMutex, QWaitCondition

from vdj_manager.ui.models.task_state import TaskState, TaskStatus


T = TypeVar("T")  # Result type


class WorkerSignals:
    """Mixin providing standard worker signals.

    These signals allow communication between the worker thread
    and the main UI thread.
    """

    pass


class PausableWorker(QThread):
    """Base class for pausable background workers.

    This worker processes items in batches, allowing the operation
    to be paused, resumed, or cancelled between batches. Progress
    and results are emitted as Qt signals for thread-safe UI updates.

    Subclasses must implement:
        - process_item(path): Process a single item
        - get_result_dict(path, result): Convert result to dict for storage

    Signals:
        progress: Emitted when progress updates (current, total, percent)
        result_ready: Emitted when an item is processed (path, result_dict)
        batch_complete: Emitted after each batch (batch_num, total_batches)
        finished_work: Emitted when all work completes (success, message)
        error: Emitted on error (error_message)
        status_changed: Emitted when status changes (new_status)
    """

    # Signals for UI communication
    progress = Signal(int, int, float)  # current, total, percent
    result_ready = Signal(str, dict)  # path, result_dict
    batch_complete = Signal(int, int)  # batch_num, total_batches
    finished_work = Signal(bool, str)  # success, message
    error = Signal(str)  # error message
    status_changed = Signal(str)  # new status

    # Default batch size for checkpoint granularity
    DEFAULT_BATCH_SIZE = 50

    def __init__(
        self,
        task_state: TaskState,
        batch_size: int | None = None,
        parent: Any = None,
    ) -> None:
        """Initialize the pausable worker.

        Args:
            task_state: TaskState containing items to process.
            batch_size: Number of items per batch. Defaults to 50.
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self.task_state = task_state
        self.batch_size = batch_size or self.DEFAULT_BATCH_SIZE

        # Threading primitives for pause/resume
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()
        self._is_paused = False
        self._is_cancelled = False

    @property
    def is_paused(self) -> bool:
        """Check if worker is currently paused."""
        return self._is_paused

    @property
    def is_cancelled(self) -> bool:
        """Check if worker has been cancelled."""
        return self._is_cancelled

    def pause(self) -> None:
        """Request the worker to pause after the current batch."""
        self._mutex.lock()
        try:
            self._is_paused = True
            self.task_state.status = TaskStatus.PAUSED
            self.status_changed.emit(TaskStatus.PAUSED.value)
        finally:
            self._mutex.unlock()

    def resume(self) -> None:
        """Resume a paused worker."""
        self._mutex.lock()
        try:
            self._is_paused = False
            self.task_state.status = TaskStatus.RUNNING
            self.status_changed.emit(TaskStatus.RUNNING.value)
            self._pause_condition.wakeAll()
        finally:
            self._mutex.unlock()

    def cancel(self) -> None:
        """Request the worker to cancel after the current item."""
        self._mutex.lock()
        try:
            self._is_cancelled = True
            self._is_paused = False  # Unblock if paused
            self.task_state.status = TaskStatus.CANCELLED
            self.status_changed.emit(TaskStatus.CANCELLED.value)
            self._pause_condition.wakeAll()  # Unblock wait
        finally:
            self._mutex.unlock()

    def _wait_if_paused(self) -> bool:
        """Wait if paused, return False if cancelled.

        Returns:
            True if should continue, False if cancelled.
        """
        self._mutex.lock()
        try:
            while self._is_paused and not self._is_cancelled:
                self._pause_condition.wait(self._mutex)
            return not self._is_cancelled
        finally:
            self._mutex.unlock()

    def _check_cancelled(self) -> bool:
        """Check if cancelled without blocking.

        Returns:
            True if cancelled.
        """
        self._mutex.lock()
        try:
            return self._is_cancelled
        finally:
            self._mutex.unlock()

    @abstractmethod
    def process_item(self, path: str) -> Any:
        """Process a single item.

        Subclasses must implement this method to perform the actual work.

        Args:
            path: File path to process.

        Returns:
            Processing result (type depends on subclass).

        Raises:
            Exception: If processing fails.
        """
        raise NotImplementedError

    @abstractmethod
    def get_result_dict(self, path: str, result: Any, error: str | None = None) -> dict:
        """Convert a processing result to a dictionary for storage.

        Args:
            path: File path that was processed.
            result: Processing result from process_item.
            error: Error message if processing failed.

        Returns:
            Dictionary representation of the result.
        """
        raise NotImplementedError

    def run(self) -> None:
        """Main worker thread execution.

        Processes items in batches with pause/cancel support.
        """
        self.task_state.status = TaskStatus.RUNNING
        self.status_changed.emit(TaskStatus.RUNNING.value)

        pending = list(self.task_state.pending_paths)
        total = self.task_state.total_items
        processed = self.task_state.processed_count

        # Calculate batches
        num_batches = (len(pending) + self.batch_size - 1) // self.batch_size
        current_batch = 0

        try:
            for i in range(0, len(pending), self.batch_size):
                # Check for pause/cancel before each batch
                if not self._wait_if_paused():
                    # Cancelled
                    self.finished_work.emit(False, "Cancelled by user")
                    return

                batch = pending[i : i + self.batch_size]
                current_batch += 1

                for path in batch:
                    # Check for cancel between items
                    if self._check_cancelled():
                        self.finished_work.emit(False, "Cancelled by user")
                        return

                    try:
                        result = self.process_item(path)
                        result_dict = self.get_result_dict(path, result)
                        self.task_state.mark_completed(path, result_dict)
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

                # Batch complete - good checkpoint opportunity
                self.batch_complete.emit(current_batch, num_batches)

            # All done
            self.task_state.status = TaskStatus.COMPLETED
            self.status_changed.emit(TaskStatus.COMPLETED.value)

            failed_count = len(self.task_state.failed_paths)
            completed_count = len(self.task_state.completed_paths)

            if failed_count > 0:
                msg = f"Completed with {failed_count} failures out of {total} items"
            else:
                msg = f"Successfully processed {completed_count} items"

            self.finished_work.emit(True, msg)

        except Exception as e:
            self.task_state.status = TaskStatus.FAILED
            self.status_changed.emit(TaskStatus.FAILED.value)
            self.error.emit(str(e))
            self.finished_work.emit(False, f"Error: {e}")


class SimpleWorker(QThread):
    """Simple non-pausable worker for quick operations.

    Use this for operations that don't need pause/resume support,
    like loading database or quick queries.

    Signals:
        finished_work: Emitted when work completes (result)
        error: Emitted on error (error_message)
    """

    finished_work = Signal(object)  # result
    error = Signal(str)  # error message

    def __init__(self, parent: Any = None) -> None:
        """Initialize the simple worker."""
        super().__init__(parent)

    @abstractmethod
    def do_work(self) -> Any:
        """Perform the work.

        Subclasses must implement this method.

        Returns:
            Result of the work.
        """
        raise NotImplementedError

    def run(self) -> None:
        """Execute the work."""
        try:
            result = self.do_work()
            self.finished_work.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ProgressSimpleWorker(QThread):
    """Non-pausable worker with progress feedback.

    Use this for operations that don't need pause/resume but do need
    to report progress (e.g., validation, scanning).

    Signals:
        progress: Emitted with progress updates (current, total, message)
        finished_work: Emitted when work completes (result)
        error: Emitted on error (error_message)
    """

    progress = Signal(int, int, str)  # current, total, message
    finished_work = Signal(object)  # result
    error = Signal(str)  # error message

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request cancellation."""
        self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    @abstractmethod
    def do_work(self) -> Any:
        """Perform the work. Subclass should call self.report_progress() periodically."""
        raise NotImplementedError

    def report_progress(self, current: int, total: int, message: str = "") -> None:
        """Emit progress from within do_work()."""
        self.progress.emit(current, total, message)

    def run(self) -> None:
        try:
            result = self.do_work()
            self.finished_work.emit(result)
        except Exception as e:
            self.error.emit(str(e))
