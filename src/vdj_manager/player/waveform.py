"""Waveform peak data generation and SQLite caching.

Uses librosa (already a dependency) for peak extraction. Results are
cached in ~/.vdj_manager/waveforms.db so waveforms only need to be
computed once per file.
"""

import contextlib
import os
import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np

from ..config import CHECKPOINT_DIR

DEFAULT_WAVEFORM_CACHE_PATH = Path(CHECKPOINT_DIR).parent / "waveforms.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS waveform_peaks (
    file_path   TEXT    NOT NULL,
    width       INTEGER NOT NULL,
    mtime       REAL    NOT NULL,
    file_size   INTEGER NOT NULL,
    peaks_blob  BLOB    NOT NULL,
    PRIMARY KEY (file_path, width)
)
"""


class WaveformCache:
    """SQLite cache for waveform peak arrays.

    Follows the same contextmanager pattern as AnalysisCache and
    MeasurementCache to prevent file descriptor leaks.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_WAVEFORM_CACHE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextlib.contextmanager
    def _connect(self):
        """Open a connection with WAL mode, auto-close on exit."""
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

    def get(self, file_path: str, width: int = 800) -> Optional[np.ndarray]:
        """Retrieve cached waveform peaks if file hasn't changed.

        Returns None on cache miss or stale entry.
        """
        try:
            stat = os.stat(file_path)
        except OSError:
            return None

        with self._connect() as conn:
            row = conn.execute(
                "SELECT peaks_blob, mtime, file_size FROM waveform_peaks "
                "WHERE file_path = ? AND width = ?",
                (file_path, width),
            ).fetchone()

        if row is None:
            return None

        # Invalidate if file changed
        if abs(row["mtime"] - stat.st_mtime) > 0.01 or row["file_size"] != stat.st_size:
            return None

        return np.frombuffer(row["peaks_blob"], dtype=np.float64)

    def put(self, file_path: str, peaks: np.ndarray, width: int = 800) -> None:
        """Store waveform peaks in cache."""
        try:
            stat = os.stat(file_path)
        except OSError:
            return

        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO waveform_peaks "
                "(file_path, width, mtime, file_size, peaks_blob) "
                "VALUES (?, ?, ?, ?, ?)",
                (file_path, width, stat.st_mtime, stat.st_size, peaks.tobytes()),
            )


def generate_waveform_peaks(
    file_path: str,
    target_width: int = 800,
    sr: int = 22050,
) -> np.ndarray:
    """Generate waveform peak data using librosa.

    Args:
        file_path: Path to audio file.
        target_width: Number of peak bins (pixels).
        sr: Sample rate for loading (lower = faster).

    Returns:
        1D numpy array of peak amplitudes (0.0-1.0), length = target_width.
    """
    import librosa

    y, _ = librosa.load(file_path, sr=sr, mono=True)

    if len(y) == 0:
        return np.zeros(target_width)

    bin_size = max(1, len(y) // target_width)
    peaks = []
    for i in range(0, len(y), bin_size):
        chunk = y[i : i + bin_size]
        peaks.append(float(np.max(np.abs(chunk))))

    # Trim or pad to exact target_width
    peaks_array = np.array(peaks[:target_width])
    if len(peaks_array) < target_width:
        peaks_array = np.pad(peaks_array, (0, target_width - len(peaks_array)))

    # Normalize to 0-1
    peak_max = peaks_array.max()
    if peak_max > 0:
        peaks_array = peaks_array / peak_max

    return peaks_array
