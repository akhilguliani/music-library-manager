"""Workers for audio analysis operations with parallel processing.

Supports pause/resume/cancel via PausableAnalysisWorker base class,
which processes futures in batches and pauses between them.
"""

import contextlib
import gc
import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from vdj_manager.core.models import Song

# Save to disk every N results to avoid losing work on crash
_SAVE_INTERVAL = 25


# ------------------------------------------------------------------
# Top-level worker functions (required for ProcessPoolExecutor pickling)
# ------------------------------------------------------------------

# Process-level cache for expensive objects.  Each subprocess in the
# ProcessPoolExecutor persists for multiple files within a batch, so
# caching the AnalysisCache connection and analyzer/backend objects
# avoids redundant construction per file.
_process_cache: dict = {}


@contextlib.contextmanager
def _suppress_stderr():
    """Suppress C-level stderr output (e.g. mpg123 decoder warnings).

    Redirects file descriptor 2 to /dev/null temporarily. This is
    necessary because libraries like mpg123 write warnings about
    corrupted MPEG headers directly to stderr at the C level, bypassing
    Python's sys.stderr.

    Uses try/finally to guarantee fd cleanup even if the body raises.
    Tracks devnull fd separately to prevent leaks if os.dup() fails
    after os.open() succeeds.
    """
    old_stderr = None
    devnull = None
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        devnull = None  # fd2 now points to /dev/null; devnull fd is closed
    except OSError:
        # If redirection setup fails, clean up and run without suppression
        if devnull is not None:
            os.close(devnull)
        if old_stderr is not None:
            os.close(old_stderr)
        old_stderr = None
    try:
        yield
    finally:
        if old_stderr is not None:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)


def _analyze_energy_single(file_path: str, cache_db_path: str | None = None) -> dict:
    """Analyze energy for a single file in a subprocess.

    Caches AnalysisCache and EnergyAnalyzer at process level so they
    are reused across files within the same subprocess.

    Returns:
        Dict with file_path, format, energy (int|None), and status.
    """
    fmt = Path(file_path).suffix.lower()
    try:
        cache = None
        if cache_db_path:
            if "analysis_cache" not in _process_cache:
                from vdj_manager.analysis.analysis_cache import AnalysisCache

                _process_cache["analysis_cache"] = AnalysisCache(db_path=Path(cache_db_path))
            cache = _process_cache["analysis_cache"]
            cached = cache.get(file_path, "energy")
            if cached is not None:
                return {
                    "file_path": file_path,
                    "format": fmt,
                    "energy": int(cached),
                    "status": "cached",
                }

        if "energy_analyzer" not in _process_cache:
            from vdj_manager.analysis.energy import EnergyAnalyzer

            _process_cache["energy_analyzer"] = EnergyAnalyzer()
        analyzer = _process_cache["energy_analyzer"]

        with _suppress_stderr():
            energy = analyzer.analyze(file_path)
        if energy is not None:
            if cache is not None:
                cache.put(file_path, "energy", str(energy))
            return {"file_path": file_path, "format": fmt, "energy": energy, "status": "ok"}
        return {"file_path": file_path, "format": fmt, "energy": None, "status": "failed"}
    except Exception as e:
        return {"file_path": file_path, "format": fmt, "energy": None, "status": f"error: {e}"}


def _analyze_mood_single(
    file_path: str,
    cache_db_path: str | None = None,
    artist: str | None = None,
    title: str | None = None,
    lastfm_api_key: str | None = None,
    enable_online: bool = False,
    skip_cache: bool = False,
    model_name: str = "mtg-jamendo",
    threshold: float = 0.1,
    max_tags: int = 5,
) -> dict:
    """Analyze mood for a single file in a subprocess.

    When enable_online is True and artist+title are available, tries
    online lookup (Last.fm -> MusicBrainz) before falling back to
    local model analysis.

    Args:
        skip_cache: If True, ignore cached results and re-analyze.
        model_name: Backend model to use ("mtg-jamendo" or "heuristic").
        threshold: Minimum confidence for multi-label selection.
        max_tags: Maximum number of mood tags per track.

    Returns:
        Dict with file_path, format, mood (str), mood_tags (list), and status.
    """
    fmt = Path(file_path).suffix.lower()
    try:
        from vdj_manager.analysis.mood_backend import MoodModel, cache_key_for_model

        cache_type = cache_key_for_model(MoodModel(model_name))

        cache = None
        if cache_db_path:
            if "analysis_cache" not in _process_cache:
                from vdj_manager.analysis.analysis_cache import AnalysisCache

                _process_cache["analysis_cache"] = AnalysisCache(db_path=Path(cache_db_path))
            cache = _process_cache["analysis_cache"]
            if skip_cache:
                cache.invalidate(file_path)
            else:
                cached = cache.get(file_path, cache_type)
                if cached is not None:
                    mood_tags = cached.split(",")
                    return {
                        "file_path": file_path,
                        "format": fmt,
                        "mood": ", ".join(mood_tags),
                        "mood_tags": mood_tags,
                        "status": "cached",
                    }

        # Try online lookup first
        if enable_online and artist and title:
            from vdj_manager.analysis.online_mood import lookup_online_mood

            mood, source = lookup_online_mood(artist, title, lastfm_api_key)
            if mood:
                mood_tags = [mood]
                if cache is not None:
                    cache.put(file_path, cache_type, mood)
                return {
                    "file_path": file_path,
                    "format": fmt,
                    "mood": mood,
                    "mood_tags": mood_tags,
                    "status": f"ok ({source})",
                }

        # Fall back to local model analysis
        from vdj_manager.analysis.mood_backend import get_backend

        backend_key = f"mood_backend:{model_name}"
        if backend_key not in _process_cache:
            _process_cache[backend_key] = get_backend(MoodModel(model_name))
        backend = _process_cache[backend_key]

        with _suppress_stderr():
            mood_tags = backend.get_mood_tags(file_path, threshold, max_tags)
        if mood_tags:
            mood_str = ", ".join(mood_tags)
            if cache is not None:
                cache.put(file_path, cache_type, ",".join(mood_tags))
            return {
                "file_path": file_path,
                "format": fmt,
                "mood": mood_str,
                "mood_tags": mood_tags,
                "status": f"ok (local:{model_name})",
            }

        # Try fallback model (mtg-jamendo ↔ heuristic)
        fallback_name = "heuristic" if model_name == "mtg-jamendo" else "mtg-jamendo"
        try:
            fallback_key = f"mood_backend:{fallback_name}"
            if fallback_key not in _process_cache:
                _process_cache[fallback_key] = get_backend(MoodModel(fallback_name))
            fallback = _process_cache[fallback_key]
            if fallback.is_available:
                with _suppress_stderr():
                    mood_tags = fallback.get_mood_tags(file_path, threshold, max_tags)
                if mood_tags:
                    mood_str = ", ".join(mood_tags)
                    if cache is not None:
                        cache.put(file_path, cache_type, ",".join(mood_tags))
                    return {
                        "file_path": file_path,
                        "format": fmt,
                        "mood": mood_str,
                        "mood_tags": mood_tags,
                        "status": f"ok (local:{fallback_name})",
                    }
        except Exception:
            pass

        # Last resort — never return "failed"
        if cache is not None:
            cache.put(file_path, cache_type, "unknown")
        return {
            "file_path": file_path,
            "format": fmt,
            "mood": "unknown",
            "mood_tags": ["unknown"],
            "status": "ok (unknown)",
        }
    except Exception as e:
        logger.warning("Mood analysis failed for %s: %s", file_path, e)
        return {
            "file_path": file_path,
            "format": fmt,
            "mood": "unknown",
            "mood_tags": ["unknown"],
            "status": "ok (unknown)",
        }


def _fetch_genre_single(
    file_path: str,
    cache_db_path: str | None = None,
    artist: str | None = None,
    title: str | None = None,
    lastfm_api_key: str | None = None,
    enable_online: bool = False,
    skip_cache: bool = False,
) -> dict:
    """Fetch genre for a single file in a subprocess.

    Two-pass approach:
    1. Read embedded file tags via FileTagEditor (fast, no network).
    2. If no genre found and online enabled, try Last.fm / MusicBrainz.

    Returns:
        Dict with file_path, format, genre (str|None), source, and status.
    """
    fmt = Path(file_path).suffix.lower()
    try:
        cache = None
        if cache_db_path:
            if "analysis_cache" not in _process_cache:
                from vdj_manager.analysis.analysis_cache import AnalysisCache

                _process_cache["analysis_cache"] = AnalysisCache(db_path=Path(cache_db_path))
            cache = _process_cache["analysis_cache"]
            if skip_cache:
                cache.invalidate(file_path, "genre")
            else:
                cached = cache.get(file_path, "genre")
                if cached is not None:
                    return {
                        "file_path": file_path,
                        "format": fmt,
                        "genre": cached,
                        "source": "cache",
                        "status": "cached",
                    }

        # Pass 1: Read embedded file tags
        if os.path.isfile(file_path):
            from vdj_manager.files.id3_editor import FileTagEditor

            if "file_tag_editor" not in _process_cache:
                _process_cache["file_tag_editor"] = FileTagEditor()
            editor = _process_cache["file_tag_editor"]

            try:
                file_tags = editor.read_tags(file_path)
                raw_genre = file_tags.get("genre")
                if raw_genre and raw_genre.strip():
                    from vdj_manager.analysis.online_genre import normalize_genre

                    genre = normalize_genre(raw_genre)
                    if genre:
                        if cache is not None:
                            cache.put(file_path, "genre", genre)
                        return {
                            "file_path": file_path,
                            "format": fmt,
                            "genre": genre,
                            "source": "file-tag",
                            "status": "ok (file-tag)",
                        }
            except Exception:
                logger.debug("Failed to read file tags for %s", file_path)

        # Pass 2: Online lookup
        if enable_online and artist and title:
            from vdj_manager.analysis.online_genre import lookup_online_genre

            online_genre, source = lookup_online_genre(artist, title, lastfm_api_key)
            if online_genre:
                if cache is not None:
                    cache.put(file_path, "genre", online_genre)
                return {
                    "file_path": file_path,
                    "format": fmt,
                    "genre": online_genre,
                    "source": source,
                    "status": f"ok ({source})",
                }

        return {
            "file_path": file_path,
            "format": fmt,
            "genre": None,
            "source": "none",
            "status": "none",
        }
    except Exception as e:
        return {
            "file_path": file_path,
            "format": fmt,
            "genre": None,
            "source": "none",
            "status": f"error: {e}",
        }


def _import_mik_single(file_path: str, cache_db_path: str | None = None) -> dict:
    """Import MIK tags for a single file in a subprocess.

    Returns:
        Dict with file_path, format, energy, key, and status.
    """
    fmt = Path(file_path).suffix.lower()
    try:
        cache = None
        if cache_db_path:
            if "analysis_cache" not in _process_cache:
                from vdj_manager.analysis.analysis_cache import AnalysisCache

                _process_cache["analysis_cache"] = AnalysisCache(db_path=Path(cache_db_path))
            cache = _process_cache["analysis_cache"]
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
            if cache is not None:
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
        return {
            "file_path": file_path,
            "format": fmt,
            "energy": None,
            "key": None,
            "status": "none",
        }
    except Exception as e:
        return {
            "file_path": file_path,
            "format": fmt,
            "energy": None,
            "key": None,
            "status": f"error: {e}",
        }


# ------------------------------------------------------------------
# Pausable analysis worker base
# ------------------------------------------------------------------


class PausableAnalysisWorker(QThread):
    """Base class for analysis workers with pause/resume/cancel.

    Extends QThread directly with pause/resume threading primitives.
    Compatible with ProgressWidget.connect_worker() via matching signals.

    Signals:
        progress: (current, total, percent) for ProgressWidget.
        result_ready: (dict) streamed per-result for ConfigurableResultsTable.
        status_changed: (str) for ProgressWidget status tracking.
        finished_work: (object) result dict on completion.
        error: (str) error message.
    """

    progress = Signal(int, int, float)  # current, total, percent
    result_ready = Signal(dict)  # per-file result dict
    status_changed = Signal(str)  # status string
    finished_work = Signal(object)  # result dict
    error = Signal(str)  # error message

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()
        self._is_paused = False
        self._is_cancelled = False

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def pause(self) -> None:
        """Request pause after current item."""
        self._mutex.lock()
        try:
            self._is_paused = True
            self.status_changed.emit("paused")
        finally:
            self._mutex.unlock()

    def resume(self) -> None:
        """Resume from pause."""
        self._mutex.lock()
        try:
            self._is_paused = False
            self.status_changed.emit("running")
            self._pause_condition.wakeAll()
        finally:
            self._mutex.unlock()

    def cancel(self) -> None:
        """Request cancellation."""
        self._mutex.lock()
        try:
            self._is_cancelled = True
            self._is_paused = False
            self.status_changed.emit("cancelled")
            self._pause_condition.wakeAll()
        finally:
            self._mutex.unlock()

    def _wait_if_paused(self) -> bool:
        """Block while paused, return False if cancelled."""
        self._mutex.lock()
        try:
            while self._is_paused and not self._is_cancelled:
                self._pause_condition.wait(self._mutex)
            return not self._is_cancelled
        finally:
            self._mutex.unlock()

    def _check_cancelled(self) -> bool:
        """Non-blocking cancel check."""
        self._mutex.lock()
        try:
            return self._is_cancelled
        finally:
            self._mutex.unlock()

    def _emit_progress(self, current: int, total: int) -> None:
        """Emit progress signal with percent."""
        percent = (current / total * 100) if total > 0 else 0.0
        self.progress.emit(current, total, percent)

    def do_work(self) -> dict:
        """Override in subclass."""
        raise NotImplementedError

    def run(self) -> None:
        """Execute do_work with status signals."""
        try:
            self.status_changed.emit("running")
            result = self.do_work()
            if not self._is_cancelled:
                self.status_changed.emit("completed")
            self.finished_work.emit(result)
        except Exception as e:
            self.status_changed.emit("failed")
            self.error.emit(str(e))


# ------------------------------------------------------------------
# Worker classes
# ------------------------------------------------------------------


class EnergyWorker(PausableAnalysisWorker):
    """Worker that analyzes energy levels for audio tracks in parallel.

    Uses ProcessPoolExecutor to analyze multiple files simultaneously,
    streaming results to the GUI via result_ready signal.
    Supports pause/resume/cancel between batches.

    Note: This worker does NOT mutate the database directly. It includes
    ``tag_updates`` in each result dict so the main-thread panel handler
    can apply DB changes safely (no cross-thread mutation).
    """

    def __init__(
        self,
        tracks: list[Song],
        max_workers: int | None = None,
        cache_db_path: str | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self._cache_db_path = cache_db_path

    def do_work(self) -> dict:
        """Analyze energy for all tracks in parallel."""
        analyzed = 0
        failed = 0
        cached = 0
        results: list[dict[str, Any]] = []
        total = len(self._tracks)

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            for batch_start in range(0, len(file_paths), _SAVE_INTERVAL):
                if not self._wait_if_paused():
                    break

                batch = file_paths[batch_start : batch_start + _SAVE_INTERVAL]
                futures = {
                    executor.submit(_analyze_energy_single, fp, self._cache_db_path): fp
                    for fp in batch
                }

                for future in as_completed(futures):
                    if self._check_cancelled():
                        executor.shutdown(wait=False, cancel_futures=True)
                        return {
                            "analyzed": analyzed,
                            "failed": failed,
                            "cached": cached,
                            "results": results,
                        }

                    try:
                        result = future.result()
                    except Exception as e:
                        fp = futures[future]
                        result = {
                            "file_path": fp,
                            "format": Path(fp).suffix.lower(),
                            "energy": None,
                            "status": f"error: {e}",
                        }

                    if result["status"] == "cached" and result["energy"] is not None:
                        result["tag_updates"] = {"Grouping": str(result["energy"])}
                        cached += 1
                    elif result["status"] == "ok" and result["energy"] is not None:
                        result["tag_updates"] = {"Grouping": str(result["energy"])}
                        analyzed += 1
                    else:
                        failed += 1

                    results.append(result)
                    self.result_ready.emit(result)
                    self._emit_progress(analyzed + failed + cached, total)

                # Free librosa/audioread handles accumulated during batch
                gc.collect()

        return {"analyzed": analyzed, "failed": failed, "cached": cached, "results": results}


class MIKImportWorker(PausableAnalysisWorker):
    """Worker that imports Mixed In Key tags from audio files in parallel.

    Reads MIK energy and key data from file tags using ProcessPoolExecutor.
    Supports pause/resume/cancel.

    Note: This worker does NOT mutate the database directly. It includes
    ``tag_updates`` in each result dict so the main-thread panel handler
    can apply DB changes safely (no cross-thread mutation).
    """

    def __init__(
        self,
        tracks: list[Song],
        max_workers: int | None = None,
        cache_db_path: str | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self._cache_db_path = cache_db_path

    def do_work(self) -> dict:
        """Import MIK tags for all tracks in parallel."""
        found = 0
        updated = 0
        results: list[dict[str, Any]] = []
        total = len(self._tracks)

        # Build a lookup for existing energy tags (read-only snapshot)
        existing_energy = {t.file_path: t.energy for t in self._tracks}

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            for batch_start in range(0, len(file_paths), _SAVE_INTERVAL):
                if not self._wait_if_paused():
                    break

                batch = file_paths[batch_start : batch_start + _SAVE_INTERVAL]
                futures = {
                    executor.submit(_import_mik_single, fp, self._cache_db_path): fp for fp in batch
                }

                for future in as_completed(futures):
                    if self._check_cancelled():
                        executor.shutdown(wait=False, cancel_futures=True)
                        return {"found": found, "updated": updated, "results": results}

                    try:
                        result = future.result()
                    except Exception as e:
                        fp = futures[future]
                        result = {
                            "file_path": fp,
                            "format": Path(fp).suffix.lower(),
                            "energy": None,
                            "key": None,
                            "status": f"error: {e}",
                        }

                    if result["status"] in ("found", "cached"):
                        found += 1
                        tag_updates = {}
                        if result.get("energy") and not existing_energy.get(result["file_path"]):
                            tag_updates["Grouping"] = str(result["energy"])
                        if result.get("key"):
                            tag_updates["Key"] = result["key"]
                        if tag_updates:
                            result["tag_updates"] = tag_updates
                            updated += 1
                            result["status"] = "updated"
                        else:
                            result["status"] = "exists"

                    results.append(result)
                    self.result_ready.emit(result)
                    self._emit_progress(len(results), total)

        return {"found": found, "updated": updated, "results": results}


class MoodWorker(PausableAnalysisWorker):
    """Worker that analyzes mood/emotion for audio tracks in parallel.

    Supports online mood lookup (Last.fm / MusicBrainz) with fallback
    to local model analysis. Multi-label: writes multiple mood hashtags
    to User2 (e.g. "#happy #uplifting #summer").
    Supports pause/resume/cancel and model selection.

    Note: This worker does NOT mutate the database directly. It includes
    ``tag_updates`` in each result dict so the main-thread panel handler
    can apply DB changes safely (no cross-thread mutation).
    """

    def __init__(
        self,
        tracks: list[Song],
        max_workers: int | None = None,
        cache_db_path: str | None = None,
        enable_online: bool = False,
        lastfm_api_key: str | None = None,
        skip_cache: bool = False,
        model_name: str = "mtg-jamendo",
        threshold: float = 0.1,
        max_tags: int = 5,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self._cache_db_path = cache_db_path
        self._enable_online = enable_online
        self._lastfm_api_key = lastfm_api_key
        self._skip_cache = skip_cache
        self._model_name = model_name
        self._threshold = threshold
        self._max_tags = max_tags

    def do_work(self) -> dict:
        """Analyze mood for all tracks in parallel."""
        # Check backend availability
        if not self._enable_online:
            from vdj_manager.analysis.mood_backend import MoodModel, get_backend

            backend = get_backend(MoodModel(self._model_name))
            if not backend.is_available:
                return {
                    "analyzed": 0,
                    "failed": 0,
                    "cached": 0,
                    "results": [],
                    "error": f"Backend '{self._model_name}' is not available "
                    "(essentia-tensorflow not installed)",
                }

        # Cap workers at 1 when online (rate limiting)
        max_workers = 1 if self._enable_online else self._max_workers

        analyzed = 0
        failed = 0
        cached = 0
        results: list[dict[str, Any]] = []
        total = len(self._tracks)

        # Build read-only snapshots for artist/title and existing user2
        track_info = {}
        existing_user2 = {}
        for t in self._tracks:
            artist = (t.tags.author or "") if t.tags else ""
            title = (t.tags.title or "") if t.tags else ""
            track_info[t.file_path] = (artist, title)
            existing_user2[t.file_path] = (t.tags.user2 or "") if t.tags else ""

        file_paths = [t.file_path for t in self._tracks]

        # Known mood class names for tag cleanup during re-analysis
        from vdj_manager.analysis.mood_backend import MOOD_CLASSES_SET

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for batch_start in range(0, len(file_paths), _SAVE_INTERVAL):
                if not self._wait_if_paused():
                    break

                batch = file_paths[batch_start : batch_start + _SAVE_INTERVAL]
                futures = {}
                for fp in batch:
                    artist, title = track_info.get(fp, ("", ""))
                    futures[
                        executor.submit(
                            _analyze_mood_single,
                            fp,
                            self._cache_db_path,
                            artist=artist,
                            title=title,
                            lastfm_api_key=self._lastfm_api_key,
                            enable_online=self._enable_online,
                            skip_cache=self._skip_cache,
                            model_name=self._model_name,
                            threshold=self._threshold,
                            max_tags=self._max_tags,
                        )
                    ] = fp

                for future in as_completed(futures):
                    if self._check_cancelled():
                        executor.shutdown(wait=False, cancel_futures=True)
                        return {
                            "analyzed": analyzed,
                            "failed": failed,
                            "cached": cached,
                            "results": results,
                        }

                    try:
                        result = future.result()
                    except Exception:
                        fp = futures[future]
                        result = {
                            "file_path": fp,
                            "format": Path(fp).suffix.lower(),
                            "mood": "unknown",
                            "mood_tags": ["unknown"],
                            "status": "ok (unknown)",
                        }

                    status = result.get("status", "")
                    mood_tags = result.get("mood_tags", [])
                    if mood_tags and (status.startswith("ok") or status == "cached"):
                        new_hashtags = {f"#{t}" for t in mood_tags}
                        existing = existing_user2.get(result["file_path"], "")

                        if self._skip_cache:
                            # Re-analyzing: strip ALL known mood hashtags, then add new
                            words = [
                                w
                                for w in existing.split()
                                if not (w.startswith("#") and w[1:] in MOOD_CLASSES_SET)
                                and w != "#unknown"
                            ]
                        else:
                            words = existing.split()

                        # Add new hashtags that aren't already present
                        existing_set = set(words)
                        for ht in sorted(new_hashtags):
                            if ht not in existing_set:
                                words.append(ht)

                        new_user2 = " ".join(words).strip()
                        result["tag_updates"] = {"User2": new_user2}
                        if status == "cached":
                            cached += 1
                        else:
                            analyzed += 1
                    else:
                        failed += 1

                    results.append(result)
                    self.result_ready.emit(result)
                    self._emit_progress(analyzed + failed + cached, total)

                # Free audioread handles accumulated during batch
                gc.collect()

        return {"analyzed": analyzed, "failed": failed, "cached": cached, "results": results}


class GenreWorker(PausableAnalysisWorker):
    """Worker that fetches/detects genre for audio tracks in parallel.

    Two-pass: reads embedded file tags first, then online lookup for
    missing genres (Last.fm / MusicBrainz).
    Supports pause/resume/cancel between batches.

    Note: This worker does NOT mutate the database directly. It includes
    ``tag_updates`` in each result dict so the main-thread panel handler
    can apply DB changes safely (no cross-thread mutation).
    """

    def __init__(
        self,
        tracks: list[Song],
        max_workers: int | None = None,
        cache_db_path: str | None = None,
        enable_online: bool = False,
        lastfm_api_key: str | None = None,
        skip_cache: bool = False,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self._cache_db_path = cache_db_path
        self._enable_online = enable_online
        self._lastfm_api_key = lastfm_api_key
        self._skip_cache = skip_cache

    def do_work(self) -> dict:
        """Fetch genre for all tracks in parallel."""
        # Cap workers at 1 when online (rate limiting)
        max_workers = 1 if self._enable_online else self._max_workers

        analyzed = 0
        failed = 0
        cached = 0
        results: list[dict[str, Any]] = []
        total = len(self._tracks)

        # Build read-only snapshot of artist/title metadata
        track_info = {}
        for t in self._tracks:
            artist = (t.tags.author or "") if t.tags else ""
            title = (t.tags.title or "") if t.tags else ""
            track_info[t.file_path] = (artist, title)

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for batch_start in range(0, len(file_paths), _SAVE_INTERVAL):
                if not self._wait_if_paused():
                    break

                batch = file_paths[batch_start : batch_start + _SAVE_INTERVAL]
                futures = {}
                for fp in batch:
                    artist, title = track_info.get(fp, ("", ""))
                    futures[
                        executor.submit(
                            _fetch_genre_single,
                            fp,
                            self._cache_db_path,
                            artist=artist,
                            title=title,
                            lastfm_api_key=self._lastfm_api_key,
                            enable_online=self._enable_online,
                            skip_cache=self._skip_cache,
                        )
                    ] = fp

                for future in as_completed(futures):
                    if self._check_cancelled():
                        executor.shutdown(wait=False, cancel_futures=True)
                        return {
                            "analyzed": analyzed,
                            "failed": failed,
                            "cached": cached,
                            "results": results,
                        }

                    try:
                        result = future.result()
                    except Exception as e:
                        fp = futures[future]
                        result = {
                            "file_path": fp,
                            "format": Path(fp).suffix.lower(),
                            "genre": None,
                            "source": "none",
                            "status": f"error: {e}",
                        }

                    genre = result.get("genre")
                    status = result.get("status", "")
                    if genre and (status.startswith("ok") or status == "cached"):
                        result["tag_updates"] = {"Genre": genre}
                        if status == "cached":
                            cached += 1
                        else:
                            analyzed += 1
                    else:
                        failed += 1

                    results.append(result)
                    self.result_ready.emit(result)
                    self._emit_progress(analyzed + failed + cached, total)

        return {"analyzed": analyzed, "failed": failed, "cached": cached, "results": results}
