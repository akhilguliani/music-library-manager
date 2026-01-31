"""Task state dataclass for checkpoint persistence."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any
import json


class TaskType(str, Enum):
    """Types of long-running tasks that support checkpointing."""

    NORMALIZE = "normalize"
    MEASURE = "measure"
    ANALYZE_ENERGY = "analyze_energy"
    ANALYZE_MOOD = "analyze_mood"


class TaskStatus(str, Enum):
    """Status of a checkpointed task."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class TaskState:
    """State of a long-running task for checkpoint persistence.

    This class tracks the progress of batch operations like normalization,
    allowing them to be paused and resumed across application restarts.

    Attributes:
        task_id: Unique identifier for this task.
        task_type: Type of operation (normalize, measure, etc.).
        status: Current status of the task.
        total_items: Total number of items to process.
        completed_paths: List of file paths that have been processed.
        pending_paths: List of file paths still waiting to be processed.
        failed_paths: Dict mapping failed paths to error messages.
        config: Task-specific configuration (target LUFS, workers, etc.).
        results: List of serialized result dictionaries.
        created_at: When the task was created.
        updated_at: When the task was last updated.
    """

    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING

    total_items: int = 0
    completed_paths: list[str] = field(default_factory=list)
    pending_paths: list[str] = field(default_factory=list)
    failed_paths: dict[str, str] = field(default_factory=dict)

    config: dict[str, Any] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def processed_count(self) -> int:
        """Number of items processed (completed + failed)."""
        return len(self.completed_paths) + len(self.failed_paths)

    @property
    def progress_percent(self) -> float:
        """Progress as a percentage (0-100)."""
        if self.total_items == 0:
            return 0.0
        return (self.processed_count / self.total_items) * 100.0

    @property
    def is_resumable(self) -> bool:
        """Check if this task can be resumed."""
        return self.status in (TaskStatus.PAUSED, TaskStatus.RUNNING) and len(
            self.pending_paths
        ) > 0

    @property
    def is_complete(self) -> bool:
        """Check if this task has finished (successfully or not)."""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        )

    def mark_completed(self, path: str, result: dict[str, Any] | None = None) -> None:
        """Mark a path as successfully completed.

        Args:
            path: File path that was processed.
            result: Optional result data to store.
        """
        if path in self.pending_paths:
            self.pending_paths.remove(path)
        if path not in self.completed_paths:
            self.completed_paths.append(path)
        if result is not None:
            self.results.append(result)
        self.updated_at = datetime.now()

    def mark_failed(self, path: str, error: str) -> None:
        """Mark a path as failed.

        Args:
            path: File path that failed.
            error: Error message describing the failure.
        """
        if path in self.pending_paths:
            self.pending_paths.remove(path)
        self.failed_paths[path] = error
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "total_items": self.total_items,
            "completed_paths": self.completed_paths,
            "pending_paths": self.pending_paths,
            "failed_paths": self.failed_paths,
            "config": self.config,
            "results": self.results,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskState":
        """Create a TaskState from a dictionary.

        Args:
            data: Dictionary representation (from JSON).

        Returns:
            TaskState instance.
        """
        return cls(
            task_id=data["task_id"],
            task_type=TaskType(data["task_type"]),
            status=TaskStatus(data["status"]),
            total_items=data["total_items"],
            completed_paths=data["completed_paths"],
            pending_paths=data["pending_paths"],
            failed_paths=data["failed_paths"],
            config=data["config"],
            results=data["results"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    def to_json(self) -> str:
        """Serialize to JSON string.

        Returns:
            JSON string representation.
        """
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "TaskState":
        """Create a TaskState from a JSON string.

        Args:
            json_str: JSON string representation.

        Returns:
            TaskState instance.
        """
        return cls.from_dict(json.loads(json_str))
