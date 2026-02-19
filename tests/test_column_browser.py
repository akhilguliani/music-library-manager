"""Tests for the ColumnBrowser widget."""

from __future__ import annotations

import gc

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from vdj_manager.core.models import Song, Tags
from vdj_manager.ui.widgets.column_browser import ColumnBrowser


@pytest.fixture(scope="module")
def qapp():
    """Create a QApplication instance for the test module."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    gc.collect()


@pytest.fixture()
def tracks():
    """Sample tracks for testing."""
    return [
        Song(
            file_path="/track1.mp3",
            tags=Tags(genre="House", author="DJ A", album="Album X"),
        ),
        Song(
            file_path="/track2.mp3",
            tags=Tags(genre="House", author="DJ B", album="Album X"),
        ),
        Song(
            file_path="/track3.mp3",
            tags=Tags(genre="Techno", author="DJ A", album="Album Y"),
        ),
        Song(
            file_path="/track4.mp3",
            tags=Tags(genre="Techno", author="DJ C"),
        ),
    ]


@pytest.fixture()
def browser(qapp):
    """Create a ColumnBrowser widget."""
    widget = ColumnBrowser()
    yield widget
    widget.close()


def test_creation(browser):
    """ColumnBrowser creates without error."""
    assert browser is not None
    assert browser._genre_list is not None
    assert browser._artist_list is not None
    assert browser._album_list is not None


def test_set_tracks_populates_genres(browser, tracks):
    """set_tracks populates genre list with 'All' + genres."""
    browser.set_tracks(tracks)

    genre_list = browser._genre_list
    # "All (4)", "House (2)", "Techno (2)"
    assert genre_list.count() == 3

    # First item is "All (4)"
    all_item = genre_list.item(0)
    assert all_item.text() == "All (4)"
    assert all_item.data(Qt.ItemDataRole.UserRole) == "__all__"

    # Genre items sorted alphabetically
    assert genre_list.item(1).text() == "House (2)"
    assert genre_list.item(2).text() == "Techno (2)"


def test_genre_cascade_filters_artists(browser, tracks, qapp):
    """Selecting a genre filters the artist list."""
    browser.set_tracks(tracks)

    # Select "Techno" only (deselect "All" first)
    browser._genre_list.blockSignals(True)
    browser._genre_list.clearSelection()
    for i in range(browser._genre_list.count()):
        item = browser._genre_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == "Techno":
            item.setSelected(True)
            break
    browser._genre_list.blockSignals(False)
    browser._on_genre_changed()
    qapp.processEvents()

    # Techno has DJ A and DJ C
    artist_list = browser._artist_list
    # "All (2)", "DJ A (1)", "DJ C (1)"
    assert artist_list.count() == 3
    texts = [artist_list.item(i).text() for i in range(artist_list.count())]
    assert "All (2)" in texts
    assert "DJ A (1)" in texts
    assert "DJ C (1)" in texts


def test_artist_cascade_filters_albums(browser, tracks, qapp):
    """Selecting an artist filters the album list."""
    browser.set_tracks(tracks)

    # Select "DJ A" only in artist list
    browser._artist_list.blockSignals(True)
    browser._artist_list.clearSelection()
    for i in range(browser._artist_list.count()):
        item = browser._artist_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == "DJ A":
            item.setSelected(True)
            break
    browser._artist_list.blockSignals(False)
    browser._on_artist_changed()
    qapp.processEvents()

    # DJ A has Album X and Album Y
    album_list = browser._album_list
    # "All (2)", "Album X (1)", "Album Y (1)"
    assert album_list.count() == 3
    texts = [album_list.item(i).text() for i in range(album_list.count())]
    assert "All (2)" in texts
    assert "Album X (1)" in texts
    assert "Album Y (1)" in texts


def test_all_selected_returns_empty_list(browser, tracks, qapp):
    """When 'All' is selected, filter_changed emits empty lists."""
    received = []
    browser.filter_changed.connect(lambda g, a, al: received.append((g, a, al)))

    browser.set_tracks(tracks)
    qapp.processEvents()

    # After set_tracks, "All" is selected in all lists
    assert len(received) > 0
    genres, artists, albums = received[-1]
    assert genres == []
    assert artists == []
    assert albums == []


def test_specific_genre_filter(browser, tracks, qapp):
    """Selecting a specific genre emits it in filter_changed."""
    received = []
    browser.filter_changed.connect(lambda g, a, al: received.append((g, a, al)))

    browser.set_tracks(tracks)
    qapp.processEvents()
    received.clear()

    # Select "House" genre
    browser._genre_list.clearSelection()
    for i in range(browser._genre_list.count()):
        item = browser._genre_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == "House":
            item.setSelected(True)
            break
    qapp.processEvents()

    assert len(received) > 0
    genres, artists, albums = received[-1]
    assert genres == ["House"]
    # Artists and albums should be empty (All selected in cascaded lists)
    assert artists == []
    assert albums == []


def test_no_genre_shows_no_genre_label(browser, qapp):
    """Tracks without genre show '(No Genre)' label."""
    tracks_no_genre = [
        Song(file_path="/track1.mp3", tags=Tags(author="DJ A")),
        Song(file_path="/track2.mp3", tags=Tags(genre="House", author="DJ B")),
    ]
    browser.set_tracks(tracks_no_genre)
    qapp.processEvents()

    genre_list = browser._genre_list
    # "All (2)", "(No Genre) (1)", "House (1)"
    assert genre_list.count() == 3
    texts = [genre_list.item(i).text() for i in range(genre_list.count())]
    assert "(No Genre) (1)" in texts
