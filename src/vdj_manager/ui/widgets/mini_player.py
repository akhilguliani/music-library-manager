"""Always-visible mini player widget for the bottom of MainWindow."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.player.bridge import PlaybackBridge
from vdj_manager.player.engine import TrackInfo
from vdj_manager.ui.theme import DARK_THEME


class MiniPlayer(QWidget):
    """Compact player bar shown at bottom of MainWindow.

    Layout:
    [AlbumArt] [Title/Artist] [<<][Play/Pause][>>] [ProgressSlider] [Time] [Volume] [^]

    Signals:
        expand_requested: User clicked expand button to open Player tab.
    """

    expand_requested = Signal()

    def __init__(self, bridge: PlaybackBridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._duration_s = 0.0
        self._seeking = False
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        self.setFixedHeight(60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Album art placeholder
        self.album_art = QLabel()
        self.album_art.setFixedSize(44, 44)
        self.album_art.setStyleSheet(
            f"background-color: {DARK_THEME.bg_surface_alt}; border-radius: 4px; "
            f"color: {DARK_THEME.text_muted}; font-size: 20px;"
        )
        self.album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_art.setText("\u266b")  # Musical note
        layout.addWidget(self.album_art)

        # Track info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(0)
        info_layout.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("No track loaded")
        font = self.title_label.font()
        font.setBold(True)
        font.setPointSize(12)
        self.title_label.setFont(font)
        self.title_label.setMaximumWidth(200)
        self.artist_label = QLabel("")
        font = self.artist_label.font()
        font.setPointSize(10)
        self.artist_label.setFont(font)
        self.artist_label.setStyleSheet(f"color: {DARK_THEME.text_secondary};")
        self.artist_label.setMaximumWidth(200)
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.artist_label)
        layout.addLayout(info_layout)

        layout.addStretch()

        # Transport controls
        self.prev_btn = QPushButton("\u23ee")  # Previous
        self.prev_btn.setFixedSize(36, 28)
        self.prev_btn.setToolTip("Previous track")
        layout.addWidget(self.prev_btn)

        self.play_btn = QPushButton("\u25b6")  # Play
        self.play_btn.setFixedSize(40, 28)
        self.play_btn.setToolTip("Play / Pause")
        layout.addWidget(self.play_btn)

        self.next_btn = QPushButton("\u23ed")  # Next
        self.next_btn.setFixedSize(36, 28)
        self.next_btn.setToolTip("Next track")
        layout.addWidget(self.next_btn)

        # Progress slider
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setMinimumWidth(200)
        self.progress_slider.setToolTip("Seek")
        layout.addWidget(self.progress_slider, stretch=1)

        # Time display
        self.time_label = QLabel("0:00 / 0:00")
        font = self.time_label.font()
        font.setPointSize(11)
        self.time_label.setFont(font)
        self.time_label.setMinimumWidth(85)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_label)

        # Volume slider
        vol_label = QLabel("\U0001f50a")  # Speaker emoji
        font = vol_label.font()
        font.setPointSize(14)
        vol_label.setFont(font)
        layout.addWidget(vol_label)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setToolTip("Volume")
        layout.addWidget(self.volume_slider)

        # Expand button
        self.expand_btn = QPushButton("\u25b2")  # Up arrow
        self.expand_btn.setFixedSize(28, 28)
        self.expand_btn.setToolTip("Open full player")
        layout.addWidget(self.expand_btn)

    def _connect_signals(self) -> None:
        self._bridge.state_changed.connect(self._on_state_changed)
        self._bridge.track_changed.connect(self._on_track_changed)
        self._bridge.position_changed.connect(self._on_position_changed)
        self._bridge.volume_changed.connect(self._on_volume_changed)

        self.play_btn.clicked.connect(self._bridge.toggle_play_pause)
        self.next_btn.clicked.connect(self._bridge.next_track)
        self.prev_btn.clicked.connect(self._bridge.previous_track)
        self.volume_slider.valueChanged.connect(self._bridge.set_volume)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        self.expand_btn.clicked.connect(self.expand_requested)

    def set_vlc_unavailable(self) -> None:
        """Disable controls when VLC is not available."""
        self.title_label.setText("VLC not found")
        self.artist_label.setText("Install VLC to enable playback")
        for btn in (self.prev_btn, self.play_btn, self.next_btn):
            btn.setEnabled(False)
        self.progress_slider.setEnabled(False)
        self.volume_slider.setEnabled(False)

    @Slot(str)
    def _on_state_changed(self, state: str) -> None:
        if state == "playing":
            self.play_btn.setText("\u23f8")  # Pause
            self.play_btn.setToolTip("Pause")
        else:
            self.play_btn.setText("\u25b6")  # Play
            self.play_btn.setToolTip("Play")

    @Slot(object)
    def _on_track_changed(self, track: TrackInfo) -> None:
        title = track.title or Path(track.file_path).stem
        self.title_label.setText(title)
        self.artist_label.setText(track.artist or "Unknown Artist")

    @Slot(float, float)
    def _on_position_changed(self, pos: float, dur: float) -> None:
        self._duration_s = dur
        if dur > 0 and not self._seeking:
            self.progress_slider.setValue(int(pos / dur * 1000))
        self.time_label.setText(f"{self._fmt(pos)} / {self._fmt(dur)}")

    @Slot(int)
    def _on_volume_changed(self, vol: int) -> None:
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(vol)
        self.volume_slider.blockSignals(False)

    def _on_slider_pressed(self) -> None:
        self._seeking = True

    def _on_slider_released(self) -> None:
        self._seeking = False
        if self._duration_s > 0:
            ratio = self.progress_slider.value() / 1000.0
            self._bridge.seek(ratio * self._duration_s)

    @staticmethod
    def _fmt(seconds: float) -> str:
        m, s = divmod(int(max(0, seconds)), 60)
        return f"{m}:{s:02d}"
