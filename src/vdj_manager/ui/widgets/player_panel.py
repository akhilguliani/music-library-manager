"""Full-featured player panel (Tab 5)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.player.bridge import PlaybackBridge
from vdj_manager.player.engine import TrackInfo
from vdj_manager.ui.widgets.cue_table_widget import CueTableWidget

if TYPE_CHECKING:
    from vdj_manager.ui.workers.player_workers import WaveformWorker
from vdj_manager.ui.widgets.star_rating_widget import StarRatingWidget
from vdj_manager.ui.widgets.waveform_widget import WaveformWidget


class PlayerPanel(QWidget):
    """Full player tab with metadata, waveform, queue, and history.

    Layout:
    ┌──────────────────────────────────────────────┐
    │ [AlbumArt] Title / Artist  BPM Key Energy    │
    │            [★★★★☆]  Speed: [----slider----]  │
    │ [=============WAVEFORM==================]     │
    ├─────────────────────┬────────────────────────┤
    │ Queue               │ History                │
    │ [list]              │ [list]                 │
    │ [Shuffle][Clear]    │                        │
    │ Repeat: [None/1/All]│                        │
    └─────────────────────┴────────────────────────┘

    Signals:
        rating_changed(str, int): (file_path, rating) when user rates a track.
    """

    rating_changed = Signal(str, int)
    cues_changed = Signal(str, list)

    def __init__(self, bridge: PlaybackBridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._current_track: TrackInfo | None = None
        self._waveform_worker: WaveformWorker | None = None
        self._duration_s = 0.0
        self._syncing_cues = False
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Top: metadata + waveform
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        # Metadata row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)

        # Album art
        self.album_art = QLabel()
        self.album_art.setFixedSize(120, 120)
        self.album_art.setStyleSheet(
            "background-color: #222; border-radius: 6px; color: #555; font-size: 40px;"
        )
        self.album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_art.setText("\u266b")
        meta_row.addWidget(self.album_art)

        # Track info column
        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        self.title_label = QLabel("No track loaded")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #eee;")
        info_col.addWidget(self.title_label)

        self.artist_label = QLabel("")
        self.artist_label.setStyleSheet("font-size: 14px; color: #aaa;")
        info_col.addWidget(self.artist_label)

        # BPM / Key / Energy row
        detail_row = QHBoxLayout()
        detail_row.setSpacing(16)
        self.bpm_label = QLabel("BPM: --")
        self.bpm_label.setStyleSheet("color: #888; font-size: 12px;")
        self.key_label = QLabel("Key: --")
        self.key_label.setStyleSheet("color: #888; font-size: 12px;")
        self.energy_label = QLabel("Energy: --")
        self.energy_label.setStyleSheet("color: #888; font-size: 12px;")
        self.mood_label = QLabel("Mood: --")
        self.mood_label.setStyleSheet("color: #888; font-size: 12px;")
        for lbl in (self.bpm_label, self.key_label, self.energy_label, self.mood_label):
            detail_row.addWidget(lbl)
        detail_row.addStretch()
        info_col.addLayout(detail_row)

        # Star rating
        rating_row = QHBoxLayout()
        rating_row.setSpacing(8)
        rating_lbl = QLabel("Rating:")
        rating_lbl.setStyleSheet("color: #888; font-size: 12px;")
        rating_row.addWidget(rating_lbl)
        self.star_rating = StarRatingWidget()
        self.star_rating.rating_changed.connect(self._on_rating_changed)
        rating_row.addWidget(self.star_rating)
        rating_row.addStretch()
        info_col.addLayout(rating_row)

        info_col.addStretch()
        meta_row.addLayout(info_col, stretch=1)

        # Speed slider column
        speed_col = QVBoxLayout()
        speed_col.setSpacing(4)
        speed_title = QLabel("Speed")
        speed_title.setStyleSheet("color: #888; font-size: 11px;")
        speed_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        speed_col.addWidget(speed_title)

        self.speed_slider = QSlider(Qt.Orientation.Vertical)
        self.speed_slider.setRange(50, 200)  # 0.5x to 2.0x
        self.speed_slider.setValue(100)
        self.speed_slider.setFixedHeight(100)
        self.speed_slider.setToolTip("Playback speed")
        speed_col.addWidget(self.speed_slider, alignment=Qt.AlignmentFlag.AlignCenter)

        self.speed_label = QLabel("1.0x")
        self.speed_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        speed_col.addWidget(self.speed_label)

        reset_speed = QPushButton("Reset")
        reset_speed.setFixedWidth(50)
        reset_speed.setStyleSheet("font-size: 10px; padding: 2px;")
        reset_speed.clicked.connect(lambda: self.speed_slider.setValue(100))
        speed_col.addWidget(reset_speed, alignment=Qt.AlignmentFlag.AlignCenter)

        meta_row.addLayout(speed_col)
        top_layout.addLayout(meta_row)

        # Waveform + Cue Table splitter
        waveform_splitter = QSplitter(Qt.Orientation.Vertical)

        self.waveform = WaveformWidget()
        self.waveform.setMinimumHeight(80)
        waveform_splitter.addWidget(self.waveform)

        self.cue_table = CueTableWidget()
        self.cue_table.setMaximumHeight(200)
        waveform_splitter.addWidget(self.cue_table)

        waveform_splitter.setStretchFactor(0, 3)
        waveform_splitter.setStretchFactor(1, 1)

        top_layout.addWidget(waveform_splitter)

        layout.addWidget(top, stretch=0)

        # Bottom splitter: Queue | History
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Queue panel
        queue_box = QGroupBox("Queue")
        queue_layout = QVBoxLayout(queue_box)

        self.queue_list = QListWidget()
        self.queue_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.queue_list.setStyleSheet("font-size: 12px;")
        queue_layout.addWidget(self.queue_list)

        queue_btns = QHBoxLayout()
        self.shuffle_btn = QPushButton("Shuffle")
        self.shuffle_btn.setToolTip("Shuffle the queue")
        queue_btns.addWidget(self.shuffle_btn)

        self.clear_queue_btn = QPushButton("Clear")
        self.clear_queue_btn.setToolTip("Clear the queue")
        queue_btns.addWidget(self.clear_queue_btn)

        self.repeat_btn = QPushButton("Repeat: Off")
        self.repeat_btn.setToolTip("Cycle repeat mode: Off / One / All")
        queue_btns.addWidget(self.repeat_btn)
        queue_layout.addLayout(queue_btns)

        splitter.addWidget(queue_box)

        # History panel
        history_box = QGroupBox("History")
        history_layout = QVBoxLayout(history_box)
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("font-size: 12px;")
        history_layout.addWidget(self.history_list)
        splitter.addWidget(history_box)

        layout.addWidget(splitter, stretch=1)

    def _connect_signals(self) -> None:
        # Bridge signals
        self._bridge.track_changed.connect(self._on_track_changed)
        self._bridge.position_changed.connect(self._on_position_changed)
        self._bridge.queue_changed.connect(self._on_queue_changed)
        self._bridge.track_finished.connect(self._on_track_finished)
        self._bridge.speed_changed.connect(self._on_speed_changed)

        # Waveform seek and cue editing
        self.waveform.seek_requested.connect(self._bridge.seek)
        self.waveform.cues_changed.connect(self._on_waveform_cues_changed)

        # Cue table editing
        self.cue_table.cues_changed.connect(self._on_cue_table_cues_changed)

        # Speed slider
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)

        # Queue controls
        self.shuffle_btn.clicked.connect(self._bridge.shuffle_queue)
        self.clear_queue_btn.clicked.connect(self._bridge.clear_queue)
        self.repeat_btn.clicked.connect(self._cycle_repeat_mode)

        # Queue double-click to play
        self.queue_list.itemDoubleClicked.connect(self._on_queue_item_double_clicked)

    @Slot(object)
    def _on_track_changed(self, track: TrackInfo) -> None:
        self._current_track = track

        title = track.title or Path(track.file_path).stem
        self.title_label.setText(title)
        self.artist_label.setText(track.artist or "Unknown Artist")

        # Metadata
        if track.bpm and track.bpm > 0:
            self.bpm_label.setText(f"BPM: {track.bpm:.0f}")
        else:
            self.bpm_label.setText("BPM: --")

        self.key_label.setText(f"Key: {track.key}" if track.key else "Key: --")
        self.energy_label.setText(
            f"Energy: {track.energy}" if track.energy is not None else "Energy: --"
        )
        self.mood_label.setText(f"Mood: {track.mood}" if track.mood else "Mood: --")

        # Rating
        self.star_rating.rating = track.rating or 0

        # Album art
        self._load_album_art(track.file_path)

        # Waveform
        self.waveform.clear()
        self._load_waveform(track.file_path)

        # Cue points
        if track.cue_points:
            self.waveform.set_cue_points(track.cue_points)
            self.cue_table.set_cue_points(track.cue_points)
        else:
            self.cue_table.set_cue_points([])

    @Slot(float, float)
    def _on_position_changed(self, pos: float, dur: float) -> None:
        self._duration_s = dur
        self.waveform.set_duration(dur)
        if dur > 0:
            self.waveform.set_position(pos / dur)

    @Slot(list)
    def _on_queue_changed(self, queue: list) -> None:
        self.queue_list.clear()
        for track in queue:
            label = track.title or Path(track.file_path).stem
            if track.artist:
                label = f"{track.artist} - {label}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, track)
            self.queue_list.addItem(item)

    @Slot(object)
    def _on_track_finished(self, track: TrackInfo) -> None:
        """Add finished track to history list."""
        label = track.title or Path(track.file_path).stem
        if track.artist:
            label = f"{track.artist} - {label}"
        self.history_list.insertItem(0, label)
        # Keep history at max 100
        while self.history_list.count() > 100:
            self.history_list.takeItem(self.history_list.count() - 1)

    @Slot(float)
    def _on_speed_changed(self, speed: float) -> None:
        self.speed_label.setText(f"{speed:.1f}x")
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(int(speed * 100))
        self.speed_slider.blockSignals(False)

    def _on_speed_slider_changed(self, value: int) -> None:
        speed = value / 100.0
        self.speed_label.setText(f"{speed:.1f}x")
        self._bridge.set_speed(speed)

    def _on_rating_changed(self, rating: int) -> None:
        if self._current_track:
            self.rating_changed.emit(self._current_track.file_path, rating)

    @Slot(list)
    def _on_waveform_cues_changed(self, cue_dicts: list) -> None:
        """Waveform edited cues — sync to table and persist."""
        if self._syncing_cues:
            return
        self._syncing_cues = True
        self.cue_table.set_cue_points(cue_dicts)
        self._syncing_cues = False
        self._persist_cues(cue_dicts)

    @Slot(list)
    def _on_cue_table_cues_changed(self, cue_dicts: list) -> None:
        """Table edited cues — sync to waveform and persist."""
        if self._syncing_cues:
            return
        self._syncing_cues = True
        self.waveform.set_cue_points(cue_dicts)
        self._syncing_cues = False
        self._persist_cues(cue_dicts)

    def _persist_cues(self, cue_dicts: list) -> None:
        """Update current track and emit cues_changed for database persistence."""
        if self._current_track:
            self._current_track.cue_points = cue_dicts
            self.cues_changed.emit(self._current_track.file_path, cue_dicts)

    def _cycle_repeat_mode(self) -> None:
        """Cycle through repeat modes: none -> one -> all -> none."""
        current = self.repeat_btn.text()
        if "Off" in current:
            self._bridge.set_repeat_mode("one")
            self.repeat_btn.setText("Repeat: One")
        elif "One" in current:
            self._bridge.set_repeat_mode("all")
            self.repeat_btn.setText("Repeat: All")
        else:
            self._bridge.set_repeat_mode("none")
            self.repeat_btn.setText("Repeat: Off")

    def _on_queue_item_double_clicked(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self._bridge.play_track(track)

    def _load_album_art(self, file_path: str) -> None:
        """Load album art in the current thread (fast mutagen read)."""
        try:
            from vdj_manager.player.album_art import extract_album_art

            art_bytes = extract_album_art(file_path)
            if art_bytes:
                img = QImage()
                img.loadFromData(art_bytes)
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img).scaled(
                        120,
                        120,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.album_art.setPixmap(pixmap)
                    self.album_art.setText("")
                    return
        except Exception:
            pass
        self.album_art.clear()
        self.album_art.setText("\u266b")

    def _load_waveform(self, file_path: str) -> None:
        """Load waveform peaks in a background thread."""
        from vdj_manager.ui.workers.player_workers import WaveformWorker

        # Cancel any existing worker
        if self._waveform_worker and self._waveform_worker.isRunning():
            self._waveform_worker.quit()
            self._waveform_worker.wait(1000)

        self._waveform_worker = WaveformWorker(file_path, self.waveform.width() or 800)
        self._waveform_worker.peaks_ready.connect(self._on_waveform_ready)
        self._waveform_worker.error.connect(self._on_waveform_error)
        self._waveform_worker.start()

    @Slot(str, object)
    def _on_waveform_ready(self, file_path: str, peaks) -> None:
        if self._current_track and self._current_track.file_path == file_path:
            self.waveform.set_peaks(peaks)

    @Slot(str, str)
    def _on_waveform_error(self, file_path: str, error: str) -> None:
        pass  # Silently handle — waveform is optional
