"""Integration tests for the music player feature."""

import time
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from vdj_manager.core.models import Song, Tags, Infos
from vdj_manager.player.engine import TrackInfo
from vdj_manager.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_song(path: str, play_count: int = 0) -> Song:
    return Song(
        file_path=path,
        tags=Tags(author="Artist", title="Title"),
        infos=Infos(song_length=240.0, play_count=play_count),
    )


class TestPlaybackIntegration:
    """Tests for playback integration with database."""

    def test_double_click_starts_playback(self, qapp):
        """Double-clicking a track should call play_track on bridge."""
        window = MainWindow()
        song = _make_song("/test/song.mp3")
        with patch.object(window._playback_bridge, "play_track") as mock_play:
            window._on_track_play_requested(song)
            mock_play.assert_called_once()
            track = mock_play.call_args[0][0]
            assert track.file_path == "/test/song.mp3"

    def test_track_finished_increments_play_count(self, qapp):
        """Track completion should increment play count in database."""
        window = MainWindow()
        mock_db = MagicMock()
        song = _make_song("/test/song.mp3", play_count=3)
        mock_db.get_song.return_value = song
        window._database = mock_db

        track = TrackInfo(file_path="/test/song.mp3", title="Song")
        window._on_track_playback_finished(track)

        mock_db.update_song_infos.assert_called_once()
        call_kwargs = mock_db.update_song_infos.call_args
        assert call_kwargs[1]["PlayCount"] == 4
        assert "LastPlay" in call_kwargs[1]

    def test_track_finished_no_db_is_noop(self, qapp):
        """Track completion without database should not crash."""
        window = MainWindow()
        track = TrackInfo(file_path="/test/song.mp3")
        # Should not raise
        window._on_track_playback_finished(track)

    def test_rating_change_updates_database(self, qapp):
        """Rating change should update Tags/@Rating in database."""
        window = MainWindow()
        mock_db = MagicMock()
        window._database = mock_db

        window._on_rating_changed("/test/song.mp3", 4)

        mock_db.update_song_tags.assert_called_once_with("/test/song.mp3", Rating=4)

    def test_debounced_save(self, qapp):
        """Multiple rapid changes should batch into one save."""
        window = MainWindow()
        mock_db = MagicMock()
        window._database = mock_db

        # Trigger multiple saves
        window._on_rating_changed("/a.mp3", 3)
        window._on_rating_changed("/b.mp3", 5)

        # Save should be pending but not yet executed
        assert window._save_pending is True
        mock_db.save.assert_not_called()

        # Force the timer
        window._flush_save()
        mock_db.save.assert_called_once()
        assert window._save_pending is False

    def test_close_flushes_save(self, qapp):
        """Closing the window should flush any pending saves."""
        window = MainWindow()
        mock_db = MagicMock()
        window._database = mock_db
        window._save_pending = True

        # Simulate close
        window._save_timer.stop()
        window._flush_save()

        mock_db.save.assert_called_once()

    def test_mini_player_and_player_panel_exist(self, qapp):
        """MainWindow should have both MiniPlayer and PlayerPanel."""
        window = MainWindow()
        from vdj_manager.ui.widgets.mini_player import MiniPlayer
        from vdj_manager.ui.widgets.player_panel import PlayerPanel

        assert isinstance(window.mini_player, MiniPlayer)
        assert isinstance(window.player_panel, PlayerPanel)
