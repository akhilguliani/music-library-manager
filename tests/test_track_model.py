"""Tests for track table model."""

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from vdj_manager.core.models import Song, Tags, Scan, Infos
from vdj_manager.ui.models.track_model import TrackTableModel


@pytest.fixture(scope="module")
def app():
    """Create a QApplication for testing."""
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        app = QApplication(["test"])
        yield app


@pytest.fixture
def sample_tracks():
    """Create sample tracks for testing."""
    return [
        Song(
            file_path="/path/to/track1.mp3",
            file_size=5000000,
            tags=Tags(
                author="Artist One",
                title="Track One",
                genre="Dance",
                grouping="Energy 7",
            ),
            infos=Infos(song_length=180.5, bitrate=320),
            scan=Scan(bpm=0.5, key="Am"),
        ),
        Song(
            file_path="/path/to/track2.mp3",
            file_size=4000000,
            tags=Tags(
                author="Artist Two",
                title="Track Two",
                genre="House",
                grouping="Energy 5",
            ),
            infos=Infos(song_length=240.0, bitrate=256),
            scan=Scan(bpm=0.4615, key="Cm"),  # ~130 BPM
        ),
        Song(
            file_path="/path/to/track3.mp3",
            file_size=3000000,
            tags=Tags(
                author="Artist Three",
                title="Track Three",
            ),
            # No scan or infos
        ),
    ]


class TestTrackTableModel:
    """Tests for TrackTableModel."""

    def test_model_creation(self, app):
        """Test model can be created."""
        model = TrackTableModel()
        assert model is not None
        assert model.rowCount() == 0
        assert model.columnCount() == 7

    def test_set_tracks(self, app, sample_tracks):
        """Test setting tracks updates the model."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        assert model.rowCount() == 3
        assert len(model.tracks) == 3

    def test_clear_tracks(self, app, sample_tracks):
        """Test clearing tracks."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)
        assert model.rowCount() == 3

        model.clear()
        assert model.rowCount() == 0

    def test_header_data(self, app):
        """Test header data."""
        model = TrackTableModel()

        # Check column headers
        assert model.headerData(0, Qt.Orientation.Horizontal) == "Title"
        assert model.headerData(1, Qt.Orientation.Horizontal) == "Artist"
        assert model.headerData(2, Qt.Orientation.Horizontal) == "BPM"
        assert model.headerData(3, Qt.Orientation.Horizontal) == "Key"
        assert model.headerData(4, Qt.Orientation.Horizontal) == "Energy"
        assert model.headerData(5, Qt.Orientation.Horizontal) == "Duration"
        assert model.headerData(6, Qt.Orientation.Horizontal) == "Genre"

    def test_data_display_role(self, app, sample_tracks):
        """Test data retrieval with DisplayRole."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        # First track - full metadata
        assert model.data(model.index(0, 0)) == "Track One"  # Title
        assert model.data(model.index(0, 1)) == "Artist One"  # Artist
        assert model.data(model.index(0, 2)) == "120.0"  # BPM (60/0.5)
        assert model.data(model.index(0, 3)) == "Am"  # Key
        assert model.data(model.index(0, 4)) == "7"  # Energy
        assert model.data(model.index(0, 5)) == "3:00"  # Duration (180.5 seconds)
        assert model.data(model.index(0, 6)) == "Dance"  # Genre

    def test_data_missing_metadata(self, app, sample_tracks):
        """Test data retrieval with missing metadata."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        # Third track - minimal metadata
        assert model.data(model.index(2, 0)) == "Track Three"  # Title
        assert model.data(model.index(2, 1)) == "Artist Three"  # Artist
        assert model.data(model.index(2, 2)) == ""  # No BPM
        assert model.data(model.index(2, 3)) == ""  # No Key
        assert model.data(model.index(2, 4)) == ""  # No Energy
        assert model.data(model.index(2, 5)) == ""  # No Duration
        assert model.data(model.index(2, 6)) == ""  # No Genre

    def test_data_tooltip_role(self, app, sample_tracks):
        """Test tooltip shows file path."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        tooltip = model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole)
        assert tooltip == "/path/to/track1.mp3"

    def test_data_user_role(self, app, sample_tracks):
        """Test UserRole returns the Song object."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        song = model.data(model.index(0, 0), Qt.ItemDataRole.UserRole)
        assert isinstance(song, Song)
        assert song.file_path == "/path/to/track1.mp3"

    def test_data_alignment(self, app, sample_tracks):
        """Test text alignment for different columns."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        # Text columns should be left-aligned
        title_align = model.data(model.index(0, 0), Qt.ItemDataRole.TextAlignmentRole)
        assert title_align & Qt.AlignmentFlag.AlignLeft

        # Numeric columns should be right-aligned
        bpm_align = model.data(model.index(0, 2), Qt.ItemDataRole.TextAlignmentRole)
        assert bpm_align & Qt.AlignmentFlag.AlignRight

    def test_get_track(self, app, sample_tracks):
        """Test getting track by row."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        track = model.get_track(0)
        assert track is not None
        assert track.file_path == "/path/to/track1.mp3"

        track = model.get_track(1)
        assert track is not None
        assert track.file_path == "/path/to/track2.mp3"

        # Out of range
        assert model.get_track(-1) is None
        assert model.get_track(10) is None

    def test_get_track_at_index(self, app, sample_tracks):
        """Test getting track from model index."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        index = model.index(1, 0)
        track = model.get_track_at_index(index)
        assert track is not None
        assert track.file_path == "/path/to/track2.mp3"

    def test_find_track_row(self, app, sample_tracks):
        """Test finding track row by file path."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        row = model.find_track_row("/path/to/track2.mp3")
        assert row == 1

        row = model.find_track_row("/nonexistent/path.mp3")
        assert row == -1

    def test_format_duration(self, app):
        """Test duration formatting."""
        model = TrackTableModel()

        assert model._format_duration(0) == "0:00"
        assert model._format_duration(30) == "0:30"
        assert model._format_duration(60) == "1:00"
        assert model._format_duration(90) == "1:30"
        assert model._format_duration(180.5) == "3:00"
        assert model._format_duration(3600) == "60:00"

    def test_invalid_index(self, app, sample_tracks):
        """Test data retrieval with invalid index."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        # Invalid index returns None
        from PySide6.QtCore import QModelIndex

        assert model.data(QModelIndex()) is None

    def test_row_count_with_parent(self, app, sample_tracks):
        """Test rowCount with parent index (should be 0)."""
        model = TrackTableModel()
        model.set_tracks(sample_tracks)

        # With valid parent, should return 0 (table is flat)
        assert model.rowCount(model.index(0, 0)) == 0

    def test_large_track_list(self, app):
        """Test model with large number of tracks."""
        # Create 1000 tracks
        tracks = [
            Song(
                file_path=f"/path/to/track{i}.mp3",
                tags=Tags(title=f"Track {i}", author=f"Artist {i}"),
            )
            for i in range(1000)
        ]

        model = TrackTableModel()
        model.set_tracks(tracks)

        assert model.rowCount() == 1000
        assert model.data(model.index(500, 0)) == "Track 500"
        assert model.data(model.index(999, 1)) == "Artist 999"
