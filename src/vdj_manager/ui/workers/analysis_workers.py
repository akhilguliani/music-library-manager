"""Workers for audio analysis operations."""

from pathlib import Path
from typing import Any

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.ui.workers.base_worker import SimpleWorker


class EnergyWorker(SimpleWorker):
    """Worker that analyzes energy levels for audio tracks.

    Analyzes files using EnergyAnalyzer and updates the database
    with energy tags in the Grouping field.
    """

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks

    def do_work(self) -> dict:
        """Analyze energy for all tracks.

        Returns:
            Dict with analyzed count, failed count, and results list.
        """
        from vdj_manager.analysis.energy import EnergyAnalyzer

        analyzer = EnergyAnalyzer()
        analyzed = 0
        failed = 0
        results = []

        for track in self._tracks:
            try:
                energy = analyzer.analyze(track.file_path)
                if energy is not None:
                    self._database.update_song_tags(
                        track.file_path, Grouping=f"Energy {energy}"
                    )
                    analyzed += 1
                    results.append({
                        "file_path": track.file_path,
                        "energy": energy,
                        "status": "ok",
                    })
                else:
                    failed += 1
                    results.append({
                        "file_path": track.file_path,
                        "energy": None,
                        "status": "failed",
                    })
            except Exception as e:
                failed += 1
                results.append({
                    "file_path": track.file_path,
                    "energy": None,
                    "status": f"error: {e}",
                })

        if analyzed > 0:
            self._database.save()

        return {"analyzed": analyzed, "failed": failed, "results": results}


class MIKImportWorker(SimpleWorker):
    """Worker that imports Mixed In Key tags from audio files.

    Reads MIK energy and key data from file tags and updates
    the VDJ database.
    """

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks

    def do_work(self) -> dict:
        """Import MIK tags for all tracks.

        Returns:
            Dict with found count, updated count, and results list.
        """
        from vdj_manager.analysis.audio_features import MixedInKeyReader

        reader = MixedInKeyReader()
        found = 0
        updated = 0
        results = []

        for track in self._tracks:
            try:
                mik_data = reader.read_tags(track.file_path)
                if mik_data.get("energy") or mik_data.get("key"):
                    found += 1
                    updates = {}
                    if mik_data.get("energy") and not track.energy:
                        updates["Grouping"] = f"Energy {mik_data['energy']}"
                    if mik_data.get("key"):
                        updates["Comment"] = mik_data["key"]
                    if updates:
                        self._database.update_song_tags(track.file_path, **updates)
                        updated += 1
                    results.append({
                        "file_path": track.file_path,
                        "energy": mik_data.get("energy"),
                        "key": mik_data.get("key"),
                        "status": "updated" if updates else "exists",
                    })
            except Exception:
                results.append({
                    "file_path": track.file_path,
                    "status": "error",
                })

        if updated > 0:
            self._database.save()

        return {"found": found, "updated": updated, "results": results}


class MoodWorker(SimpleWorker):
    """Worker that analyzes mood/emotion for audio tracks.

    Uses MoodAnalyzer (requires essentia-tensorflow) to classify
    audio mood and updates the database Comment field.
    """

    def __init__(
        self,
        database: VDJDatabase,
        tracks: list[Song],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._tracks = tracks

    def do_work(self) -> dict:
        """Analyze mood for all tracks.

        Returns:
            Dict with analyzed count, failed count, and results list.
        """
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

        for track in self._tracks:
            try:
                mood_tag = analyzer.get_mood_tag(track.file_path)
                if mood_tag:
                    self._database.update_song_tags(track.file_path, Comment=mood_tag)
                    analyzed += 1
                    results.append({
                        "file_path": track.file_path,
                        "mood": mood_tag,
                        "status": "ok",
                    })
                else:
                    failed += 1
                    results.append({
                        "file_path": track.file_path,
                        "mood": None,
                        "status": "failed",
                    })
            except Exception as e:
                failed += 1
                results.append({
                    "file_path": track.file_path,
                    "mood": None,
                    "status": f"error: {e}",
                })

        if analyzed > 0:
            self._database.save()

        return {"analyzed": analyzed, "failed": failed, "results": results}
