"""SQLite-backed cache for loudness measurements.

Persists LUFS measurements across sessions so files don't need to be
re-analyzed by ffmpeg when they haven't changed. Measurements are keyed
by (file_path, target_lufs) and automatically invalidated when the
file's mtime or size changes on disk.
"""

import contextlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

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

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_CACHE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the measurements table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextlib.contextmanager
    def _connect(self):
        """Open a connection with WAL mode, auto-close on exit.

        Using a contextmanager ensures the connection is always closed,
        preventing file descriptor leaks in long-running ProcessPoolExecutor
        workers that process thousands of files.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, file_path: str, target_lufs: float) -> dict | None:
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

    def get_batch(self, file_paths: list[str], target_lufs: float) -> dict[str, dict]:
        """Look up cached measurements for multiple files.

        Uses a single ``WHERE IN`` query instead of N individual lookups,
        then validates mtime/size against the filesystem.

        Args:
            file_paths: List of absolute file paths.
            target_lufs: The target LUFS.

        Returns:
            Dict mapping file_path → result dict for cache hits only.
        """
        if not file_paths:
            return {}

        hits: dict[str, dict] = {}
        placeholders = ",".join("?" * len(file_paths))
        params: list = list(file_paths) + [target_lufs]

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT file_path, mtime, file_size, "
                f"integrated_lufs, true_peak, lra, threshold, gain_db "
                f"FROM measurements "
                f"WHERE file_path IN ({placeholders}) AND target_lufs = ?",
                params,
            ).fetchall()

        for row in rows:
            fp = row["file_path"]
            try:
                stat = os.stat(fp)
            except OSError:
                continue
            if row["mtime"] != stat.st_mtime or row["file_size"] != stat.st_size:
                continue
            hits[fp] = {
                "integrated_lufs": row["integrated_lufs"],
                "true_peak": row["true_peak"],
                "lra": row["lra"],
                "threshold": row["threshold"],
                "gain_db": row["gain_db"],
            }

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
