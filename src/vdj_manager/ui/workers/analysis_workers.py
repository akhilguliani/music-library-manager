"""Workers for audio analysis operations with parallel processing."""

import contextlib
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.ui.workers.base_worker import ProgressSimpleWorker

# Save to disk every N results to avoid losing work on crash
_SAVE_INTERVAL = 25


# ------------------------------------------------------------------
# Top-level worker functions (required for ProcessPoolExecutor pickling)
# ------------------------------------------------------------------

@contextlib.contextmanager
def _suppress_stderr():
    """Suppress C-level stderr output (e.g. mpg123 decoder warnings).

    Redirects file descriptor 2 to /dev/null temporarily. This is
    necessary because libraries like mpg123 write warnings about
    corrupted MPEG headers directly to stderr at the C level, bypassing
    Python's sys.stderr.
    """
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        yield
    except OSError:
        yield  # If redirection fails, run without suppression
    else:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)


def _analyze_energy_single(file_path: str, cache_db_path: str | None = None) -> dict:
    """Analyze energy for a single file in a subprocess.

    Returns:
        Dict with file_path, format, energy (int|None), and status.
    """
    fmt = Path(file_path).suffix.lower()
    try:
        # Check cache first
        if cache_db_path:
            from vdj_manager.analysis.analysis_cache import AnalysisCache
            cache = AnalysisCache(db_path=Path(cache_db_path))
            cached = cache.get(file_path, "energy")
            if cached is not None:
                return {"file_path": file_path, "format": fmt, "energy": int(cached), "status": "cached"}

        from vdj_manager.analysis.energy import EnergyAnalyzer

        analyzer = EnergyAnalyzer()
        with _suppress_stderr():
            energy = analyzer.analyze(file_path)
        if energy is not None:
            # Store in cache
            if cache_db_path:
                from vdj_manager.analysis.analysis_cache import AnalysisCache
                cache = AnalysisCache(db_path=Path(cache_db_path))
                cache.put(file_path, "energy", str(energy))
            return {"file_path": file_path, "format": fmt, "energy": energy, "status": "ok"}
        return {"file_path": file_path, "format": fmt, "energy": None, "status": "failed"}
    except Exception as e:
        return {"file_path": file_path, "format": fmt, "energy": None, "status": f"error: {e}"}


def _analyze_mood_single(file_path: str, cache_db_path: str | None = None) -> dict:
    """Analyze mood for a single file in a subprocess.

    Returns:
        Dict with file_path, format, mood (str|None), and status.
    """
    fmt = Path(file_path).suffix.lower()
    try:
        # Check cache first
        if cache_db_path:
            from vdj_manager.analysis.analysis_cache import AnalysisCache
            cache = AnalysisCache(db_path=Path(cache_db_path))
            cached = cache.get(file_path, "mood")
            if cached is not None:
                return {"file_path": file_path, "format": fmt, "mood": cached, "status": "cached"}

        from vdj_manager.analysis.mood import MoodAnalyzer

        analyzer = MoodAnalyzer()
        with _suppress_stderr():
            mood_tag = analyzer.get_mood_tag(file_path)
        if mood_tag:
            # Store in cache
            if cache_db_path:
                from vdj_manager.analysis.analysis_cache import AnalysisCache
                cache = AnalysisCache(db_path=Path(cache_db_path))
                cache.put(file_path, "mood", mood_tag)
            return {"file_path": file_path, "format": fmt, "mood": mood_tag, "status": "ok"}
        return {"file_path": file_path, "format": fmt, "mood": None, "status": "failed"}
    except Exception as e:
        return {"file_path": file_path, "format": fmt, "mood": None, "status": f"error: {e}"}


def _import_mik_single(file_path: str, cache_db_path: str | None = None) -> dict:
    """Import MIK tags for a single file in a subprocess.

    Returns:
        Dict with file_path, format, energy, key, and status.
    """
    fmt = Path(file_path).suffix.lower()
    try:
        # Check cache first
        if cache_db_path:
            from vdj_manager.analysis.analysis_cache import AnalysisCache
            cache = AnalysisCache(db_path=Path(cache_db_path))
            cached = cache.get(file_path, "mik")
            if cached is not None:
                # cached format: "energy:key" e.g. "8:Am" or ":Am" or "8:"
                parts = cached.split(":", 1)
                energy = int(parts[0]) if parts[0] else None
                key = parts[1] if len(parts) > 1 and parts[1] else None
                if energy or key:
                    return {
                        "file_path": file_path,
                        "format": fmt,
                        "energy": energy,
                        "key": key,
                        "status": "cached",
                    }

        from vdj_manager.analysis.audio_features import MixedInKeyReader

        reader = MixedInKeyReader()
        mik_data = reader.read_tags(file_path)
        if mik_data.get("energy") or mik_data.get("key"):
            # Store in cache
            if cache_db_path:
                from vdj_manager.analysis.analysis_cache import AnalysisCache
                cache = AnalysisCache(db_path=Path(cache_db_path))
                energy_str = str(mik_data.get("energy") or "")
                key_str = mik_data.get("key") or ""
                cache.put(file_path, "mik", f"{energy_str}:{key_str}")
            return {
                "file_path": file_path,
                "format": fmt,
                "energy": mik_data.get("energy"),
                "key": mik_data.get("key"),
                "status": "found",
            }
        return {"file_path": file_path, "format": fmt, "energy": None, "key": None, "status": "none"}
    except Exception:
        return {"file_path": file_path, "format": fmt, "status": "error"}


# ------------------------------------------------------------------
# Worker classes
# ------------------------------------------------------------------

class EnergyWorker(ProgressSimpleWorker):
    """Worker that analyzes energy levels for audio tracks in parallel.

    Uses ProcessPoolExecutor to analyze multiple files simultaneously,
    streaming results to the GUI and saving periodically.
    """

    result_ready = Signal(dict)

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        max_workers: int | None = None,
        cache_db_path: str | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self._cache_db_path = cache_db_path

    def do_work(self) -> dict:
        """Analyze energy for all tracks in parallel.

        Returns:
            Dict with analyzed count, failed count, cached count, and results list.
        """
        analyzed = 0
        failed = 0
        cached = 0
        results = []
        total = len(self._tracks)
        unsaved = 0

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(_analyze_energy_single, fp, self._cache_db_path): fp
                for fp in file_paths
            }

            for future in as_completed(futures):
                if self.is_cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                result = future.result()
                results.append(result)

                if result["status"] == "cached" and result["energy"] is not None:
                    self._database.update_song_tags(
                        result["file_path"],
                        Grouping=str(result["energy"]),
                    )
                    cached += 1
                    unsaved += 1
                elif result["status"] == "ok" and result["energy"] is not None:
                    self._database.update_song_tags(
                        result["file_path"],
                        Grouping=str(result["energy"]),
                    )
                    analyzed += 1
                    unsaved += 1
                else:
                    failed += 1

                self.result_ready.emit(result)
                self.report_progress(analyzed + failed + cached, total, result["file_path"])

                if unsaved >= _SAVE_INTERVAL:
                    self._database.save()
                    unsaved = 0

        if unsaved > 0:
            self._database.save()

        return {"analyzed": analyzed, "failed": failed, "cached": cached, "results": results}


class MIKImportWorker(ProgressSimpleWorker):
    """Worker that imports Mixed In Key tags from audio files in parallel.

    Reads MIK energy and key data from file tags using ProcessPoolExecutor
    and updates the VDJ database.
    """

    result_ready = Signal(dict)

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        max_workers: int | None = None,
        cache_db_path: str | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self._cache_db_path = cache_db_path

    def do_work(self) -> dict:
        """Import MIK tags for all tracks in parallel.

        Returns:
            Dict with found count, updated count, and results list.
        """
        found = 0
        updated = 0
        results = []
        total = len(self._tracks)
        unsaved = 0

        # Build a lookup for existing energy tags
        existing_energy = {
            t.file_path: t.energy for t in self._tracks
        }

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(_import_mik_single, fp, self._cache_db_path): fp
                for fp in file_paths
            }

            for future in as_completed(futures):
                if self.is_cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                result = future.result()

                if result["status"] in ("found", "cached"):
                    found += 1
                    updates = {}
                    if result.get("energy") and not existing_energy.get(result["file_path"]):
                        updates["Grouping"] = str(result["energy"])
                    if result.get("key"):
                        updates["Key"] = result["key"]
                    if updates:
                        self._database.update_song_tags(result["file_path"], **updates)
                        updated += 1
                        unsaved += 1
                        result["status"] = "updated"
                    else:
                        result["status"] = "exists"

                results.append(result)
                self.result_ready.emit(result)
                self.report_progress(len(results), total, result["file_path"])

                if unsaved >= _SAVE_INTERVAL:
                    self._database.save()
                    unsaved = 0

        if unsaved > 0:
            self._database.save()

        return {"found": found, "updated": updated, "results": results}


class MoodWorker(ProgressSimpleWorker):
    """Worker that analyzes mood/emotion for audio tracks in parallel.

    Uses MoodAnalyzer (requires essentia-tensorflow) with ProcessPoolExecutor
    to classify audio mood and stores results in the User2 hashtag field.
    """

    result_ready = Signal(dict)

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        max_workers: int | None = None,
        cache_db_path: str | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self._cache_db_path = cache_db_path

    def do_work(self) -> dict:
        """Analyze mood for all tracks in parallel.

        Returns:
            Dict with analyzed count, failed count, cached count, and results list.
        """
        # Check availability before spawning workers
        from vdj_manager.analysis.mood import MoodAnalyzer

        analyzer = MoodAnalyzer()
        if not analyzer.is_available:
            return {
                "analyzed": 0,
                "failed": 0,
                "cached": 0,
                "results": [],
                "error": "essentia-tensorflow is not installed",
            }

        analyzed = 0
        failed = 0
        cached = 0
        results = []
        total = len(self._tracks)
        unsaved = 0

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(_analyze_mood_single, fp, self._cache_db_path): fp
                for fp in file_paths
            }

            for future in as_completed(futures):
                if self.is_cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                result = future.result()
                results.append(result)

                if result.get("mood") and result["status"] in ("ok", "cached"):
                    mood_hashtag = f"#{result['mood']}"
                    # Append mood hashtag to existing User2 value
                    song = self._database.get_song(result["file_path"])
                    existing = (song.tags.user2 or "") if song and song.tags else ""
                    if mood_hashtag not in existing.split():
                        new_user2 = f"{existing} {mood_hashtag}".strip()
                    else:
                        new_user2 = existing
                    self._database.update_song_tags(
                        result["file_path"], User2=new_user2
                    )
                    if result["status"] == "cached":
                        cached += 1
                    else:
                        analyzed += 1
                    unsaved += 1
                else:
                    failed += 1

                self.result_ready.emit(result)
                self.report_progress(analyzed + failed + cached, total, result["file_path"])

                if unsaved >= _SAVE_INTERVAL:
                    self._database.save()
                    unsaved = 0

        if unsaved > 0:
            self._database.save()

        return {"analyzed": analyzed, "failed": failed, "cached": cached, "results": results}
