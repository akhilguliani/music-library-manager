"""Tests for queue context menu: engine insert_next, bridge delegation, and panel context menu."""

import pytest

from vdj_manager.player.engine import PlaybackEngine, TrackInfo

# ---------------------------------------------------------------------------
# Engine: insert_next
# ---------------------------------------------------------------------------


def _make_track(name: str) -> TrackInfo:
    return TrackInfo(file_path=f"/music/{name}.mp3", title=name)


class TestInsertNext:
    """Tests for PlaybackEngine.insert_next()."""

    def test_insert_next_empty_queue(self):
        """insert_next on empty queue appends the track."""
        engine = PlaybackEngine()
        track = _make_track("A")
        engine.insert_next(track)
        assert engine.queue == [track]

    def test_insert_next_after_current(self):
        """insert_next inserts after the current queue index."""
        engine = PlaybackEngine()
        t1, t2, t3 = _make_track("A"), _make_track("B"), _make_track("C")
        engine._queue = [t1, t2]
        engine._queue_index = 0
        engine.insert_next(t3)
        assert engine.queue == [t1, t3, t2]

    def test_insert_next_at_end(self):
        """insert_next when current is last track inserts at the end."""
        engine = PlaybackEngine()
        t1, t2, t3 = _make_track("A"), _make_track("B"), _make_track("C")
        engine._queue = [t1, t2]
        engine._queue_index = 1
        engine.insert_next(t3)
        assert engine.queue == [t1, t2, t3]

    def test_insert_next_fires_queue_callback(self):
        """insert_next fires queue change callbacks."""
        engine = PlaybackEngine()
        calls = []
        engine.on_queue_change(lambda q: calls.append(q))
        engine.insert_next(_make_track("A"))
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# Bridge: insert_next delegation
# ---------------------------------------------------------------------------


class TestBridgeInsertNext:
    """Tests for PlaybackBridge.insert_next()."""

    @pytest.fixture
    def qapp(self):
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_bridge_insert_next(self, qapp):
        from vdj_manager.player.bridge import PlaybackBridge

        bridge = PlaybackBridge()
        track = _make_track("A")
        bridge.insert_next(track)
        assert bridge.engine.queue == [track]


# ---------------------------------------------------------------------------
# DatabasePanel: context menu & multi-select
# ---------------------------------------------------------------------------


class TestDatabasePanelContextMenu:
    """Tests for DatabasePanel context menu and multi-select."""

    @pytest.fixture
    def qapp(self):
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_extended_selection_mode(self, qapp):
        """Track table should use ExtendedSelection."""
        from PySide6.QtWidgets import QAbstractItemView

        from vdj_manager.ui.widgets.database_panel import DatabasePanel

        panel = DatabasePanel()
        mode = panel.track_table.selectionMode()
        assert mode == QAbstractItemView.SelectionMode.ExtendedSelection

    def test_no_context_menu_without_selection(self, qapp):
        """_on_track_context_menu should be a no-op when nothing is selected."""
        from PySide6.QtCore import QPoint

        from vdj_manager.ui.widgets.database_panel import DatabasePanel

        panel = DatabasePanel()
        # Should not raise
        panel._on_track_context_menu(QPoint(0, 0))

    def test_panel_has_queue_signals(self, qapp):
        """DatabasePanel should have play_next_requested and add_to_queue_requested signals."""
        from vdj_manager.ui.widgets.database_panel import DatabasePanel

        panel = DatabasePanel()
        assert hasattr(panel, "play_next_requested")
        assert hasattr(panel, "add_to_queue_requested")
