"""Tests for pausable worker base class."""

import time
from typing import Any

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
from vdj_manager.ui.workers.base_worker import PausableWorker, SimpleWorker


def process_events_until(condition_fn, timeout_ms=5000, interval_ms=10):
    """Process Qt events until condition is true or timeout."""
    app = QCoreApplication.instance()
    start = time.time()
    timeout_sec = timeout_ms / 1000

    while not condition_fn():
        if time.time() - start > timeout_sec:
            return False
        app.processEvents()
        time.sleep(interval_ms / 1000)

    return True


class MockPausableWorker(PausableWorker):
    """Mock worker for testing that processes items with a small delay."""

    def __init__(self, task_state: TaskState, process_time: float = 0.001, **kwargs):
        super().__init__(task_state, **kwargs)
        self.process_time = process_time
        self.processed_items: list[str] = []

    def process_item(self, path: str) -> dict:
        """Simulate processing with a small delay."""
        time.sleep(self.process_time)
        self.processed_items.append(path)
        return {"path": path, "lufs": -14.0}

    def get_result_dict(self, path: str, result: Any, error: str | None = None) -> dict:
        """Convert result to dict."""
        if error:
            return {"path": path, "success": False, "error": error}
        return {"path": path, "success": True, **(result or {})}


class FailingWorker(PausableWorker):
    """Worker that fails on specific items."""

    def __init__(self, task_state: TaskState, fail_on: list[str], **kwargs):
        super().__init__(task_state, **kwargs)
        self.fail_on = fail_on

    def process_item(self, path: str) -> dict:
        if path in self.fail_on:
            raise ValueError(f"Failed to process {path}")
        return {"path": path, "processed": True}

    def get_result_dict(self, path: str, result: Any, error: str | None = None) -> dict:
        if error:
            return {"path": path, "success": False, "error": error}
        return {"path": path, "success": True}


class MockSimpleWorker(SimpleWorker):
    """Mock simple worker for testing."""

    def __init__(self, return_value: Any = None, raise_error: Exception | None = None):
        super().__init__()
        self.return_value = return_value
        self.raise_error = raise_error

    def do_work(self) -> Any:
        if self.raise_error:
            raise self.raise_error
        return self.return_value


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
def task_state():
    """Create a task state with test items."""
    paths = [f"/path/to/file{i}.mp3" for i in range(10)]
    return TaskState(
        task_id="test_task",
        task_type=TaskType.NORMALIZE,
        status=TaskStatus.PENDING,
        total_items=len(paths),
        pending_paths=list(paths),
        config={"target_lufs": -14.0},
    )


class TestPausableWorker:
    """Tests for PausableWorker base class."""

    def test_worker_creation(self, app, task_state):
        """Test worker can be created."""
        worker = MockPausableWorker(task_state)
        assert worker is not None
        assert worker.task_state is task_state
        assert worker.batch_size == PausableWorker.DEFAULT_BATCH_SIZE

    def test_worker_custom_batch_size(self, app, task_state):
        """Test worker with custom batch size."""
        worker = MockPausableWorker(task_state, batch_size=5)
        assert worker.batch_size == 5

    def test_worker_initial_state(self, app, task_state):
        """Test worker initial state."""
        worker = MockPausableWorker(task_state)
        assert not worker.is_paused
        assert not worker.is_cancelled

    def test_pause_sets_state(self, app, task_state):
        """Test that pause sets the paused state."""
        worker = MockPausableWorker(task_state)

        worker.pause()

        assert worker.is_paused
        assert task_state.status == TaskStatus.PAUSED

    def test_resume_clears_pause(self, app, task_state):
        """Test that resume clears the paused state."""
        worker = MockPausableWorker(task_state)

        worker.pause()
        assert worker.is_paused

        worker.resume()
        assert not worker.is_paused
        assert task_state.status == TaskStatus.RUNNING

    def test_cancel_sets_state(self, app, task_state):
        """Test that cancel sets the cancelled state."""
        worker = MockPausableWorker(task_state)

        worker.cancel()

        assert worker.is_cancelled
        assert task_state.status == TaskStatus.CANCELLED

    def test_worker_completes_all_items(self, app, task_state):
        """Test that worker processes all items to completion."""
        worker = MockPausableWorker(task_state, batch_size=3)

        # Track signals
        progress_updates = []
        results = []
        finished = []

        worker.progress.connect(lambda c, t, p: progress_updates.append((c, t, p)))
        worker.result_ready.connect(lambda p, r: results.append((p, r)))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        # Run worker
        worker.start()

        # Wait for completion
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        # Verify all items processed
        assert len(results) == 10
        assert len(progress_updates) == 10
        assert len(finished) == 1
        assert finished[0][0] is True  # success

        # Verify task state updated
        assert task_state.status == TaskStatus.COMPLETED
        assert len(task_state.completed_paths) == 10
        assert len(task_state.pending_paths) == 0

    def test_worker_handles_failures(self, app, task_state):
        """Test that worker handles item failures gracefully."""
        fail_on = ["/path/to/file3.mp3", "/path/to/file7.mp3"]
        worker = FailingWorker(task_state, fail_on=fail_on, batch_size=3)

        results = []
        finished = []

        worker.result_ready.connect(lambda p, r: results.append((p, r)))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        # Verify completion with failures reported
        assert len(results) == 10
        assert len(finished) == 1
        assert finished[0][0] is True  # Still "success" but with failures

        # Verify failures tracked
        assert len(task_state.failed_paths) == 2
        assert len(task_state.completed_paths) == 8

    def test_worker_cancel_stops_processing(self, app, task_state):
        """Test that cancel stops processing."""
        # Use longer process time to allow cancellation
        worker = MockPausableWorker(task_state, process_time=0.05, batch_size=2)

        results = []
        finished = []

        worker.result_ready.connect(lambda p, r: results.append((p, r)))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()

        # Process a few events then cancel
        time.sleep(0.1)
        app.processEvents()
        worker.cancel()

        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        # Should have processed some but not all
        assert len(results) < 10
        assert len(finished) == 1
        assert finished[0][0] is False  # Not successful
        assert "Cancel" in finished[0][1]

    def test_batch_complete_signal(self, app, task_state):
        """Test that batch complete signals are emitted."""
        worker = MockPausableWorker(task_state, batch_size=3)

        batch_completes = []
        finished = []

        worker.batch_complete.connect(lambda b, t: batch_completes.append((b, t)))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        # 10 items / 3 per batch = 4 batches
        assert len(batch_completes) == 4
        assert batch_completes[-1][0] == 4  # Last batch number
        assert batch_completes[-1][1] == 4  # Total batches

    def test_status_changed_signals(self, app, task_state):
        """Test that status change signals are emitted."""
        worker = MockPausableWorker(task_state, batch_size=5)

        status_changes = []
        finished = []

        worker.status_changed.connect(lambda s: status_changes.append(s))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        # Should have at least RUNNING and COMPLETED
        assert TaskStatus.RUNNING.value in status_changes
        assert TaskStatus.COMPLETED.value in status_changes


class TestSimpleWorker:
    """Tests for SimpleWorker class."""

    def test_simple_worker_success(self, app):
        """Test simple worker completes successfully."""
        worker = MockSimpleWorker(return_value={"data": "test"})

        results = []
        worker.finished_work.connect(lambda r: results.append(r))

        worker.start()
        success = process_events_until(lambda: len(results) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        assert len(results) == 1
        assert results[0] == {"data": "test"}

    def test_simple_worker_error(self, app):
        """Test simple worker handles errors."""
        worker = MockSimpleWorker(raise_error=ValueError("Test error"))

        errors = []
        worker.error.connect(lambda e: errors.append(e))

        worker.start()
        success = process_events_until(lambda: len(errors) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        assert len(errors) == 1
        assert "Test error" in errors[0]


class TestPausableWorkerEdgeCases:
    """Edge case tests for PausableWorker."""

    def test_empty_pending_paths(self, app):
        """Test worker with no items to process."""
        task_state = TaskState(
            task_id="empty_task",
            task_type=TaskType.NORMALIZE,
            total_items=0,
            pending_paths=[],
        )
        worker = MockPausableWorker(task_state)

        finished = []
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        assert len(finished) == 1
        assert finished[0][0] is True
        assert task_state.status == TaskStatus.COMPLETED

    def test_cancel_before_start(self, app, task_state):
        """Test cancelling worker before starting."""
        worker = MockPausableWorker(task_state)

        worker.cancel()

        finished = []
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        assert len(finished) == 1
        assert finished[0][0] is False

    def test_single_item_batch(self, app):
        """Test worker with batch size of 1."""
        paths = [f"/path/to/file{i}.mp3" for i in range(3)]
        task_state = TaskState(
            task_id="single_batch_task",
            task_type=TaskType.NORMALIZE,
            total_items=3,
            pending_paths=list(paths),
        )
        worker = MockPausableWorker(task_state, batch_size=1)

        batch_completes = []
        finished = []

        worker.batch_complete.connect(lambda b, t: batch_completes.append((b, t)))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        assert len(batch_completes) == 3
