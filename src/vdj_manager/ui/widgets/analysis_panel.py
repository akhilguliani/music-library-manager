"""Analysis panel with energy, mood, and MIK import sub-tabs."""

import multiprocessing
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QTabWidget,
    QSpinBox,
    QCheckBox,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from vdj_manager.analysis.analysis_cache import DEFAULT_ANALYSIS_CACHE_PATH
from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.ui.widgets.results_table import ConfigurableResultsTable
from vdj_manager.ui.workers.analysis_workers import (
    EnergyWorker,
    MIKImportWorker,
    MoodWorker,
)


class AnalysisPanel(QWidget):
    """Panel for audio analysis operations.

    Provides sub-tabs for:
    - Energy level analysis (1-10 scale)
    - Mood classification
    - Mixed In Key tag import

    Signals:
        database_changed: Emitted when database is modified.
    """

    database_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._database: VDJDatabase | None = None
        self._tracks: list[Song] = []
        self._energy_worker: EnergyWorker | None = None
        self._mik_worker: MIKImportWorker | None = None
        self._mood_worker: MoodWorker | None = None

        self._setup_ui()

    def set_database(self, database: VDJDatabase | None, tracks: list[Song] | None = None) -> None:
        """Set the database and tracks for analysis.

        Args:
            database: VDJDatabase instance.
            tracks: Optional list of tracks.
        """
        self._database = database
        if tracks is not None:
            self._tracks = tracks
        elif database is not None:
            self._tracks = list(database.iter_songs())
        else:
            self._tracks = []

        has_db = database is not None and len(self._tracks) > 0
        self.energy_all_btn.setEnabled(has_db)
        self.energy_untagged_btn.setEnabled(has_db)
        self.mik_scan_btn.setEnabled(has_db)
        self.mood_btn.setEnabled(has_db)
        self._update_track_info()

    def _setup_ui(self) -> None:
        """Set up the panel UI with sub-tabs."""
        layout = QVBoxLayout(self)

        # Workers configuration (shared across all sub-tabs)
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("Workers:"))
        cpu_count = multiprocessing.cpu_count()
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 20)
        self.workers_spin.setValue(max(1, cpu_count - 1))
        self.workers_spin.setToolTip(
            f"Parallel workers for analysis ({cpu_count} CPU cores detected)"
        )
        config_layout.addWidget(self.workers_spin)

        config_layout.addWidget(QLabel("Limit:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 999999)
        self.limit_spin.setValue(0)
        self.limit_spin.setSpecialValueText("All")
        self.limit_spin.setToolTip("Limit number of tracks to process (0 = all)")
        config_layout.addWidget(self.limit_spin)

        config_layout.addWidget(QLabel("Max Duration:"))
        self.max_duration_spin = QSpinBox()
        self.max_duration_spin.setRange(0, 999)
        self.max_duration_spin.setValue(0)
        self.max_duration_spin.setSuffix(" min")
        self.max_duration_spin.setSpecialValueText("No limit")
        self.max_duration_spin.setToolTip("Skip tracks longer than this (minutes, 0 = no limit)")
        config_layout.addWidget(self.max_duration_spin)

        config_layout.addStretch()
        layout.addLayout(config_layout)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.setTabPosition(QTabWidget.TabPosition.North)

        self._create_energy_tab()
        self._create_mik_tab()
        self._create_mood_tab()

        layout.addWidget(self.sub_tabs)

    def _create_energy_tab(self) -> None:
        """Create the energy analysis sub-tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Info section
        info_group = QGroupBox("Energy Analysis")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(
            "Analyze audio features to classify energy levels (1-10 scale).\n"
            "Uses tempo, RMS energy, and spectral centroid analysis.\n"
            "Requires: librosa"
        ))
        self.energy_info_label = QLabel("No database loaded")
        info_layout.addWidget(self.energy_info_label)
        layout.addWidget(info_group)

        # Controls
        controls_layout = QHBoxLayout()

        self.energy_all_btn = QPushButton("Analyze All")
        self.energy_all_btn.setEnabled(False)
        self.energy_all_btn.setToolTip("Analyze energy for all audio tracks")
        self.energy_all_btn.clicked.connect(lambda: self._on_energy_clicked(untagged_only=False))
        controls_layout.addWidget(self.energy_all_btn)

        self.energy_untagged_btn = QPushButton("Analyze Untagged")
        self.energy_untagged_btn.setEnabled(False)
        self.energy_untagged_btn.setToolTip("Only analyze tracks without energy tags")
        self.energy_untagged_btn.clicked.connect(lambda: self._on_energy_clicked(untagged_only=True))
        controls_layout.addWidget(self.energy_untagged_btn)

        controls_layout.addStretch()

        self.energy_status = QLabel("")
        controls_layout.addWidget(self.energy_status)

        layout.addLayout(controls_layout)

        # Results table
        self.energy_results = ConfigurableResultsTable([
            {"name": "Track", "key": "file_path", "width": 400},
            {"name": "Energy", "key": "energy", "width": 80},
            {"name": "Status", "key": "status", "width": 120},
        ])
        layout.addWidget(self.energy_results)

        self.sub_tabs.addTab(tab, "Energy")

    def _create_mik_tab(self) -> None:
        """Create the MIK import sub-tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Info section
        info_group = QGroupBox("Mixed In Key Import")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(
            "Import energy and key tags from Mixed In Key data\n"
            "embedded in audio file metadata (ID3/MP4/FLAC tags).\n"
            "Requires: mutagen"
        ))
        self.mik_info_label = QLabel("No database loaded")
        info_layout.addWidget(self.mik_info_label)
        layout.addWidget(info_group)

        # Controls
        controls_layout = QHBoxLayout()

        self.mik_scan_btn = QPushButton("Scan && Import")
        self.mik_scan_btn.setEnabled(False)
        self.mik_scan_btn.setToolTip("Scan audio files for MIK tags and import them")
        self.mik_scan_btn.clicked.connect(self._on_mik_clicked)
        controls_layout.addWidget(self.mik_scan_btn)

        controls_layout.addStretch()

        self.mik_status = QLabel("")
        controls_layout.addWidget(self.mik_status)

        layout.addLayout(controls_layout)

        # Results table
        self.mik_results = ConfigurableResultsTable([
            {"name": "Track", "key": "file_path", "width": 400},
            {"name": "Energy", "key": "energy", "width": 80},
            {"name": "Key", "key": "key", "width": 100},
            {"name": "Status", "key": "status", "width": 120},
        ])
        layout.addWidget(self.mik_results)

        self.sub_tabs.addTab(tab, "MIK Import")

    def _create_mood_tab(self) -> None:
        """Create the mood analysis sub-tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Info section
        info_group = QGroupBox("Mood Analysis")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(
            "Classify audio mood/emotion using audio analysis.\n"
            "Requires: essentia-tensorflow\n"
            "Install with: pip install 'vdj-manager[mood]'"
        ))
        self.mood_info_label = QLabel("No database loaded")
        info_layout.addWidget(self.mood_info_label)
        layout.addWidget(info_group)

        # Controls
        controls_layout = QHBoxLayout()

        self.mood_btn = QPushButton("Analyze Mood")
        self.mood_btn.setEnabled(False)
        self.mood_btn.setToolTip("Analyze mood/emotion for audio tracks")
        self.mood_btn.clicked.connect(self._on_mood_clicked)
        controls_layout.addWidget(self.mood_btn)

        controls_layout.addStretch()

        self.mood_status = QLabel("")
        controls_layout.addWidget(self.mood_status)

        layout.addLayout(controls_layout)

        # Results table
        self.mood_results = ConfigurableResultsTable([
            {"name": "Track", "key": "file_path", "width": 400},
            {"name": "Mood", "key": "mood", "width": 120},
            {"name": "Status", "key": "status", "width": 120},
        ])
        layout.addWidget(self.mood_results)

        self.sub_tabs.addTab(tab, "Mood")

    def _update_track_info(self) -> None:
        """Update track info labels across all tabs."""
        if not self._tracks:
            for label in (self.energy_info_label, self.mik_info_label, self.mood_info_label):
                label.setText("No database loaded")
            return

        audio_tracks = self._get_audio_tracks()
        untagged = [t for t in audio_tracks if t.energy is None]

        self.energy_info_label.setText(
            f"{len(audio_tracks)} audio tracks, {len(untagged)} without energy tags"
        )
        self.mik_info_label.setText(f"{len(audio_tracks)} audio tracks to scan")
        self.mood_info_label.setText(f"{len(audio_tracks)} audio tracks")

    def _get_audio_tracks(self, untagged_only: bool = False) -> list[Song]:
        """Get filterable audio tracks, respecting duration and count limits.

        Args:
            untagged_only: If True, only return tracks without energy tags.

        Returns:
            List of Song objects.
        """
        audio_extensions = {
            ".mp3", ".m4a", ".aac", ".flac", ".wav",
            ".aiff", ".aif", ".ogg", ".opus",
        }
        tracks = []
        for track in self._tracks:
            if track.is_netsearch or track.is_windows_path:
                continue
            if track.extension not in audio_extensions:
                continue
            if untagged_only and track.energy is not None:
                continue
            if not Path(track.file_path).exists():
                continue
            tracks.append(track)

        # Duration filter (minutes → seconds); tracks without metadata are kept
        max_duration = self.max_duration_spin.value() * 60
        if max_duration > 0:
            tracks = [
                t for t in tracks
                if not (t.infos and t.infos.song_length and t.infos.song_length > max_duration)
            ]

        # Count limit
        limit = self.limit_spin.value()
        if limit > 0:
            tracks = tracks[:limit]

        return tracks

    def is_running(self) -> bool:
        """Check if any analysis operation is currently running."""
        for worker in (self._energy_worker, self._mik_worker, self._mood_worker):
            if worker is not None and worker.isRunning():
                return True
        return False

    def _on_energy_clicked(self, untagged_only: bool = False) -> None:
        """Handle energy analysis button click."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An analysis is already in progress.")
            return
        if self._database is None:
            return

        tracks = self._get_audio_tracks(untagged_only=untagged_only)
        if not tracks:
            QMessageBox.information(self, "No Tracks", "No tracks to analyze.")
            return

        # Auto-backup before modifying
        try:
            from vdj_manager.core.backup import BackupManager
            BackupManager().create_backup(self._database.db_path, label="pre_energy")
        except Exception:
            pass

        self.energy_all_btn.setEnabled(False)
        self.energy_untagged_btn.setEnabled(False)
        self.energy_status.setText("Analyzing...")
        self.energy_results.clear()

        self._energy_worker = EnergyWorker(
            self._database, tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
        )
        self._energy_worker.finished_work.connect(self._on_energy_finished)
        self._energy_worker.error.connect(self._on_energy_error)
        self._energy_worker.start()

    @Slot(object)
    def _on_energy_finished(self, result: dict) -> None:
        """Handle energy analysis completion."""
        self.energy_all_btn.setEnabled(True)
        self.energy_untagged_btn.setEnabled(True)

        analyzed = result["analyzed"]
        failed = result["failed"]
        cached = result.get("cached", 0)
        parts = [f"{analyzed} analyzed"]
        if cached:
            parts.append(f"{cached} cached")
        parts.append(f"{failed} failed")
        self.energy_status.setText(f"Done: {', '.join(parts)}")

        for r in result["results"]:
            self.energy_results.add_result(r)

        if analyzed > 0:
            self.database_changed.emit()

    @Slot(str)
    def _on_energy_error(self, error: str) -> None:
        """Handle energy analysis error."""
        self.energy_all_btn.setEnabled(True)
        self.energy_untagged_btn.setEnabled(True)
        self.energy_status.setText(f"Error: {error}")

    def _on_mik_clicked(self) -> None:
        """Handle MIK import button click."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An analysis is already in progress.")
            return
        if self._database is None:
            return

        tracks = self._get_audio_tracks()
        if not tracks:
            QMessageBox.information(self, "No Tracks", "No tracks to scan.")
            return

        # Auto-backup before modifying
        try:
            from vdj_manager.core.backup import BackupManager
            BackupManager().create_backup(self._database.db_path, label="pre_mik")
        except Exception:
            pass

        self.mik_scan_btn.setEnabled(False)
        self.mik_status.setText("Scanning...")
        self.mik_results.clear()

        self._mik_worker = MIKImportWorker(
            self._database, tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
        )
        self._mik_worker.finished_work.connect(self._on_mik_finished)
        self._mik_worker.error.connect(self._on_mik_error)
        self._mik_worker.start()

    @Slot(object)
    def _on_mik_finished(self, result: dict) -> None:
        """Handle MIK import completion."""
        self.mik_scan_btn.setEnabled(True)

        found = result["found"]
        updated = result["updated"]
        self.mik_status.setText(f"Done: {found} found, {updated} updated")

        for r in result["results"]:
            self.mik_results.add_result(r)

        if updated > 0:
            self.database_changed.emit()

    @Slot(str)
    def _on_mik_error(self, error: str) -> None:
        """Handle MIK import error."""
        self.mik_scan_btn.setEnabled(True)
        self.mik_status.setText(f"Error: {error}")

    def _on_mood_clicked(self) -> None:
        """Handle mood analysis button click."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An analysis is already in progress.")
            return
        if self._database is None:
            return

        tracks = self._get_audio_tracks()
        if not tracks:
            QMessageBox.information(self, "No Tracks", "No tracks to analyze.")
            return

        # Auto-backup before modifying
        try:
            from vdj_manager.core.backup import BackupManager
            BackupManager().create_backup(self._database.db_path, label="pre_mood")
        except Exception:
            pass

        self.mood_btn.setEnabled(False)
        self.mood_status.setText("Analyzing...")
        self.mood_results.clear()

        self._mood_worker = MoodWorker(
            self._database, tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
        )
        self._mood_worker.finished_work.connect(self._on_mood_finished)
        self._mood_worker.error.connect(self._on_mood_error)
        self._mood_worker.start()

    @Slot(object)
    def _on_mood_finished(self, result: dict) -> None:
        """Handle mood analysis completion."""
        self.mood_btn.setEnabled(True)

        if result.get("error"):
            self.mood_status.setText(f"Error: {result['error']}")
            return

        analyzed = result["analyzed"]
        failed = result["failed"]
        cached = result.get("cached", 0)
        parts = [f"{analyzed} analyzed"]
        if cached:
            parts.append(f"{cached} cached")
        parts.append(f"{failed} failed")
        self.mood_status.setText(f"Done: {', '.join(parts)}")

        for r in result["results"]:
            self.mood_results.add_result(r)

        if analyzed > 0:
            self.database_changed.emit()

    @Slot(str)
    def _on_mood_error(self, error: str) -> None:
        """Handle mood analysis error."""
        self.mood_btn.setEnabled(True)
        self.mood_status.setText(f"Error: {error}")
