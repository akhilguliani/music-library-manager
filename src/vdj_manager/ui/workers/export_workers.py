"""Workers for export operations."""

from pathlib import Path
from typing import Any, Optional

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.ui.workers.base_worker import SimpleWorker


class SeratoExportWorker(SimpleWorker):
    """Worker that exports VDJ library to Serato format.

    Writes Serato-compatible tags to audio files and optionally
    creates Serato crate files for playlists.
    """

    def __init__(
        self,
        tracks: list[Song],
        cues_only: bool = False,
        serato_dir: Optional[Path] = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks
        self._cues_only = cues_only
        self._serato_dir = serato_dir

    def do_work(self) -> dict:
        """Export tracks to Serato format.

        Returns:
            Dict with exported count, failed count, and details.
        """
        from vdj_manager.export.serato import SeratoExporter

        exporter = SeratoExporter(self._serato_dir)
        exported = 0
        failed = 0
        results = []

        for track in self._tracks:
            try:
                success = exporter.export_song(track, cues_only=self._cues_only)
                if success:
                    exported += 1
                    results.append({
                        "file_path": track.file_path,
                        "status": "exported",
                    })
                else:
                    failed += 1
                    results.append({
                        "file_path": track.file_path,
                        "status": "skipped",
                    })
            except Exception as e:
                failed += 1
                results.append({
                    "file_path": track.file_path,
                    "status": f"error: {e}",
                })

        return {"exported": exported, "failed": failed, "results": results}


class CrateExportWorker(SimpleWorker):
    """Worker that exports a VDJ playlist as a Serato crate."""

    def __init__(
        self,
        crate_name: str,
        file_paths: list[str],
        serato_dir: Optional[Path] = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._crate_name = crate_name
        self._file_paths = file_paths
        self._serato_dir = serato_dir

    def do_work(self) -> dict:
        """Create a Serato crate file.

        Returns:
            Dict with crate path and track count.
        """
        from vdj_manager.export.serato import SeratoCrateWriter

        writer = SeratoCrateWriter(self._serato_dir)
        crate_path = writer.write_crate(self._crate_name, self._file_paths)

        return {
            "crate_name": self._crate_name,
            "crate_path": str(crate_path),
            "track_count": len(self._file_paths),
        }
