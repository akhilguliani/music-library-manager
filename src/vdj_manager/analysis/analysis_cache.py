"""SQLite-backed cache for analysis results.

Persists energy, mood, and MIK analysis results across sessions so files
don't need to be re-analyzed when they haven't changed. Results are keyed
by (file_path, analysis_type) and automatically invalidated when the
file's mtime or size changes on disk.
"""

import contextlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import CHECKPOINT_DIR

# Default location alongside other persisted state
DEFAULT_ANALYSIS_CACHE_PATH = Path(CHECKPOINT_DIR).parent / "analysis.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_results (
    file_path      TEXT    NOT NULL,
    analysis_type  TEXT    NOT NULL,
    mtime          REAL    NOT NULL,
    file_size      INTEGER NOT NULL,
    result_value   TEXT,
    analyzed_at    TEXT    NOT NULL,
    PRIMARY KEY (file_path, analysis_type)
)
"""


class AnalysisCache:
    """Persistent cache of audio analysis results.

    Stores analysis results in a SQLite database so that subsequent runs
    can skip expensive analysis for files that haven't been modified.

    Args:
        db_path: Path to the SQLite database file.
                 Defaults to ``~/.vdj_manager/analysis.db``.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_ANALYSIS_CACHE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the analysis_results table if it doesn't exist."""
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

    def get(self, file_path: str, analysis_type: str) -> Optional[str]:
        """Look up a cached analysis result.

        Returns the cached result value if the file has not been modified
        (same mtime and size), otherwise ``None``.

        Args:
            file_path: Absolute path to the audio file.
            analysis_type: Type of analysis (e.g. "energy", "mood", "mik").

        Returns:
            The result value string, or ``None`` on cache miss.
        """
        try:
            stat = os.stat(file_path)
        except OSError:
            return None

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_results "
                "WHERE file_path = ? AND analysis_type = ?",
                (file_path, analysis_type),
            ).fetchone()

        if row is None:
            return None

        # Invalidate if file changed
        if row["mtime"] != stat.st_mtime or row["file_size"] != stat.st_size:
            return None

        return row["result_value"]

    def put(
        self,
        file_path: str,
        analysis_type: str,
        result_value: str,
    ) -> None:
        """Store an analysis result.

        Overwrites any existing entry for the same ``(file_path, analysis_type)``.

        Args:
            file_path: Absolute path to the audio file.
            analysis_type: Type of analysis (e.g. "energy", "mood", "mik").
            result_value: The analysis result to cache.
        """
        try:
            stat = os.stat(file_path)
        except OSError:
            return  # Can't cache if file doesn't exist

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO analysis_results
                    (file_path, analysis_type, mtime, file_size,
                     result_value, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    file_path,
                    analysis_type,
                    stat.st_mtime,
                    stat.st_size,
                    result_value,
                    datetime.now().isoformat(),
                ),
            )

    def get_batch(
        self, file_paths: list[str], analysis_type: str
    ) -> dict[str, str]:
        """Look up cached results for multiple files.

        Args:
            file_paths: List of absolute file paths.
            analysis_type: Type of analysis.

        Returns:
            Dict mapping file_path → result_value for cache hits only.
        """
        hits: dict[str, str] = {}
        for path in file_paths:
            result = self.get(path, analysis_type)
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
                "DELETE FROM analysis_results WHERE file_path = ?",
                (file_path,),
            )

    def clear(self) -> None:
        """Remove all cached analysis results."""
        with self._connect() as conn:
            conn.execute("DELETE FROM analysis_results")

    def stats(self) -> dict:
        """Return cache statistics.

        Returns:
            Dict with ``count`` (number of entries) and
            ``db_size_bytes`` (file size on disk).
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM analysis_results"
            ).fetchone()
            count = row["cnt"] if row else 0

        try:
            db_size = self.db_path.stat().st_size
        except OSError:
            db_size = 0

        return {"count": count, "db_size_bytes": db_size}
