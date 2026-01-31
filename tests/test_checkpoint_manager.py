"""Tests for checkpoint manager and task state."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType
from vdj_manager.ui.state.checkpoint_manager import CheckpointManager


class TestTaskState:
    """Tests for TaskState dataclass."""

    def test_create_task_state(self):
        """Test creating a basic task state."""
        state = TaskState(
            task_id="test_001",
            task_type=TaskType.NORMALIZE,
        )

        assert state.task_id == "test_001"
        assert state.task_type == TaskType.NORMALIZE
        assert state.status == TaskStatus.PENDING
        assert state.total_items == 0
        assert state.completed_paths == []
        assert state.pending_paths == []
        assert state.failed_paths == {}

    def test_task_state_with_paths(self):
        """Test task state with file paths."""
        paths = ["/path/to/file1.mp3", "/path/to/file2.mp3", "/path/to/file3.mp3"]

        state = TaskState(
            task_id="test_002",
            task_type=TaskType.MEASURE,
            total_items=len(paths),
            pending_paths=list(paths),
        )

        assert state.total_items == 3
        assert len(state.pending_paths) == 3
        assert state.processed_count == 0
        assert state.progress_percent == 0.0

    def test_mark_completed(self):
        """Test marking a path as completed."""
        paths = ["/path/to/file1.mp3", "/path/to/file2.mp3"]

        state = TaskState(
            task_id="test_003",
            task_type=TaskType.NORMALIZE,
            total_items=2,
            pending_paths=list(paths),
        )

        state.mark_completed("/path/to/file1.mp3", {"lufs": -14.0})

        assert len(state.pending_paths) == 1
        assert len(state.completed_paths) == 1
        assert state.processed_count == 1
        assert state.progress_percent == 50.0
        assert len(state.results) == 1

    def test_mark_failed(self):
        """Test marking a path as failed."""
        paths = ["/path/to/file1.mp3", "/path/to/file2.mp3"]

        state = TaskState(
            task_id="test_004",
            task_type=TaskType.NORMALIZE,
            total_items=2,
            pending_paths=list(paths),
        )

        state.mark_failed("/path/to/file1.mp3", "File not found")

        assert len(state.pending_paths) == 1
        assert len(state.failed_paths) == 1
        assert state.failed_paths["/path/to/file1.mp3"] == "File not found"
        assert state.processed_count == 1

    def test_is_resumable(self):
        """Test is_resumable property."""
        # Pending task with items is not resumable
        state = TaskState(
            task_id="test_005",
            task_type=TaskType.NORMALIZE,
            status=TaskStatus.PENDING,
            pending_paths=["/path/to/file.mp3"],
        )
        assert not state.is_resumable

        # Paused task with items is resumable
        state.status = TaskStatus.PAUSED
        assert state.is_resumable

        # Running task with items is resumable (crashed)
        state.status = TaskStatus.RUNNING
        assert state.is_resumable

        # Completed task is not resumable
        state.status = TaskStatus.COMPLETED
        assert not state.is_resumable

        # Paused task without items is not resumable
        state.status = TaskStatus.PAUSED
        state.pending_paths = []
        assert not state.is_resumable

    def test_is_complete(self):
        """Test is_complete property."""
        state = TaskState(task_id="test_006", task_type=TaskType.NORMALIZE)

        state.status = TaskStatus.PENDING
        assert not state.is_complete

        state.status = TaskStatus.RUNNING
        assert not state.is_complete

        state.status = TaskStatus.PAUSED
        assert not state.is_complete

        state.status = TaskStatus.COMPLETED
        assert state.is_complete

        state.status = TaskStatus.CANCELLED
        assert state.is_complete

        state.status = TaskStatus.FAILED
        assert state.is_complete

    def test_to_dict_and_from_dict(self):
        """Test serialization to dict and back."""
        original = TaskState(
            task_id="test_007",
            task_type=TaskType.NORMALIZE,
            status=TaskStatus.PAUSED,
            total_items=3,
            completed_paths=["/path/to/file1.mp3"],
            pending_paths=["/path/to/file2.mp3", "/path/to/file3.mp3"],
            failed_paths={},
            config={"target_lufs": -14.0, "workers": 4},
            results=[{"path": "/path/to/file1.mp3", "lufs": -13.5}],
        )

        data = original.to_dict()
        restored = TaskState.from_dict(data)

        assert restored.task_id == original.task_id
        assert restored.task_type == original.task_type
        assert restored.status == original.status
        assert restored.total_items == original.total_items
        assert restored.completed_paths == original.completed_paths
        assert restored.pending_paths == original.pending_paths
        assert restored.config == original.config
        assert restored.results == original.results

    def test_to_json_and_from_json(self):
        """Test JSON serialization and deserialization."""
        original = TaskState(
            task_id="test_008",
            task_type=TaskType.MEASURE,
            status=TaskStatus.RUNNING,
            total_items=2,
            pending_paths=["/path/to/file1.mp3"],
            completed_paths=["/path/to/file2.mp3"],
        )

        json_str = original.to_json()
        assert isinstance(json_str, str)
        assert "test_008" in json_str

        restored = TaskState.from_json(json_str)
        assert restored.task_id == original.task_id
        assert restored.task_type == original.task_type


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create a temporary directory for checkpoints."""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_checkpoint_dir):
        """Create a checkpoint manager with temp directory."""
        return CheckpointManager(checkpoint_dir=temp_checkpoint_dir)

    def test_ensure_dir(self, manager, temp_checkpoint_dir):
        """Test that ensure_dir creates the directory."""
        # Remove the directory first
        if temp_checkpoint_dir.exists():
            temp_checkpoint_dir.rmdir()

        path = manager.ensure_dir()
        assert path.exists()
        assert path == temp_checkpoint_dir

    def test_create_task(self, manager):
        """Test creating a new task."""
        paths = ["/path/to/file1.mp3", "/path/to/file2.mp3"]
        config = {"target_lufs": -14.0}

        state = manager.create_task(TaskType.NORMALIZE, paths, config)

        assert state.task_type == TaskType.NORMALIZE
        assert state.total_items == 2
        assert state.pending_paths == paths
        assert state.config == config
        assert "normalize_" in state.task_id

    def test_save_and_load(self, manager):
        """Test saving and loading a checkpoint."""
        state = manager.create_task(
            TaskType.NORMALIZE,
            ["/path/to/file1.mp3", "/path/to/file2.mp3"],
            {"target_lufs": -14.0},
        )
        state.status = TaskStatus.RUNNING

        # Save
        checkpoint_path = manager.save(state)
        assert checkpoint_path.exists()

        # Load
        loaded = manager.load(state.task_id)
        assert loaded is not None
        assert loaded.task_id == state.task_id
        assert loaded.task_type == state.task_type
        assert loaded.pending_paths == state.pending_paths

    def test_load_nonexistent(self, manager):
        """Test loading a non-existent checkpoint returns None."""
        result = manager.load("nonexistent_task_id")
        assert result is None

    def test_delete(self, manager):
        """Test deleting a checkpoint."""
        state = manager.create_task(TaskType.NORMALIZE, ["/path/to/file.mp3"])
        manager.save(state)

        # Verify it exists
        assert manager.load(state.task_id) is not None

        # Delete
        result = manager.delete(state.task_id)
        assert result is True

        # Verify it's gone
        assert manager.load(state.task_id) is None

    def test_delete_nonexistent(self, manager):
        """Test deleting a non-existent checkpoint returns False."""
        result = manager.delete("nonexistent_task_id")
        assert result is False

    def test_list_checkpoints(self, manager):
        """Test listing all checkpoints."""
        # Create and save several tasks
        state1 = manager.create_task(TaskType.NORMALIZE, ["/path/to/file1.mp3"])
        state2 = manager.create_task(TaskType.MEASURE, ["/path/to/file2.mp3"])
        state3 = manager.create_task(TaskType.ANALYZE_ENERGY, ["/path/to/file3.mp3"])

        manager.save(state1)
        manager.save(state2)
        manager.save(state3)

        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) == 3

        # Check they're sorted by updated_at descending
        task_ids = [cp.task_id for cp in checkpoints]
        assert state3.task_id == task_ids[0]  # Most recent first

    def test_list_resumable(self, manager):
        """Test listing only resumable checkpoints."""
        # Create tasks with different statuses
        state1 = manager.create_task(TaskType.NORMALIZE, ["/path/to/file1.mp3"])
        state1.status = TaskStatus.PAUSED

        state2 = manager.create_task(TaskType.MEASURE, ["/path/to/file2.mp3"])
        state2.status = TaskStatus.COMPLETED

        state3 = manager.create_task(TaskType.ANALYZE_ENERGY, ["/path/to/file3.mp3"])
        state3.status = TaskStatus.RUNNING

        manager.save(state1)
        manager.save(state2)
        manager.save(state3)

        resumable = manager.list_resumable()
        assert len(resumable) == 2  # state1 (paused) and state3 (running)

        task_ids = [cp.task_id for cp in resumable]
        assert state1.task_id in task_ids
        assert state3.task_id in task_ids
        assert state2.task_id not in task_ids  # Completed

    def test_list_incomplete(self, manager):
        """Test listing incomplete checkpoints."""
        # Create tasks with different statuses
        state1 = manager.create_task(TaskType.NORMALIZE, ["/path/to/file1.mp3"])
        state1.status = TaskStatus.PAUSED

        state2 = manager.create_task(TaskType.MEASURE, ["/path/to/file2.mp3"])
        state2.status = TaskStatus.COMPLETED

        state3 = manager.create_task(TaskType.ANALYZE_ENERGY, ["/path/to/file3.mp3"])
        state3.status = TaskStatus.PENDING

        manager.save(state1)
        manager.save(state2)
        manager.save(state3)

        incomplete = manager.list_incomplete()
        assert len(incomplete) == 2  # state1 (paused) and state3 (pending)

    def test_cleanup_completed(self, manager):
        """Test cleaning up old completed checkpoints."""
        # Create an old completed task
        state1 = manager.create_task(TaskType.NORMALIZE, ["/path/to/file1.mp3"])
        state1.status = TaskStatus.COMPLETED
        state1.updated_at = datetime.now() - timedelta(days=10)
        manager.save(state1, update_timestamp=False)

        # Create a recent completed task
        state2 = manager.create_task(TaskType.MEASURE, ["/path/to/file2.mp3"])
        state2.status = TaskStatus.COMPLETED
        manager.save(state2)

        # Create an old but incomplete task
        state3 = manager.create_task(TaskType.ANALYZE_ENERGY, ["/path/to/file3.mp3"])
        state3.status = TaskStatus.PAUSED
        state3.updated_at = datetime.now() - timedelta(days=10)
        manager.save(state3, update_timestamp=False)

        # Cleanup
        deleted = manager.cleanup_completed(max_age_days=7)
        assert deleted == 1  # Only state1 should be deleted

        # Verify
        checkpoints = manager.list_checkpoints()
        task_ids = [cp.task_id for cp in checkpoints]
        assert state1.task_id not in task_ids
        assert state2.task_id in task_ids
        assert state3.task_id in task_ids  # Incomplete, not deleted

    def test_iter_checkpoints(self, manager):
        """Test iterating over checkpoints."""
        state1 = manager.create_task(TaskType.NORMALIZE, ["/path/to/file1.mp3"])
        state2 = manager.create_task(TaskType.MEASURE, ["/path/to/file2.mp3"])

        manager.save(state1)
        manager.save(state2)

        task_ids = [cp.task_id for cp in manager.iter_checkpoints()]
        assert len(task_ids) == 2
        assert state1.task_id in task_ids
        assert state2.task_id in task_ids

    def test_resume_workflow(self, manager):
        """Test a complete pause/resume workflow."""
        paths = ["/path/to/file1.mp3", "/path/to/file2.mp3", "/path/to/file3.mp3"]

        # Create and start task
        state = manager.create_task(TaskType.NORMALIZE, paths, {"target_lufs": -14.0})
        state.status = TaskStatus.RUNNING
        manager.save(state)

        # Process first file
        state.mark_completed("/path/to/file1.mp3", {"lufs": -14.0})
        manager.save(state)

        # Pause mid-process
        state.status = TaskStatus.PAUSED
        manager.save(state)

        # Simulate application restart - load from checkpoint
        loaded = manager.load(state.task_id)
        assert loaded is not None
        assert loaded.is_resumable
        assert loaded.progress_percent == pytest.approx(33.33, rel=0.01)
        assert len(loaded.pending_paths) == 2

        # Resume
        loaded.status = TaskStatus.RUNNING
        manager.save(loaded)

        # Process remaining files
        loaded.mark_completed("/path/to/file2.mp3", {"lufs": -13.8})
        loaded.mark_completed("/path/to/file3.mp3", {"lufs": -14.2})
        loaded.status = TaskStatus.COMPLETED
        manager.save(loaded)

        # Verify final state
        final = manager.load(state.task_id)
        assert final.is_complete
        assert final.progress_percent == 100.0
        assert len(final.results) == 3
