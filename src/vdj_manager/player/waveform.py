"""Waveform peak data generation and SQLite caching.

Uses librosa (already a dependency) for peak extraction. Results are
cached in ~/.vdj_manager/waveforms.db so waveforms only need to be
computed once per file.
"""

import contextlib
import os
import sqlite3
from pathlib import Path

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

    def __init__(self, db_path: Path | None = None) -> None:
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

    def get(self, file_path: str, width: int = 800) -> np.ndarray | None:
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
    """Generate waveform peak data from an audio file.

    Tries soundfile first (handles WAV/FLAC/OGG/AIFF natively without
    subprocess spawning). Falls back to librosa for MP3/M4A and other
    compressed formats that soundfile cannot read.

    Args:
        file_path: Path to audio file.
        target_width: Number of peak bins (pixels).
        sr: Sample rate for loading (lower = faster).

    Returns:
        1D numpy array of peak amplitudes (0.0-1.0), length = target_width.
    """
    import soundfile as sf

    try:
        data, file_sr = sf.read(file_path, dtype="float32", always_2d=True)
        y = data.mean(axis=1)  # mono mixdown
        if file_sr != sr:
            import librosa

            y = librosa.resample(y, orig_sr=file_sr, target_sr=sr)
    except (RuntimeError, OSError):
        # soundfile can't decode this format (MP3/M4A) — try ffmpeg pipe
        import subprocess

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    file_path,
                    "-f",
                    "wav",
                    "-ac",
                    "1",
                    "-ar",
                    str(sr),
                    "-loglevel",
                    "error",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and len(result.stdout) > 44:
                import io

                data, _ = sf.read(io.BytesIO(result.stdout), dtype="float32")
                y = data if data.ndim == 1 else data.mean(axis=1)
            else:
                raise RuntimeError("ffmpeg decode failed")
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            # Final fallback: librosa (may trigger audioread deprecation)
            import librosa

            y, _ = librosa.load(file_path, sr=sr, mono=True)

    if len(y) == 0:
        return np.zeros(target_width)

    bin_size = max(1, len(y) // target_width)
    n_bins = min(target_width, len(y) // bin_size)

    # Vectorized: reshape into (n_bins, bin_size) and take max(abs) per row
    if n_bins > 0:
        peaks_array = np.abs(y[: n_bins * bin_size].reshape(n_bins, bin_size)).max(axis=1)
    else:
        peaks_array = np.array([], dtype=y.dtype)

    # Pad to exact target_width if needed
    if len(peaks_array) < target_width:
        peaks_array = np.pad(peaks_array, (0, target_width - len(peaks_array)))

    # Normalize to 0-1
    peak_max = peaks_array.max()
    if peak_max > 0:
        peaks_array = peaks_array / peak_max

    return peaks_array
