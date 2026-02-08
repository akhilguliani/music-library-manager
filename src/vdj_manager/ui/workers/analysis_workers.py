"""Workers for audio analysis operations with parallel processing."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.ui.workers.base_worker import ProgressSimpleWorker


# ------------------------------------------------------------------
# Top-level worker functions (required for ProcessPoolExecutor pickling)
# ------------------------------------------------------------------

def _analyze_energy_single(file_path: str) -> dict:
    """Analyze energy for a single file in a subprocess.

    Returns:
        Dict with file_path, energy (int|None), and status.
    """
    try:
        from vdj_manager.analysis.energy import EnergyAnalyzer

        analyzer = EnergyAnalyzer()
        energy = analyzer.analyze(file_path)
        if energy is not None:
            return {"file_path": file_path, "energy": energy, "status": "ok"}
        return {"file_path": file_path, "energy": None, "status": "failed"}
    except Exception as e:
        return {"file_path": file_path, "energy": None, "status": f"error: {e}"}


def _analyze_mood_single(file_path: str) -> dict:
    """Analyze mood for a single file in a subprocess.

    Returns:
        Dict with file_path, mood (str|None), and status.
    """
    try:
        from vdj_manager.analysis.mood import MoodAnalyzer

        analyzer = MoodAnalyzer()
        mood_tag = analyzer.get_mood_tag(file_path)
        if mood_tag:
            return {"file_path": file_path, "mood": mood_tag, "status": "ok"}
        return {"file_path": file_path, "mood": None, "status": "failed"}
    except Exception as e:
        return {"file_path": file_path, "mood": None, "status": f"error: {e}"}


def _import_mik_single(file_path: str) -> dict:
    """Import MIK tags for a single file in a subprocess.

    Returns:
        Dict with file_path, energy, key, and status.
    """
    try:
        from vdj_manager.analysis.audio_features import MixedInKeyReader

        reader = MixedInKeyReader()
        mik_data = reader.read_tags(file_path)
        if mik_data.get("energy") or mik_data.get("key"):
            return {
                "file_path": file_path,
                "energy": mik_data.get("energy"),
                "key": mik_data.get("key"),
                "status": "found",
            }
        return {"file_path": file_path, "energy": None, "key": None, "status": "none"}
    except Exception:
        return {"file_path": file_path, "status": "error"}


# ------------------------------------------------------------------
# Worker classes
# ------------------------------------------------------------------

class EnergyWorker(ProgressSimpleWorker):
    """Worker that analyzes energy levels for audio tracks in parallel.

    Uses ProcessPoolExecutor to analyze multiple files simultaneously,
    then batch-writes results to the database.
    """

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        max_workers: int | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)

    def do_work(self) -> dict:
        """Analyze energy for all tracks in parallel.

        Returns:
            Dict with analyzed count, failed count, and results list.
        """
        analyzed = 0
        failed = 0
        results = []
        total = len(self._tracks)

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(_analyze_energy_single, fp): fp
                for fp in file_paths
            }

            for future in as_completed(futures):
                if self.is_cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                result = future.result()
                results.append(result)

                if result["status"] == "ok" and result["energy"] is not None:
                    self._database.update_song_tags(
                        result["file_path"],
                        Grouping=f"Energy {result['energy']}",
                    )
                    analyzed += 1
                else:
                    failed += 1

                self.report_progress(analyzed + failed, total, result["file_path"])

        if analyzed > 0:
            self._database.save()

        return {"analyzed": analyzed, "failed": failed, "results": results}


class MIKImportWorker(ProgressSimpleWorker):
    """Worker that imports Mixed In Key tags from audio files in parallel.

    Reads MIK energy and key data from file tags using ProcessPoolExecutor
    and updates the VDJ database.
    """

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        max_workers: int | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)

    def do_work(self) -> dict:
        """Import MIK tags for all tracks in parallel.

        Returns:
            Dict with found count, updated count, and results list.
        """
        found = 0
        updated = 0
        results = []
        total = len(self._tracks)

        # Build a lookup for existing energy tags
        existing_energy = {
            t.file_path: t.energy for t in self._tracks
        }

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(_import_mik_single, fp): fp
                for fp in file_paths
            }

            for future in as_completed(futures):
                if self.is_cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                result = future.result()

                if result["status"] == "found":
                    found += 1
                    updates = {}
                    if result.get("energy") and not existing_energy.get(result["file_path"]):
                        updates["Grouping"] = f"Energy {result['energy']}"
                    if result.get("key"):
                        updates["Comment"] = result["key"]
                    if updates:
                        self._database.update_song_tags(result["file_path"], **updates)
                        updated += 1
                        result["status"] = "updated"
                    else:
                        result["status"] = "exists"

                results.append(result)
                self.report_progress(len(results), total, result["file_path"])

        if updated > 0:
            self._database.save()

        return {"found": found, "updated": updated, "results": results}


class MoodWorker(ProgressSimpleWorker):
    """Worker that analyzes mood/emotion for audio tracks in parallel.

    Uses MoodAnalyzer (requires essentia-tensorflow) with ProcessPoolExecutor
    to classify audio mood and updates the database Comment field.
    """

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        max_workers: int | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks
        self._max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)

    def do_work(self) -> dict:
        """Analyze mood for all tracks in parallel.

        Returns:
            Dict with analyzed count, failed count, and results list.
        """
        # Check availability before spawning workers
        from vdj_manager.analysis.mood import MoodAnalyzer

        analyzer = MoodAnalyzer()
        if not analyzer.is_available:
            return {
                "analyzed": 0,
                "failed": 0,
                "results": [],
                "error": "essentia-tensorflow is not installed",
            }

        analyzed = 0
        failed = 0
        results = []
        total = len(self._tracks)

        file_paths = [t.file_path for t in self._tracks]

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(_analyze_mood_single, fp): fp
                for fp in file_paths
            }

            for future in as_completed(futures):
                if self.is_cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                result = future.result()
                results.append(result)

                if result["status"] == "ok" and result.get("mood"):
                    self._database.update_song_tags(
                        result["file_path"], Comment=result["mood"]
                    )
                    analyzed += 1
                else:
                    failed += 1

                self.report_progress(analyzed + failed, total, result["file_path"])

        if analyzed > 0:
            self._database.save()

        return {"analyzed": analyzed, "failed": failed, "results": results}
