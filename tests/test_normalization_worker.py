"""Tests for normalization worker."""

import pytest
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch, PropertyMock

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
from vdj_manager.ui.state.checkpoint_manager import CheckpointManager
from vdj_manager.ui.workers.normalization_worker import (
    NormalizationWorker,
    MeasureWorker,
)
from vdj_manager.normalize.processor import NormalizationResult


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
def temp_checkpoint_dir():
    """Create a temporary directory for checkpoints."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def checkpoint_manager(temp_checkpoint_dir):
    """Create a checkpoint manager with temp directory."""
    return CheckpointManager(checkpoint_dir=temp_checkpoint_dir)


@pytest.fixture
def task_state():
    """Create a task state for testing."""
    paths = [f"/path/to/track{i}.mp3" for i in range(5)]
    return TaskState(
        task_id="test_norm_task",
        task_type=TaskType.NORMALIZE,
        status=TaskStatus.PENDING,
        total_items=len(paths),
        pending_paths=list(paths),
        config={"target_lufs": -14.0},
    )


class TestNormalizationWorker:
    """Tests for NormalizationWorker."""

    def test_worker_creation(self, app, task_state, checkpoint_manager):
        """Test worker can be created."""
        worker = NormalizationWorker(
            task_state,
            target_lufs=-14.0,
            checkpoint_manager=checkpoint_manager,
        )
        assert worker is not None
        assert worker.target_lufs == -14.0

    def test_worker_parallel_workers_config(self, app, task_state, checkpoint_manager):
        """Test worker respects max_workers configuration."""
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()

        # Default workers should be CPU count - 1
        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
        )
        assert worker.max_workers == max(1, cpu_count - 1)

        # Custom workers setting
        worker_custom = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
            max_workers=4,
        )
        assert worker_custom.max_workers == 4

    def test_get_result_dict_success(self, app, task_state, checkpoint_manager):
        """Test result dict conversion for success."""
        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
        )

        result = NormalizationResult(
            file_path="/path/to/track.mp3",
            success=True,
            current_lufs=-12.5,
            gain_db=-1.5,
        )

        result_dict = worker.get_result_dict("/path/to/track.mp3", result)

        assert result_dict["success"] is True
        assert result_dict["current_lufs"] == -12.5
        assert result_dict["gain_db"] == -1.5
        assert result_dict["error"] is None

    def test_get_result_dict_failure(self, app, task_state, checkpoint_manager):
        """Test result dict conversion for failure."""
        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
        )

        result = NormalizationResult(
            file_path="/path/to/track.mp3",
            success=False,
            error="File not found",
        )

        result_dict = worker.get_result_dict("/path/to/track.mp3", result)

        assert result_dict["success"] is False
        assert result_dict["error"] == "File not found"

    def test_get_result_dict_with_error_override(self, app, task_state, checkpoint_manager):
        """Test result dict with error parameter."""
        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
        )

        result_dict = worker.get_result_dict(
            "/path/to/track.mp3",
            None,
            error="Custom error",
        )

        assert result_dict["success"] is False
        assert result_dict["error"] == "Custom error"

    @patch("vdj_manager.ui.workers.normalization_worker.NormalizationProcessor")
    def test_worker_processes_items(
        self, mock_processor_cls, app, task_state, checkpoint_manager
    ):
        """Test worker processes all items."""
        # Mock the processor
        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        # Mock successful results
        mock_processor.measure_batch_parallel.return_value = [
            NormalizationResult(
                file_path=task_state.pending_paths[0],
                success=True,
                current_lufs=-13.5,
                gain_db=-0.5,
            )
        ]

        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
            batch_size=2,
        )

        results = []
        finished = []

        worker.result_ready.connect(lambda p, r: results.append((p, r)))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success, "Worker did not finish in time"

        assert len(finished) == 1
        assert finished[0][0] is True  # success

    @patch("vdj_manager.ui.workers.normalization_worker.NormalizationProcessor")
    def test_worker_saves_checkpoints(
        self, mock_processor_cls, app, task_state, checkpoint_manager
    ):
        """Test worker saves checkpoints after batches."""
        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor
        mock_processor.measure_batch_parallel.return_value = [
            NormalizationResult(
                file_path="path",
                success=True,
                current_lufs=-14.0,
                gain_db=0.0,
            )
        ]

        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
            batch_size=2,
        )

        checkpoint_signals = []
        finished = []

        worker.checkpoint_saved.connect(lambda tid: checkpoint_signals.append(tid))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success

        # Should have saved checkpoints
        assert len(checkpoint_signals) >= 1

        # Verify checkpoint file exists
        loaded = checkpoint_manager.load(task_state.task_id)
        assert loaded is not None

    @patch("vdj_manager.ui.workers.normalization_worker.NormalizationProcessor")
    def test_worker_handles_pause_and_resume(
        self, mock_processor_cls, app, task_state, checkpoint_manager
    ):
        """Test worker can be paused and resumed."""
        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        # Slow down processing to allow pause
        def slow_measure(paths):
            time.sleep(0.05)
            return [
                NormalizationResult(
                    file_path=paths[0],
                    success=True,
                    current_lufs=-14.0,
                    gain_db=0.0,
                )
            ]

        mock_processor.measure_batch_parallel.side_effect = slow_measure

        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
            batch_size=1,
        )

        results = []
        finished = []

        worker.result_ready.connect(lambda p, r: results.append((p, r)))
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()

        # Let some work happen
        time.sleep(0.1)
        app.processEvents()

        # Pause
        worker.pause()
        results_at_pause = len(results)

        time.sleep(0.1)
        app.processEvents()

        # Should not have progressed much (maybe current item finished)
        assert len(results) <= results_at_pause + 1

        # Resume
        worker.resume()

        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success

        # Should complete all items
        assert finished[0][0] is True

    @patch("vdj_manager.ui.workers.normalization_worker.NormalizationProcessor")
    def test_worker_handles_cancel(
        self, mock_processor_cls, app, task_state, checkpoint_manager
    ):
        """Test worker can be cancelled."""
        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        def slow_measure(paths):
            time.sleep(0.05)
            return [
                NormalizationResult(
                    file_path=paths[0],
                    success=True,
                    current_lufs=-14.0,
                    gain_db=0.0,
                )
            ]

        mock_processor.measure_batch_parallel.side_effect = slow_measure

        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
            batch_size=1,
        )

        finished = []
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        time.sleep(0.1)
        app.processEvents()

        worker.cancel()

        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success

        # Should report cancellation
        assert finished[0][0] is False
        assert "Cancel" in finished[0][1]

        # Checkpoint should be saved
        loaded = checkpoint_manager.load(task_state.task_id)
        assert loaded is not None
        assert loaded.status == TaskStatus.CANCELLED


class TestMeasureWorker:
    """Tests for MeasureWorker (alias for NormalizationWorker)."""

    def test_measure_worker_is_normalization_worker(self):
        """Test MeasureWorker is same as NormalizationWorker."""
        assert issubclass(MeasureWorker, NormalizationWorker)


class TestWorkerEdgeCases:
    """Edge case tests for normalization worker."""

    @patch("vdj_manager.ui.workers.normalization_worker.NormalizationProcessor")
    def test_empty_task(self, mock_processor_cls, app, checkpoint_manager):
        """Test worker with no items."""
        mock_processor_cls.return_value = MagicMock()

        task_state = TaskState(
            task_id="empty_task",
            task_type=TaskType.NORMALIZE,
            total_items=0,
            pending_paths=[],
        )

        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
        )

        finished = []
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success

        assert finished[0][0] is True
        assert task_state.status == TaskStatus.COMPLETED

    @patch("vdj_manager.ui.workers.normalization_worker.NormalizationProcessor")
    def test_all_failures(self, mock_processor_cls, app, task_state, checkpoint_manager):
        """Test worker when all items fail."""
        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        mock_processor.measure_batch_parallel.return_value = [
            NormalizationResult(
                file_path="path",
                success=False,
                error="File not found",
            )
        ]

        worker = NormalizationWorker(
            task_state,
            checkpoint_manager=checkpoint_manager,
            batch_size=2,
        )

        finished = []
        worker.finished_work.connect(lambda s, m: finished.append((s, m)))

        worker.start()
        success = process_events_until(lambda: len(finished) > 0, timeout_ms=10000)
        assert success

        # Should still complete (with failures noted)
        assert finished[0][0] is True
        assert "failed" in finished[0][1].lower()
        assert len(task_state.failed_paths) == 5
