"""SQLite-backed cache for loudness measurements.

Persists LUFS measurements across sessions so files don't need to be
re-analyzed by ffmpeg when they haven't changed. Measurements are keyed
by (file_path, target_lufs) and automatically invalidated when the
file's mtime or size changes on disk.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import CHECKPOINT_DIR

# Default location alongside other persisted state
DEFAULT_CACHE_PATH = Path(CHECKPOINT_DIR).parent / "measurements.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    file_path   TEXT    NOT NULL,
    target_lufs REAL    NOT NULL,
    mtime       REAL    NOT NULL,
    file_size   INTEGER NOT NULL,
    integrated_lufs REAL,
    true_peak   REAL,
    lra         REAL,
    threshold   REAL,
    gain_db     REAL,
    measured_at TEXT    NOT NULL,
    PRIMARY KEY (file_path, target_lufs)
)
"""


class MeasurementCache:
    """Persistent cache of LUFS loudness measurements.

    Stores measurements in a SQLite database so that subsequent runs
    can skip ffmpeg for files that haven't been modified.

    Args:
        db_path: Path to the SQLite database file.
                 Defaults to ``~/.vdj_manager/measurements.db``.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_CACHE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the measurements table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with WAL mode for concurrent-read safety."""
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, file_path: str, target_lufs: float) -> Optional[dict]:
        """Look up a cached measurement.

        Returns the cached result dict if the file has not been modified
        (same mtime and size), otherwise ``None``.

        Args:
            file_path: Absolute path to the audio file.
            target_lufs: The target LUFS the measurement was made against.

        Returns:
            A dict with keys ``integrated_lufs``, ``true_peak``, ``lra``,
            ``threshold``, ``gain_db``; or ``None`` on cache miss.
        """
        try:
            stat = os.stat(file_path)
        except OSError:
            return None

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM measurements WHERE file_path = ? AND target_lufs = ?",
                (file_path, target_lufs),
            ).fetchone()

        if row is None:
            return None

        # Invalidate if file changed
        if row["mtime"] != stat.st_mtime or row["file_size"] != stat.st_size:
            return None

        return {
            "integrated_lufs": row["integrated_lufs"],
            "true_peak": row["true_peak"],
            "lra": row["lra"],
            "threshold": row["threshold"],
            "gain_db": row["gain_db"],
        }

    def put(
        self,
        file_path: str,
        target_lufs: float,
        result: dict,
    ) -> None:
        """Store a measurement result.

        Overwrites any existing entry for the same ``(file_path, target_lufs)``.

        Args:
            file_path: Absolute path to the audio file.
            target_lufs: The target LUFS the measurement was made against.
            result: Dict containing measurement data. Expected keys:
                    ``integrated_lufs``, ``gain_db``, and optionally
                    ``true_peak``, ``lra``, ``threshold``.
        """
        try:
            stat = os.stat(file_path)
        except OSError:
            return  # Can't cache if file doesn't exist

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO measurements
                    (file_path, target_lufs, mtime, file_size,
                     integrated_lufs, true_peak, lra, threshold,
                     gain_db, measured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_path,
                    target_lufs,
                    stat.st_mtime,
                    stat.st_size,
                    result.get("integrated_lufs"),
                    result.get("true_peak"),
                    result.get("lra"),
                    result.get("threshold"),
                    result.get("gain_db"),
                    datetime.now().isoformat(),
                ),
            )

    def get_batch(
        self, file_paths: list[str], target_lufs: float
    ) -> dict[str, dict]:
        """Look up cached measurements for multiple files.

        Args:
            file_paths: List of absolute file paths.
            target_lufs: The target LUFS.

        Returns:
            Dict mapping file_path → result dict for cache hits only.
        """
        hits: dict[str, dict] = {}
        for path in file_paths:
            result = self.get(path, target_lufs)
            if result is not None:
                hits[path] = result
        return hits

    def invalidate(self, file_path: str) -> None:
        """Remove all cached entries for a file path.

        Args:
            file_path: Absolute path to invalidate.
        """
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM measurements WHERE file_path = ?",
                (file_path,),
            )

    def clear(self) -> None:
        """Remove all cached measurements."""
        with self._connect() as conn:
            conn.execute("DELETE FROM measurements")

    def stats(self) -> dict:
        """Return cache statistics.

        Returns:
            Dict with ``count`` (number of entries) and
            ``db_size_bytes`` (file size on disk).
        """
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM measurements").fetchone()
            count = row["cnt"] if row else 0

        try:
            db_size = self.db_path.stat().st_size
        except OSError:
            db_size = 0

        return {"count": count, "db_size_bytes": db_size}
