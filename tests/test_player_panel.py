"""Tests for the PlayerPanel widget."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from vdj_manager.player.bridge import PlaybackBridge
from vdj_manager.player.engine import PlaybackState, TrackInfo
from vdj_manager.ui.widgets.player_panel import PlayerPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def player_panel(qapp):
    bridge = PlaybackBridge()
    panel = PlayerPanel(bridge)
    return panel, bridge


class TestPlayerPanel:
    """Tests for PlayerPanel widget."""

    def test_initial_state(self, player_panel):
        """Panel should show no track loaded initially."""
        panel, _ = player_panel
        assert panel.title_label.text() == "No track loaded"
        assert panel.artist_label.text() == ""
        assert panel.bpm_label.text() == "BPM: --"

    def test_track_changed_updates_metadata(self, qapp, player_panel):
        """Track change should update all metadata labels."""
        panel, bridge = player_panel
        track = TrackInfo(
            file_path="/test.mp3",
            title="Test Song",
            artist="Test Artist",
            bpm=128.0,
            key="Am",
            energy=7,
            mood="#happy",
        )
        with patch.object(panel, "_load_album_art"), \
             patch.object(panel, "_load_waveform"):
            bridge._emit_track(track)
            qapp.processEvents()

        assert panel.title_label.text() == "Test Song"
        assert panel.artist_label.text() == "Test Artist"
        assert panel.bpm_label.text() == "BPM: 128"
        assert panel.key_label.text() == "Key: Am"
        assert panel.energy_label.text() == "Energy: 7"
        assert panel.mood_label.text() == "Mood: #happy"

    def test_track_without_metadata(self, qapp, player_panel):
        """Track without metadata should show defaults."""
        panel, bridge = player_panel
        track = TrackInfo(file_path="/music/cool_track.mp3")
        with patch.object(panel, "_load_album_art"), \
             patch.object(panel, "_load_waveform"):
            bridge._emit_track(track)
            qapp.processEvents()

        assert panel.title_label.text() == "cool_track"
        assert panel.artist_label.text() == "Unknown Artist"
        assert panel.bpm_label.text() == "BPM: --"

    def test_position_updates_waveform(self, qapp, player_panel):
        """Position changes should update waveform widget."""
        panel, bridge = player_panel
        bridge._emit_position(60.0, 240.0)
        qapp.processEvents()

        assert panel.waveform._duration == 240.0
        assert abs(panel.waveform._position - 0.25) < 0.01

    def test_queue_changed_updates_list(self, qapp, player_panel):
        """Queue changes should update the queue list widget."""
        panel, bridge = player_panel
        tracks = [
            TrackInfo(file_path="/a.mp3", title="Song A", artist="Artist 1"),
            TrackInfo(file_path="/b.mp3", title="Song B"),
        ]
        bridge._emit_queue(tracks)
        qapp.processEvents()

        assert panel.queue_list.count() == 2
        assert "Artist 1 - Song A" in panel.queue_list.item(0).text()
        assert "Song B" in panel.queue_list.item(1).text()

    def test_track_finished_adds_to_history(self, qapp, player_panel):
        """Finished tracks should appear at top of history list."""
        panel, bridge = player_panel
        track = TrackInfo(file_path="/done.mp3", title="Done Song", artist="Done Artist")
        bridge._emit_track_finished(track)
        qapp.processEvents()

        assert panel.history_list.count() >= 1
        assert "Done Artist - Done Song" in panel.history_list.item(0).text()

    def test_history_max_100(self, qapp, player_panel):
        """History should cap at 100 entries."""
        panel, bridge = player_panel
        panel.history_list.clear()
        for i in range(105):
            bridge._emit_track_finished(TrackInfo(file_path=f"/t{i}.mp3", title=f"T{i}"))
            qapp.processEvents()

        assert panel.history_list.count() == 100

    def test_speed_slider_initial(self, player_panel):
        """Speed slider should start at 100 (1.0x)."""
        panel, _ = player_panel
        assert panel.speed_slider.value() == 100
        assert panel.speed_label.text() == "1.0x"

    def test_speed_changed_updates_ui(self, qapp, player_panel):
        """Speed change from bridge should update slider and label."""
        panel, bridge = player_panel
        bridge.speed_changed.emit(1.5)
        qapp.processEvents()
        assert panel.speed_slider.value() == 150
        assert panel.speed_label.text() == "1.5x"

    def test_rating_changed_signal(self, qapp, player_panel):
        """Rating change should emit rating_changed with file path."""
        panel, bridge = player_panel
        # Set a current track first
        track = TrackInfo(file_path="/rated.mp3", title="Rated")
        with patch.object(panel, "_load_album_art"), \
             patch.object(panel, "_load_waveform"):
            bridge._emit_track(track)
            qapp.processEvents()

        received = []
        panel.rating_changed.connect(lambda fp, r: received.append((fp, r)))
        panel.star_rating.rating_changed.emit(4)
        qapp.processEvents()

        assert received == [("/rated.mp3", 4)]

    def test_repeat_cycle(self, qapp, player_panel):
        """Repeat button should cycle through Off -> One -> All -> Off."""
        panel, _ = player_panel
        assert "Off" in panel.repeat_btn.text()

        panel.repeat_btn.click()
        qapp.processEvents()
        assert "One" in panel.repeat_btn.text()

        panel.repeat_btn.click()
        qapp.processEvents()
        assert "All" in panel.repeat_btn.text()

        panel.repeat_btn.click()
        qapp.processEvents()
        assert "Off" in panel.repeat_btn.text()

    def test_waveform_seek_connects_to_bridge(self, qapp, player_panel):
        """Waveform seek signal should be connected to bridge.seek."""
        panel, bridge = player_panel
        with patch.object(bridge, "seek") as mock_seek:
            panel.waveform.seek_requested.emit(60.0)
            qapp.processEvents()
            mock_seek.assert_called_once_with(60.0)
