"""Checkpoint manager for saving and loading task state."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterator

from vdj_manager.config import CHECKPOINT_DIR
from vdj_manager.ui.models.task_state import TaskState, TaskStatus, TaskType


class CheckpointManager:
    """Manages checkpoint files for pausable tasks.

    Checkpoints are saved as JSON files in the checkpoint directory,
    allowing tasks to be resumed after application restart.
    """

    def __init__(self, checkpoint_dir: Path | None = None) -> None:
        """Initialize the checkpoint manager.

        Args:
            checkpoint_dir: Directory to store checkpoints.
                           Defaults to CHECKPOINT_DIR from config.
        """
        self.checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR

    def ensure_dir(self) -> Path:
        """Ensure the checkpoint directory exists.

        Returns:
            Path to the checkpoint directory.
        """
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        return self.checkpoint_dir

    def _get_checkpoint_path(self, task_id: str) -> Path:
        """Get the file path for a checkpoint.

        Args:
            task_id: Unique task identifier.

        Returns:
            Path to the checkpoint file.
        """
        return self.checkpoint_dir / f"{task_id}.json"

    def create_task(
        self,
        task_type: TaskType,
        paths: list[str],
        config: dict | None = None,
    ) -> TaskState:
        """Create a new task state with a unique ID.

        Args:
            task_type: Type of task (normalize, measure, etc.).
            paths: List of file paths to process.
            config: Task-specific configuration.

        Returns:
            New TaskState instance with unique ID.
        """
        task_id = f"{task_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        return TaskState(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            total_items=len(paths),
            pending_paths=list(paths),
            config=config or {},
        )

    def save(self, state: TaskState, update_timestamp: bool = True) -> Path:
        """Save task state to a checkpoint file.

        Args:
            state: TaskState to save.
            update_timestamp: Whether to update the updated_at timestamp.
                            Set to False when preserving existing timestamps.

        Returns:
            Path to the saved checkpoint file.
        """
        self.ensure_dir()
        if update_timestamp:
            state.updated_at = datetime.now()

        checkpoint_path = self._get_checkpoint_path(state.task_id)
        checkpoint_path.write_text(state.to_json(), encoding="utf-8")

        return checkpoint_path

    def load(self, task_id: str) -> TaskState | None:
        """Load task state from a checkpoint file.

        Args:
            task_id: Unique task identifier.

        Returns:
            TaskState if found, None otherwise.
        """
        checkpoint_path = self._get_checkpoint_path(task_id)

        if not checkpoint_path.exists():
            return None

        try:
            json_str = checkpoint_path.read_text(encoding="utf-8")
            return TaskState.from_json(json_str)
        except (ValueError, KeyError) as e:
            # Invalid checkpoint file
            return None

    def delete(self, task_id: str) -> bool:
        """Delete a checkpoint file.

        Args:
            task_id: Unique task identifier.

        Returns:
            True if deleted, False if not found.
        """
        checkpoint_path = self._get_checkpoint_path(task_id)

        if checkpoint_path.exists():
            checkpoint_path.unlink()
            return True

        return False

    def list_checkpoints(self) -> list[TaskState]:
        """List all saved checkpoints.

        Returns:
            List of TaskState objects, sorted by updated_at descending.
        """
        if not self.checkpoint_dir.exists():
            return []

        checkpoints = []
        for path in self.checkpoint_dir.glob("*.json"):
            try:
                json_str = path.read_text(encoding="utf-8")
                state = TaskState.from_json(json_str)
                checkpoints.append(state)
            except (ValueError, KeyError):
                # Skip invalid checkpoint files
                continue

        # Sort by updated_at, most recent first
        checkpoints.sort(key=lambda s: s.updated_at, reverse=True)
        return checkpoints

    def list_resumable(self) -> list[TaskState]:
        """List checkpoints that can be resumed.

        Returns:
            List of resumable TaskState objects.
        """
        return [cp for cp in self.list_checkpoints() if cp.is_resumable]

    def list_incomplete(self) -> list[TaskState]:
        """List checkpoints that are not completed.

        This includes paused, running (crashed), and pending tasks.

        Returns:
            List of incomplete TaskState objects.
        """
        return [cp for cp in self.list_checkpoints() if not cp.is_complete]

    def cleanup_completed(self, max_age_days: int = 7) -> int:
        """Remove old completed checkpoints.

        Args:
            max_age_days: Delete completed checkpoints older than this.

        Returns:
            Number of checkpoints deleted.
        """
        if not self.checkpoint_dir.exists():
            return 0

        deleted = 0
        cutoff = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)

        for state in self.list_checkpoints():
            if state.is_complete and state.updated_at.timestamp() < cutoff:
                if self.delete(state.task_id):
                    deleted += 1

        return deleted

    def iter_checkpoints(self) -> Iterator[TaskState]:
        """Iterate over all checkpoints.

        Yields:
            TaskState objects.
        """
        yield from self.list_checkpoints()
