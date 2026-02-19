"""Analysis panel with energy, mood, genre, and MIK import sub-tabs."""

import logging
import multiprocessing
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.analysis.analysis_cache import DEFAULT_ANALYSIS_CACHE_PATH
from vdj_manager.config import AUDIO_EXTENSIONS, get_lastfm_api_key
from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.ui.theme import DARK_THEME, ThemeManager
from vdj_manager.ui.widgets.progress_widget import ProgressWidget
from vdj_manager.ui.widgets.results_table import ConfigurableResultsTable
from vdj_manager.ui.workers.analysis_workers import (
    EnergyWorker,
    GenreWorker,
    MIKImportWorker,
    MoodWorker,
)

logger = logging.getLogger(__name__)


class AnalysisPanel(QWidget):
    """Panel for audio analysis operations.

    Provides sub-tabs for:
    - Energy level analysis (1-10 scale)
    - Mood classification
    - Genre detection
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
        self._genre_worker: GenreWorker | None = None
        self._unsaved_count: int = 0

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
        self.mood_reanalyze_btn.setEnabled(has_db)
        self.mood_reanalyze_all_btn.setEnabled(has_db)
        self.genre_btn.setEnabled(has_db)
        self.genre_untagged_btn.setEnabled(has_db)
        self.genre_redetect_btn.setEnabled(has_db)
        self._update_track_info()

    def _setup_ui(self) -> None:
        """Set up the panel UI with sub-tabs."""
        layout = QVBoxLayout(self)

        # Settings bar
        settings_group = QGroupBox("Settings")
        config_layout = QHBoxLayout(settings_group)
        config_layout.setContentsMargins(8, 4, 8, 4)

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
        layout.addWidget(settings_group)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.setTabPosition(QTabWidget.TabPosition.North)

        self._create_energy_tab()
        self._create_mik_tab()
        self._create_mood_tab()
        self._create_genre_tab()

        layout.addWidget(self.sub_tabs)

    def _create_energy_tab(self) -> None:
        """Create the energy analysis sub-tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Info
        self.energy_info_label = QLabel("No database loaded")
        self.energy_info_label.setStyleSheet(f"color: {DARK_THEME.text_tertiary};")
        layout.addWidget(self.energy_info_label)

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
        self.energy_untagged_btn.clicked.connect(
            lambda: self._on_energy_clicked(untagged_only=True)
        )
        controls_layout.addWidget(self.energy_untagged_btn)

        controls_layout.addStretch()

        self.energy_status = QLabel("")
        controls_layout.addWidget(self.energy_status)

        layout.addLayout(controls_layout)

        # Progress widget with pause/resume/cancel
        self.energy_progress = ProgressWidget()
        self.energy_progress.setVisible(False)
        layout.addWidget(self.energy_progress)

        # Results table
        self.energy_results = ConfigurableResultsTable(
            [
                {"name": "Track", "key": "file_path"},
                {"name": "Fmt", "key": "format", "width": 50},
                {"name": "Energy", "key": "energy", "width": 80},
                {"name": "Status", "key": "status", "width": 100},
            ]
        )
        layout.addWidget(self.energy_results)

        self.sub_tabs.addTab(tab, "Energy")

    def _create_mik_tab(self) -> None:
        """Create the MIK import sub-tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Info
        self.mik_info_label = QLabel("No database loaded")
        self.mik_info_label.setStyleSheet(f"color: {DARK_THEME.text_tertiary};")
        layout.addWidget(self.mik_info_label)

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

        # Progress widget with pause/resume/cancel
        self.mik_progress = ProgressWidget()
        self.mik_progress.setVisible(False)
        layout.addWidget(self.mik_progress)

        # Results table
        self.mik_results = ConfigurableResultsTable(
            [
                {"name": "Track", "key": "file_path"},
                {"name": "Fmt", "key": "format", "width": 50},
                {"name": "Energy", "key": "energy", "width": 80},
                {"name": "Key", "key": "key", "width": 100},
                {"name": "Status", "key": "status", "width": 100},
            ]
        )
        layout.addWidget(self.mik_results)

        self.sub_tabs.addTab(tab, "MIK Import")

    def _create_mood_tab(self) -> None:
        """Create the mood analysis sub-tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Info
        self.mood_info_label = QLabel("No database loaded")
        self.mood_info_label.setStyleSheet(f"color: {DARK_THEME.text_tertiary};")
        layout.addWidget(self.mood_info_label)

        # Online mood controls
        online_layout = QHBoxLayout()

        self.mood_online_checkbox = QCheckBox("Enable online lookup (Last.fm / MusicBrainz)")
        self.mood_online_checkbox.setChecked(True)
        self.mood_online_checkbox.setToolTip(
            "Fetch mood from online databases by artist+title before falling back to local analysis"
        )
        self.mood_online_checkbox.stateChanged.connect(lambda _: self._update_track_info())
        online_layout.addWidget(self.mood_online_checkbox)

        self.mood_api_key_label = QLabel("")
        self._update_api_key_label()
        online_layout.addWidget(self.mood_api_key_label)

        online_layout.addStretch()
        layout.addLayout(online_layout)

        # Model settings
        model_layout = QHBoxLayout()

        model_layout.addWidget(QLabel("Model:"))
        self.mood_model_combo = QComboBox()
        self.mood_model_combo.addItem("MTG-Jamendo (recommended)", "mtg-jamendo")
        self.mood_model_combo.addItem("Heuristic (legacy)", "heuristic")
        self.mood_model_combo.setToolTip("Mood analysis model to use")
        model_layout.addWidget(self.mood_model_combo)

        self.mood_threshold_spin = QDoubleSpinBox()
        self.mood_threshold_spin.setRange(0.01, 0.50)
        self.mood_threshold_spin.setSingleStep(0.01)
        self.mood_threshold_spin.setValue(0.10)
        self.mood_threshold_spin.setPrefix("Threshold: ")
        self.mood_threshold_spin.setToolTip(
            "Min confidence to include a mood tag (lower = more tags)"
        )
        model_layout.addWidget(self.mood_threshold_spin)

        self.mood_max_tags_spin = QSpinBox()
        self.mood_max_tags_spin.setRange(1, 10)
        self.mood_max_tags_spin.setValue(5)
        self.mood_max_tags_spin.setPrefix("Max tags: ")
        self.mood_max_tags_spin.setToolTip("Maximum number of mood tags per track")
        model_layout.addWidget(self.mood_max_tags_spin)

        model_layout.addStretch()
        layout.addLayout(model_layout)

        # Controls
        controls_layout = QHBoxLayout()

        self.mood_btn = QPushButton("Analyze Mood")
        self.mood_btn.setEnabled(False)
        self.mood_btn.setToolTip("Analyze mood/emotion for audio tracks")
        self.mood_btn.clicked.connect(self._on_mood_clicked)
        controls_layout.addWidget(self.mood_btn)

        self.mood_reanalyze_btn = QPushButton("Re-analyze Unknown")
        self.mood_reanalyze_btn.setEnabled(False)
        self.mood_reanalyze_btn.setToolTip("Re-analyze tracks tagged #unknown using online lookup")
        self.mood_reanalyze_btn.clicked.connect(self._on_mood_reanalyze_clicked)
        controls_layout.addWidget(self.mood_reanalyze_btn)

        self.mood_reanalyze_all_btn = QPushButton("Re-analyze All")
        self.mood_reanalyze_all_btn.setEnabled(False)
        self.mood_reanalyze_all_btn.setToolTip(
            "Invalidate mood cache and re-analyze all tracks with the selected model"
        )
        self.mood_reanalyze_all_btn.clicked.connect(self._on_mood_reanalyze_all_clicked)
        controls_layout.addWidget(self.mood_reanalyze_all_btn)

        controls_layout.addStretch()

        self.mood_status = QLabel("")
        controls_layout.addWidget(self.mood_status)

        layout.addLayout(controls_layout)

        # Progress widget with pause/resume/cancel
        self.mood_progress = ProgressWidget()
        self.mood_progress.setVisible(False)
        layout.addWidget(self.mood_progress)

        # Results table
        self.mood_results = ConfigurableResultsTable(
            [
                {"name": "Track", "key": "file_path"},
                {"name": "Fmt", "key": "format", "width": 50},
                {"name": "Mood", "key": "mood", "width": 120},
                {"name": "Status", "key": "status", "width": 100},
            ]
        )
        layout.addWidget(self.mood_results)

        self.sub_tabs.addTab(tab, "Mood")

    def _create_genre_tab(self) -> None:
        """Create the genre detection sub-tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Info
        self.genre_info_label = QLabel("No database loaded")
        self.genre_info_label.setStyleSheet(f"color: {DARK_THEME.text_tertiary};")
        layout.addWidget(self.genre_info_label)

        # Online toggle
        online_layout = QHBoxLayout()
        self.genre_online_checkbox = QCheckBox("Enable online lookup (Last.fm / MusicBrainz)")
        self.genre_online_checkbox.setChecked(True)
        self.genre_online_checkbox.setToolTip(
            "Look up genre from online databases by artist+title when file tags are empty"
        )
        self.genre_online_checkbox.stateChanged.connect(lambda _: self._update_track_info())
        online_layout.addWidget(self.genre_online_checkbox)

        self.genre_api_key_label = QLabel("")
        self._update_genre_api_key_label()
        online_layout.addWidget(self.genre_api_key_label)

        online_layout.addStretch()
        layout.addLayout(online_layout)

        # Controls
        controls_layout = QHBoxLayout()

        self.genre_btn = QPushButton("Detect Genre")
        self.genre_btn.setEnabled(False)
        self.genre_btn.setToolTip("Detect genre for all audio tracks")
        self.genre_btn.clicked.connect(lambda: self._on_genre_clicked(untagged_only=False))
        controls_layout.addWidget(self.genre_btn)

        self.genre_untagged_btn = QPushButton("Untagged Only")
        self.genre_untagged_btn.setEnabled(False)
        self.genre_untagged_btn.setToolTip("Only detect genre for tracks without genre tags")
        self.genre_untagged_btn.clicked.connect(lambda: self._on_genre_clicked(untagged_only=True))
        controls_layout.addWidget(self.genre_untagged_btn)

        self.genre_redetect_btn = QPushButton("Re-detect All")
        self.genre_redetect_btn.setEnabled(False)
        self.genre_redetect_btn.setToolTip("Invalidate genre cache and re-detect all tracks")
        self.genre_redetect_btn.clicked.connect(self._on_genre_redetect_all_clicked)
        controls_layout.addWidget(self.genre_redetect_btn)

        controls_layout.addStretch()

        self.genre_status = QLabel("")
        controls_layout.addWidget(self.genre_status)

        layout.addLayout(controls_layout)

        # Progress widget with pause/resume/cancel
        self.genre_progress = ProgressWidget()
        self.genre_progress.setVisible(False)
        layout.addWidget(self.genre_progress)

        # Results table
        self.genre_results = ConfigurableResultsTable(
            [
                {"name": "Track", "key": "file_path"},
                {"name": "Fmt", "key": "format", "width": 50},
                {"name": "Genre", "key": "genre", "width": 120},
                {"name": "Source", "key": "source", "width": 80},
                {"name": "Status", "key": "status", "width": 100},
            ]
        )
        layout.addWidget(self.genre_results)

        self.sub_tabs.addTab(tab, "Genre")

    def _update_genre_api_key_label(self) -> None:
        """Update the Last.fm API key status label for the genre tab."""
        tm = ThemeManager()
        key = get_lastfm_api_key()
        if key:
            self.genre_api_key_label.setText("API key: configured")
            self.genre_api_key_label.setStyleSheet(
                f"color: {tm.status_color('success')}; font-size: 11px;"
            )
        else:
            self.genre_api_key_label.setText("API key: not set (set LASTFM_API_KEY env var)")
            self.genre_api_key_label.setStyleSheet(
                f"color: {tm.status_color('warning')}; font-size: 11px;"
            )

    def _update_api_key_label(self) -> None:
        """Update the Last.fm API key status label."""
        tm = ThemeManager()
        key = get_lastfm_api_key()
        if key:
            self.mood_api_key_label.setText("API key: configured")
            self.mood_api_key_label.setStyleSheet(
                f"color: {tm.status_color('success')}; font-size: 11px;"
            )
        else:
            self.mood_api_key_label.setText("API key: not set (set LASTFM_API_KEY env var)")
            self.mood_api_key_label.setStyleSheet(
                f"color: {tm.status_color('warning')}; font-size: 11px;"
            )

    def _update_track_info(self) -> None:
        """Update track info labels across all tabs."""
        if not self._tracks:
            for label in (
                self.energy_info_label,
                self.mik_info_label,
                self.mood_info_label,
                self.genre_info_label,
            ):
                label.setText("No database loaded")
            return

        audio_tracks = self._get_audio_tracks()
        local = [t for t in audio_tracks if not t.is_windows_path]
        remote = [t for t in audio_tracks if t.is_windows_path]
        untagged = [t for t in audio_tracks if t.energy is None]

        if remote:
            self.energy_info_label.setText(
                f"{len(audio_tracks)} tracks ({len(local)} local, {len(remote)} remote), "
                f"{len(untagged)} without energy"
            )
            self.mik_info_label.setText(
                f"{len(audio_tracks)} tracks ({len(local)} local, {len(remote)} remote) to scan"
            )
        else:
            self.energy_info_label.setText(
                f"{len(audio_tracks)} audio tracks, {len(untagged)} without energy tags"
            )
            self.mik_info_label.setText(f"{len(audio_tracks)} audio tracks to scan")

        mood_tracks = self._get_mood_tracks()
        mood_local = [t for t in mood_tracks if not t.is_windows_path]
        mood_remote = [t for t in mood_tracks if t.is_windows_path]
        unknown_mood = [
            t
            for t in mood_tracks
            if t.tags and t.tags.user2 and "#unknown" in (t.tags.user2 or "").split()
        ]
        if mood_remote:
            self.mood_info_label.setText(
                f"{len(mood_tracks)} tracks ({len(mood_local)} local, {len(mood_remote)} remote), "
                f"{len(unknown_mood)} with #unknown mood"
            )
        else:
            self.mood_info_label.setText(
                f"{len(mood_tracks)} eligible tracks, {len(unknown_mood)} with #unknown mood"
            )

        genre_tracks = self._get_genre_tracks()
        genre_local = [t for t in genre_tracks if not t.is_windows_path]
        genre_remote = [t for t in genre_tracks if t.is_windows_path]
        no_genre = [t for t in genre_tracks if not (t.tags and t.tags.genre)]
        if genre_remote:
            self.genre_info_label.setText(
                f"{len(genre_tracks)} tracks ({len(genre_local)} local, "
                f"{len(genre_remote)} remote), {len(no_genre)} without genre"
            )
        else:
            self.genre_info_label.setText(
                f"{len(genre_tracks)} eligible tracks, {len(no_genre)} without genre"
            )

    def _get_audio_tracks(self, untagged_only: bool = False) -> list[Song]:
        """Get filterable audio tracks, respecting duration and count limits.

        Args:
            untagged_only: If True, only return tracks without energy tags.

        Returns:
            List of Song objects.
        """
        tracks = []
        for track in self._tracks:
            if track.is_netsearch:
                continue
            if track.extension not in AUDIO_EXTENSIONS:
                continue
            if untagged_only and track.energy is not None:
                continue
            if not track.is_windows_path and not Path(track.file_path).exists():
                continue
            tracks.append(track)

        # Duration filter (minutes -> seconds); tracks without metadata are kept
        max_duration = self.max_duration_spin.value() * 60
        if max_duration > 0:
            tracks = [
                t
                for t in tracks
                if not (t.infos and t.infos.song_length and t.infos.song_length > max_duration)
            ]

        # Count limit
        limit = self.limit_spin.value()
        if limit > 0:
            tracks = tracks[:limit]

        return tracks

    def _get_mood_tracks(self) -> list:
        """Get tracks eligible for mood analysis.

        Unlike _get_audio_tracks, includes Windows-path tracks when online
        mode is enabled since online lookup only needs artist/title metadata.
        """
        tracks = []
        for track in self._tracks:
            if track.is_netsearch:
                continue
            if track.extension not in AUDIO_EXTENSIONS:
                continue
            file_exists = not track.is_windows_path and Path(track.file_path).exists()
            has_metadata = track.tags and (track.tags.author or track.tags.title)
            if not file_exists and not has_metadata and not track.is_windows_path:
                continue
            tracks.append(track)

        # Duration filter
        max_duration = self.max_duration_spin.value() * 60
        if max_duration > 0:
            tracks = [
                t
                for t in tracks
                if not (t.infos and t.infos.song_length and t.infos.song_length > max_duration)
            ]

        # Count limit
        limit = self.limit_spin.value()
        if limit > 0:
            tracks = tracks[:limit]

        return tracks

    def _get_genre_tracks(self, untagged_only: bool = False) -> list[Song]:
        """Get tracks eligible for genre detection.

        Like _get_mood_tracks, includes Windows-path tracks when online
        mode is enabled since online lookup only needs artist/title metadata.

        Args:
            untagged_only: If True, only return tracks without genre tags.

        Returns:
            List of Song objects.
        """
        tracks = []
        for track in self._tracks:
            if track.is_netsearch:
                continue
            if track.extension not in AUDIO_EXTENSIONS:
                continue
            if untagged_only and track.tags and track.tags.genre:
                continue
            file_exists = not track.is_windows_path and Path(track.file_path).exists()
            has_metadata = track.tags and (track.tags.author or track.tags.title)
            if not file_exists and not has_metadata and not track.is_windows_path:
                continue
            tracks.append(track)

        # Duration filter
        max_duration = self.max_duration_spin.value() * 60
        if max_duration > 0:
            tracks = [
                t
                for t in tracks
                if not (t.infos and t.infos.song_length and t.infos.song_length > max_duration)
            ]

        # Count limit
        limit = self.limit_spin.value()
        if limit > 0:
            tracks = tracks[:limit]

        return tracks

    def is_running(self) -> bool:
        """Check if any analysis operation is currently running."""
        for worker in (
            self._energy_worker,
            self._mik_worker,
            self._mood_worker,
            self._genre_worker,
        ):
            if worker is not None and worker.isRunning():
                return True
        return False

    # ------------------------------------------------------------------
    # Energy handlers
    # ------------------------------------------------------------------

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
            logger.warning("Auto-backup failed before analysis", exc_info=True)

        self.energy_all_btn.setEnabled(False)
        self.energy_untagged_btn.setEnabled(False)
        self.energy_status.setText("Analyzing...")
        self.energy_results.clear()

        self._energy_worker = EnergyWorker(
            tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
        )
        self._energy_worker.finished_work.connect(self._on_energy_finished)
        self._energy_worker.error.connect(self._on_energy_error)
        self._energy_worker.result_ready.connect(self.energy_results.add_result)
        self._energy_worker.result_ready.connect(self._apply_result_to_db)

        # Set up progress widget
        self.energy_progress.reset()
        self.energy_progress.start(len(tracks))
        self.energy_progress.setVisible(True)
        self._energy_worker.progress.connect(self.energy_progress.update_progress)
        self._energy_worker.status_changed.connect(self.energy_progress.on_status_changed)
        self._energy_worker.finished_work.connect(
            lambda _: self.energy_progress.on_finished(True, "Done")
        )
        self.energy_progress.pause_requested.connect(self._energy_worker.pause)
        self.energy_progress.resume_requested.connect(self._energy_worker.resume)
        self.energy_progress.cancel_requested.connect(self._energy_worker.cancel)

        self._energy_worker.start()

    # ------------------------------------------------------------------
    # Main-thread DB mutation handler
    # ------------------------------------------------------------------

    @Slot(dict)
    def _apply_result_to_db(self, result: dict) -> None:
        """Apply tag updates from a worker result to the database.

        Called on the main thread via signal connection, ensuring
        VDJDatabase is never mutated from a worker QThread.

        Only updates in-memory state here; disk save is deferred to
        ``_save_if_needed()`` which is called once when the worker
        finishes, avoiding redundant I/O during batch processing.
        """
        tag_updates = result.get("tag_updates")
        if not tag_updates or self._database is None:
            return
        self._database.update_song_tags(result["file_path"], **tag_updates)
        self._unsaved_count += 1

    def _save_if_needed(self) -> None:
        """Save database if there are pending changes."""
        if self._unsaved_count > 0 and self._database is not None:
            self._database.save()
            self._unsaved_count = 0

    @staticmethod
    def _format_failure_summary(results: list[dict], failed_count: int) -> str:
        """Build a failure breakdown by format, e.g. '(.flac: 2, .wav: 1)'."""
        if failed_count == 0:
            return ""
        from collections import Counter

        fmt_counts: Counter[str] = Counter()
        for r in results:
            status = str(r.get("status", "")).lower()
            if status in ("failed", "none") or status.startswith("error"):
                fmt_counts[r.get("format", "?")] += 1
        if not fmt_counts:
            return ""
        breakdown = ", ".join(f"{fmt}: {cnt}" for fmt, cnt in fmt_counts.most_common())
        return f" ({breakdown})"

    @Slot(object)
    def _on_energy_finished(self, result: dict) -> None:
        """Handle energy analysis completion."""
        self._save_if_needed()
        self.energy_all_btn.setEnabled(True)
        self.energy_untagged_btn.setEnabled(True)

        analyzed = result["analyzed"]
        failed = result["failed"]
        cached = result.get("cached", 0)
        parts = [f"{analyzed} analyzed"]
        if cached:
            parts.append(f"{cached} cached")
        parts.append(f"{failed} failed")
        summary = f"Done: {', '.join(parts)}"
        summary += self._format_failure_summary(result.get("results", []), failed)
        self.energy_status.setText(summary)

        if analyzed + cached > 0:
            self.database_changed.emit()

    @Slot(str)
    def _on_energy_error(self, error: str) -> None:
        """Handle energy analysis error."""
        self.energy_all_btn.setEnabled(True)
        self.energy_untagged_btn.setEnabled(True)
        self.energy_status.setText(f"Error: {error}")

    # ------------------------------------------------------------------
    # MIK handlers
    # ------------------------------------------------------------------

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
            logger.warning("Auto-backup failed before analysis", exc_info=True)

        self.mik_scan_btn.setEnabled(False)
        self.mik_status.setText("Scanning...")
        self.mik_results.clear()

        self._mik_worker = MIKImportWorker(
            tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
        )
        self._mik_worker.finished_work.connect(self._on_mik_finished)
        self._mik_worker.error.connect(self._on_mik_error)
        self._mik_worker.result_ready.connect(self.mik_results.add_result)
        self._mik_worker.result_ready.connect(self._apply_result_to_db)

        # Set up progress widget
        self.mik_progress.reset()
        self.mik_progress.start(len(tracks))
        self.mik_progress.setVisible(True)
        self._mik_worker.progress.connect(self.mik_progress.update_progress)
        self._mik_worker.status_changed.connect(self.mik_progress.on_status_changed)
        self._mik_worker.finished_work.connect(
            lambda _: self.mik_progress.on_finished(True, "Done")
        )
        self.mik_progress.pause_requested.connect(self._mik_worker.pause)
        self.mik_progress.resume_requested.connect(self._mik_worker.resume)
        self.mik_progress.cancel_requested.connect(self._mik_worker.cancel)

        self._mik_worker.start()

    @Slot(object)
    def _on_mik_finished(self, result: dict) -> None:
        """Handle MIK import completion."""
        self._save_if_needed()
        self.mik_scan_btn.setEnabled(True)

        found = result["found"]
        updated = result["updated"]
        self.mik_status.setText(f"Done: {found} found, {updated} updated")

        if updated > 0:
            self.database_changed.emit()

    @Slot(str)
    def _on_mik_error(self, error: str) -> None:
        """Handle MIK import error."""
        self.mik_scan_btn.setEnabled(True)
        self.mik_status.setText(f"Error: {error}")

    # ------------------------------------------------------------------
    # Mood handlers
    # ------------------------------------------------------------------

    def _on_mood_clicked(self) -> None:
        """Handle mood analysis button click."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An analysis is already in progress.")
            return
        if self._database is None:
            return

        tracks = self._get_mood_tracks()
        if not tracks:
            QMessageBox.information(self, "No Tracks", "No tracks to analyze.")
            return

        # Auto-backup before modifying
        try:
            from vdj_manager.core.backup import BackupManager

            BackupManager().create_backup(self._database.db_path, label="pre_mood")
        except Exception:
            logger.warning("Auto-backup failed before analysis", exc_info=True)

        self.mood_btn.setEnabled(False)
        self.mood_status.setText("Analyzing...")
        self.mood_results.clear()

        enable_online = self.mood_online_checkbox.isChecked()
        lastfm_api_key = get_lastfm_api_key() if enable_online else None

        model_name = self.mood_model_combo.currentData()
        threshold = self.mood_threshold_spin.value()
        max_tags = self.mood_max_tags_spin.value()

        self._mood_worker = MoodWorker(
            tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
            enable_online=enable_online,
            lastfm_api_key=lastfm_api_key,
            model_name=model_name,
            threshold=threshold,
            max_tags=max_tags,
        )
        self._mood_worker.finished_work.connect(self._on_mood_finished)
        self._mood_worker.error.connect(self._on_mood_error)
        self._mood_worker.result_ready.connect(self.mood_results.add_result)
        self._mood_worker.result_ready.connect(self._apply_result_to_db)

        # Set up progress widget
        self.mood_progress.reset()
        self.mood_progress.start(len(tracks))
        self.mood_progress.setVisible(True)
        self._mood_worker.progress.connect(self.mood_progress.update_progress)
        self._mood_worker.status_changed.connect(self.mood_progress.on_status_changed)
        self._mood_worker.finished_work.connect(
            lambda _: self.mood_progress.on_finished(True, "Done")
        )
        self.mood_progress.pause_requested.connect(self._mood_worker.pause)
        self.mood_progress.resume_requested.connect(self._mood_worker.resume)
        self.mood_progress.cancel_requested.connect(self._mood_worker.cancel)

        self._mood_worker.start()

    def _on_mood_reanalyze_clicked(self) -> None:
        """Re-analyze tracks with #unknown mood using online lookup."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An analysis is already in progress.")
            return
        if self._database is None:
            return

        # Filter to tracks with #unknown in User2
        all_tracks = self._get_mood_tracks()
        tracks = [
            t
            for t in all_tracks
            if t.tags and t.tags.user2 and "#unknown" in (t.tags.user2 or "").split()
        ]
        if not tracks:
            QMessageBox.information(
                self, "No Unknown Tracks", "No tracks with #unknown mood tag found."
            )
            return

        # Auto-backup
        try:
            from vdj_manager.core.backup import BackupManager

            BackupManager().create_backup(self._database.db_path, label="pre_mood_reanalyze")
        except Exception:
            logger.warning("Auto-backup failed before analysis", exc_info=True)

        self.mood_btn.setEnabled(False)
        self.mood_reanalyze_btn.setEnabled(False)
        self.mood_status.setText(f"Re-analyzing {len(tracks)} unknown tracks...")
        self.mood_results.clear()

        lastfm_api_key = get_lastfm_api_key()

        model_name = self.mood_model_combo.currentData()
        threshold = self.mood_threshold_spin.value()
        max_tags = self.mood_max_tags_spin.value()

        self._mood_worker = MoodWorker(
            tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
            enable_online=True,
            lastfm_api_key=lastfm_api_key,
            skip_cache=True,
            model_name=model_name,
            threshold=threshold,
            max_tags=max_tags,
        )
        self._mood_worker.finished_work.connect(self._on_mood_finished)
        self._mood_worker.error.connect(self._on_mood_error)
        self._mood_worker.result_ready.connect(self.mood_results.add_result)
        self._mood_worker.result_ready.connect(self._apply_result_to_db)

        # Set up progress widget
        self.mood_progress.reset()
        self.mood_progress.start(len(tracks))
        self.mood_progress.setVisible(True)
        self._mood_worker.progress.connect(self.mood_progress.update_progress)
        self._mood_worker.status_changed.connect(self.mood_progress.on_status_changed)
        self._mood_worker.finished_work.connect(
            lambda _: self.mood_progress.on_finished(True, "Done")
        )
        self.mood_progress.pause_requested.connect(self._mood_worker.pause)
        self.mood_progress.resume_requested.connect(self._mood_worker.resume)
        self.mood_progress.cancel_requested.connect(self._mood_worker.cancel)

        self._mood_worker.start()

    def _on_mood_reanalyze_all_clicked(self) -> None:
        """Re-analyze ALL tracks, invalidating mood cache first."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An analysis is already in progress.")
            return
        if self._database is None:
            return

        tracks = self._get_mood_tracks()
        if not tracks:
            QMessageBox.information(self, "No Tracks", "No tracks to analyze.")
            return

        reply = QMessageBox.question(
            self,
            "Re-analyze All",
            f"This will re-analyze mood for all {len(tracks)} audio tracks, "
            "invalidating existing mood cache.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Invalidate all mood cache entries
        from vdj_manager.analysis.analysis_cache import AnalysisCache

        cache = AnalysisCache(db_path=DEFAULT_ANALYSIS_CACHE_PATH)
        cache.invalidate_by_type_prefix("mood:")

        # Auto-backup
        try:
            from vdj_manager.core.backup import BackupManager

            BackupManager().create_backup(self._database.db_path, label="pre_mood_reanalyze_all")
        except Exception:
            logger.warning("Auto-backup failed before analysis", exc_info=True)

        self.mood_btn.setEnabled(False)
        self.mood_reanalyze_btn.setEnabled(False)
        self.mood_reanalyze_all_btn.setEnabled(False)
        self.mood_status.setText(f"Re-analyzing all {len(tracks)} tracks...")
        self.mood_results.clear()

        model_name = self.mood_model_combo.currentData()
        threshold = self.mood_threshold_spin.value()
        max_tags = self.mood_max_tags_spin.value()
        enable_online = self.mood_online_checkbox.isChecked()
        lastfm_api_key = get_lastfm_api_key() if enable_online else None

        self._mood_worker = MoodWorker(
            tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
            enable_online=enable_online,
            lastfm_api_key=lastfm_api_key,
            skip_cache=True,
            model_name=model_name,
            threshold=threshold,
            max_tags=max_tags,
        )
        self._mood_worker.finished_work.connect(self._on_mood_finished)
        self._mood_worker.error.connect(self._on_mood_error)
        self._mood_worker.result_ready.connect(self.mood_results.add_result)
        self._mood_worker.result_ready.connect(self._apply_result_to_db)

        self.mood_progress.reset()
        self.mood_progress.start(len(tracks))
        self.mood_progress.setVisible(True)
        self._mood_worker.progress.connect(self.mood_progress.update_progress)
        self._mood_worker.status_changed.connect(self.mood_progress.on_status_changed)
        self._mood_worker.finished_work.connect(
            lambda _: self.mood_progress.on_finished(True, "Done")
        )
        self.mood_progress.pause_requested.connect(self._mood_worker.pause)
        self.mood_progress.resume_requested.connect(self._mood_worker.resume)
        self.mood_progress.cancel_requested.connect(self._mood_worker.cancel)

        self._mood_worker.start()

    @Slot(object)
    def _on_mood_finished(self, result: dict) -> None:
        """Handle mood analysis completion."""
        self._save_if_needed()
        self.mood_btn.setEnabled(True)
        self.mood_reanalyze_btn.setEnabled(True)
        self.mood_reanalyze_all_btn.setEnabled(True)

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
        summary = f"Done: {', '.join(parts)}"
        summary += self._format_failure_summary(result.get("results", []), failed)
        self.mood_status.setText(summary)

        if analyzed + cached > 0:
            self.database_changed.emit()

    @Slot(str)
    def _on_mood_error(self, error: str) -> None:
        """Handle mood analysis error."""
        self.mood_btn.setEnabled(True)
        self.mood_reanalyze_btn.setEnabled(True)
        self.mood_reanalyze_all_btn.setEnabled(True)
        self.mood_status.setText(f"Error: {error}")

    # ------------------------------------------------------------------
    # Genre handlers
    # ------------------------------------------------------------------

    def _on_genre_clicked(self, untagged_only: bool = False) -> None:
        """Handle genre detection button click."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An analysis is already in progress.")
            return
        if self._database is None:
            return

        tracks = self._get_genre_tracks(untagged_only=untagged_only)
        if not tracks:
            QMessageBox.information(self, "No Tracks", "No tracks to analyze.")
            return

        # Auto-backup before modifying
        try:
            from vdj_manager.core.backup import BackupManager

            BackupManager().create_backup(self._database.db_path, label="pre_genre")
        except Exception:
            logger.warning("Auto-backup failed before analysis", exc_info=True)

        self.genre_btn.setEnabled(False)
        self.genre_untagged_btn.setEnabled(False)
        self.genre_redetect_btn.setEnabled(False)
        self.genre_status.setText("Detecting...")
        self.genre_results.clear()

        enable_online = self.genre_online_checkbox.isChecked()
        lastfm_api_key = get_lastfm_api_key() if enable_online else None

        self._genre_worker = GenreWorker(
            tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
            enable_online=enable_online,
            lastfm_api_key=lastfm_api_key,
        )
        self._genre_worker.finished_work.connect(self._on_genre_finished)
        self._genre_worker.error.connect(self._on_genre_error)
        self._genre_worker.result_ready.connect(self.genre_results.add_result)
        self._genre_worker.result_ready.connect(self._apply_result_to_db)

        # Set up progress widget
        self.genre_progress.reset()
        self.genre_progress.start(len(tracks))
        self.genre_progress.setVisible(True)
        self._genre_worker.progress.connect(self.genre_progress.update_progress)
        self._genre_worker.status_changed.connect(self.genre_progress.on_status_changed)
        self._genre_worker.finished_work.connect(
            lambda _: self.genre_progress.on_finished(True, "Done")
        )
        self.genre_progress.pause_requested.connect(self._genre_worker.pause)
        self.genre_progress.resume_requested.connect(self._genre_worker.resume)
        self.genre_progress.cancel_requested.connect(self._genre_worker.cancel)

        self._genre_worker.start()

    def _on_genre_redetect_all_clicked(self) -> None:
        """Re-detect genre for ALL tracks, invalidating genre cache first."""
        if self.is_running():
            QMessageBox.warning(self, "Already Running", "An analysis is already in progress.")
            return
        if self._database is None:
            return

        tracks = self._get_genre_tracks()
        if not tracks:
            QMessageBox.information(self, "No Tracks", "No tracks to analyze.")
            return

        reply = QMessageBox.question(
            self,
            "Re-detect All",
            f"This will re-detect genre for all {len(tracks)} audio tracks, "
            "invalidating existing genre cache.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Invalidate all genre cache entries
        from vdj_manager.analysis.analysis_cache import AnalysisCache

        cache = AnalysisCache(db_path=DEFAULT_ANALYSIS_CACHE_PATH)
        cache.invalidate_by_type("genre")

        # Auto-backup
        try:
            from vdj_manager.core.backup import BackupManager

            BackupManager().create_backup(self._database.db_path, label="pre_genre_redetect")
        except Exception:
            logger.warning("Auto-backup failed before analysis", exc_info=True)

        self.genre_btn.setEnabled(False)
        self.genre_untagged_btn.setEnabled(False)
        self.genre_redetect_btn.setEnabled(False)
        self.genre_status.setText(f"Re-detecting all {len(tracks)} tracks...")
        self.genre_results.clear()

        enable_online = self.genre_online_checkbox.isChecked()
        lastfm_api_key = get_lastfm_api_key() if enable_online else None

        self._genre_worker = GenreWorker(
            tracks,
            max_workers=self.workers_spin.value(),
            cache_db_path=str(DEFAULT_ANALYSIS_CACHE_PATH),
            enable_online=enable_online,
            lastfm_api_key=lastfm_api_key,
            skip_cache=True,
        )
        self._genre_worker.finished_work.connect(self._on_genre_finished)
        self._genre_worker.error.connect(self._on_genre_error)
        self._genre_worker.result_ready.connect(self.genre_results.add_result)
        self._genre_worker.result_ready.connect(self._apply_result_to_db)

        self.genre_progress.reset()
        self.genre_progress.start(len(tracks))
        self.genre_progress.setVisible(True)
        self._genre_worker.progress.connect(self.genre_progress.update_progress)
        self._genre_worker.status_changed.connect(self.genre_progress.on_status_changed)
        self._genre_worker.finished_work.connect(
            lambda _: self.genre_progress.on_finished(True, "Done")
        )
        self.genre_progress.pause_requested.connect(self._genre_worker.pause)
        self.genre_progress.resume_requested.connect(self._genre_worker.resume)
        self.genre_progress.cancel_requested.connect(self._genre_worker.cancel)

        self._genre_worker.start()

    @Slot(object)
    def _on_genre_finished(self, result: dict) -> None:
        """Handle genre detection completion."""
        self._save_if_needed()
        self.genre_btn.setEnabled(True)
        self.genre_untagged_btn.setEnabled(True)
        self.genre_redetect_btn.setEnabled(True)

        analyzed = result["analyzed"]
        failed = result["failed"]
        cached = result.get("cached", 0)
        parts = [f"{analyzed} detected"]
        if cached:
            parts.append(f"{cached} cached")
        parts.append(f"{failed} failed")
        summary = f"Done: {', '.join(parts)}"
        summary += self._format_failure_summary(result.get("results", []), failed)
        self.genre_status.setText(summary)

        if analyzed + cached > 0:
            self.database_changed.emit()

    @Slot(str)
    def _on_genre_error(self, error: str) -> None:
        """Handle genre detection error."""
        self.genre_btn.setEnabled(True)
        self.genre_untagged_btn.setEnabled(True)
        self.genre_redetect_btn.setEnabled(True)
        self.genre_status.setText(f"Error: {error}")
