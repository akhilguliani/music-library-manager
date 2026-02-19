"""Tests for online genre enrichment module."""

from unittest.mock import MagicMock, patch

from vdj_manager.analysis.online_genre import (
    TAG_TO_GENRE,
    LastFmGenreLookup,
    MusicBrainzGenreLookup,
    TagToGenreMapper,
    _cached_genre_lookup,
    lookup_online_genre,
    normalize_genre,
)

# =============================================================================
# TagToGenreMapper tests
# =============================================================================


class TestTagToGenreMapper:
    """Tests for tag-to-genre mapping logic."""

    def setup_method(self):
        self.mapper = TagToGenreMapper()

    def test_map_tags_house(self):
        tags = [("house", 100), ("deep house", 50)]
        assert self.mapper.map_tags(tags) == "House"

    def test_map_tags_techno(self):
        tags = [("techno", 100), ("minimal", 80)]
        result = self.mapper.map_tags(tags)
        assert result in ("Techno", "Minimal Techno")

    def test_map_tags_hip_hop(self):
        tags = [("hip hop", 100), ("rap", 80)]
        assert self.mapper.map_tags(tags) == "Hip-Hop"

    def test_map_tags_rock(self):
        tags = [("rock", 100), ("classic rock", 80)]
        assert self.mapper.map_tags(tags) == "Rock"

    def test_map_tags_weighted_scoring(self):
        """Higher count should win when tags map to different genres."""
        tags = [("house", 10), ("rock", 100)]
        assert self.mapper.map_tags(tags) == "Rock"

    def test_map_tags_no_match(self):
        tags = [("unknown_tag", 100), ("random_thing", 50)]
        assert self.mapper.map_tags(tags) is None

    def test_map_tags_empty_list(self):
        assert self.mapper.map_tags([]) is None

    def test_map_tags_case_insensitive(self):
        tags = [("HOUSE", 100), ("TECHNO", 50)]
        result = self.mapper.map_tags(tags)
        assert result in ("House", "Techno")

    def test_map_genres_electronic(self):
        genres = ["electronic", "house", "dance"]
        # electronic -> Electronic, house -> House
        result = self.mapper.map_genres(genres)
        assert result is not None

    def test_map_genres_no_match(self):
        genres = ["completely_unknown", "niche_thing"]
        assert self.mapper.map_genres(genres) is None

    def test_map_genres_empty(self):
        assert self.mapper.map_genres([]) is None

    def test_map_genres_case_insensitive(self):
        genres = ["Jazz", "BLUES"]
        result = self.mapper.map_genres(genres)
        assert result in ("Jazz", "Blues")

    def test_map_genres_unweighted(self):
        """Multiple tags mapping to same genre should beat a single different one."""
        genres = ["hip hop", "rap", "jazz"]
        # hip hop + rap both -> Hip-Hop (2 votes), jazz -> Jazz (1 vote)
        assert self.mapper.map_genres(genres) == "Hip-Hop"


# =============================================================================
# normalize_genre tests
# =============================================================================


class TestNormalizeGenre:
    """Tests for genre normalization."""

    def test_exact_match(self):
        assert normalize_genre("house") == "House"

    def test_case_insensitive(self):
        assert normalize_genre("DEEP HOUSE") == "Deep House"

    def test_whitespace_handling(self):
        assert normalize_genre("  techno  ") == "Techno"

    def test_unknown_genre_title_cased(self):
        assert normalize_genre("progressive breaks") == "Progressive Breaks"

    def test_empty_string(self):
        assert normalize_genre("") == ""

    def test_whitespace_only(self):
        assert normalize_genre("   ") == ""

    def test_hip_hop_variant(self):
        assert normalize_genre("hip-hop") == "Hip-Hop"

    def test_drum_and_bass(self):
        assert normalize_genre("drum and bass") == "Drum & Bass"

    def test_already_canonical(self):
        """Genre already in canonical form should pass through."""
        assert normalize_genre("House") == "House"


# =============================================================================
# LastFmGenreLookup tests
# =============================================================================


class TestLastFmGenreLookup:
    """Tests for Last.fm genre lookup."""

    def test_get_genre_success(self):
        """Should return genre when Last.fm returns matching tags."""
        mock_tag = MagicMock()
        mock_tag.item.get_name.return_value = "house"
        mock_tag.weight = "100"

        mock_track = MagicMock()
        mock_track.get_top_tags.return_value = [mock_tag]

        mock_network = MagicMock()
        mock_network.get_track.return_value = mock_track

        with patch.dict("sys.modules", {"pylast": MagicMock()}):
            import pylast

            pylast.LastFMNetwork.return_value = mock_network
            lookup = LastFmGenreLookup(api_key="test_key")
            result = lookup.get_genre("Artist", "Title")
            assert result == "House"

    def test_get_genre_track_not_found(self):
        """Should return None when track is not found."""
        with patch.dict("sys.modules", {"pylast": MagicMock()}):
            import pylast

            pylast.WSError = type("WSError", (Exception,), {})
            pylast.NetworkError = type("NetworkError", (Exception,), {})
            pylast.MalformedResponseError = type("MalformedResponseError", (Exception,), {})
            pylast.LastFMNetwork.return_value.get_track.side_effect = pylast.WSError(
                "network", "status", "Track not found"
            )
            lookup = LastFmGenreLookup(api_key="test_key")
            result = lookup.get_genre("Unknown", "Track")
            assert result is None

    def test_get_genre_network_error(self):
        """Should return None on network errors."""
        with patch.dict("sys.modules", {"pylast": MagicMock()}):
            import pylast

            pylast.WSError = type("WSError", (Exception,), {})
            pylast.NetworkError = type("NetworkError", (Exception,), {})
            pylast.MalformedResponseError = type("MalformedResponseError", (Exception,), {})
            pylast.LastFMNetwork.return_value.get_track.side_effect = pylast.NetworkError("timeout")
            lookup = LastFmGenreLookup(api_key="test_key")
            result = lookup.get_genre("Artist", "Title")
            assert result is None

    def test_get_genre_not_installed(self):
        """Should return None when pylast is not installed."""
        with patch.dict("sys.modules", {"pylast": None}):
            lookup = LastFmGenreLookup(api_key="test_key")
            result = lookup.get_genre("Artist", "Title")
            assert result is None

    def test_get_genre_from_artist(self):
        """Artist fallback should return genre from artist tags."""
        mock_tag = MagicMock()
        mock_tag.item.get_name.return_value = "techno"
        mock_tag.weight = "100"

        mock_artist = MagicMock()
        mock_artist.get_top_tags.return_value = [mock_tag]

        mock_network = MagicMock()
        mock_network.get_artist.return_value = mock_artist

        with patch.dict("sys.modules", {"pylast": MagicMock()}):
            import pylast

            pylast.LastFMNetwork.return_value = mock_network
            lookup = LastFmGenreLookup(api_key="test_key")
            result = lookup.get_genre_from_artist("Artist")
            assert result == "Techno"


# =============================================================================
# MusicBrainzGenreLookup tests
# =============================================================================


class TestMusicBrainzGenreLookup:
    """Tests for MusicBrainz genre lookup."""

    def test_get_genre_success(self):
        """Should return genre when MusicBrainz returns matching genres."""
        mock_result = {
            "recording-list": [
                {
                    "tag-list": [
                        {"name": "electronic"},
                        {"name": "house"},
                    ]
                }
            ]
        }

        with patch.dict("sys.modules", {"musicbrainzngs": MagicMock()}):
            import musicbrainzngs

            musicbrainzngs.search_recordings.return_value = mock_result
            lookup = MusicBrainzGenreLookup()
            result = lookup.get_genre("Artist", "Title")
            assert result is not None

    def test_get_genre_no_results(self):
        """Should return None when no recordings found."""
        with patch.dict("sys.modules", {"musicbrainzngs": MagicMock()}):
            import musicbrainzngs

            musicbrainzngs.search_recordings.return_value = {"recording-list": []}
            lookup = MusicBrainzGenreLookup()
            result = lookup.get_genre("Unknown", "Track")
            assert result is None

    def test_get_genre_not_installed(self):
        """Should return None when musicbrainzngs is not installed."""
        with patch.dict("sys.modules", {"musicbrainzngs": None}):
            lookup = MusicBrainzGenreLookup()
            result = lookup.get_genre("Artist", "Title")
            assert result is None

    def test_get_genre_empty_tag_list(self):
        """Should return None when tag-list is empty."""
        mock_result = {"recording-list": [{"tag-list": []}]}

        with patch.dict("sys.modules", {"musicbrainzngs": MagicMock()}):
            import musicbrainzngs

            musicbrainzngs.search_recordings.return_value = mock_result
            lookup = MusicBrainzGenreLookup()
            result = lookup.get_genre("Artist", "Title")
            assert result is None


# =============================================================================
# lookup_online_genre tests
# =============================================================================


class TestLookupOnlineGenre:
    """Tests for the top-level lookup function."""

    def setup_method(self):
        _cached_genre_lookup.cache_clear()

    def test_lastfm_success_skips_mb(self):
        """Should return Last.fm result and skip MusicBrainz."""
        with (
            patch("vdj_manager.analysis.online_genre.LastFmGenreLookup") as MockLfm,
            patch("vdj_manager.analysis.online_genre.MusicBrainzGenreLookup") as MockMb,
        ):
            MockLfm.return_value.get_genre.return_value = "House"
            genre, source = lookup_online_genre("Artist", "Title", "api_key")
            assert genre == "House"
            assert source == "lastfm"
            MockMb.return_value.get_genre.assert_not_called()

    def test_lastfm_track_fails_tries_artist(self):
        """Should fall back to artist tags when track tags are empty."""
        _cached_genre_lookup.cache_clear()
        with (
            patch("vdj_manager.analysis.online_genre.LastFmGenreLookup") as MockLfm,
            patch("vdj_manager.analysis.online_genre.MusicBrainzGenreLookup") as MockMb,
        ):
            MockLfm.return_value.get_genre.return_value = None
            MockLfm.return_value.get_genre_from_artist.return_value = "Techno"
            genre, source = lookup_online_genre("Artist", "Title2", "api_key")
            assert genre == "Techno"
            assert source == "lastfm-artist"
            MockMb.return_value.get_genre.assert_not_called()

    def test_lastfm_all_fail_tries_mb(self):
        """Should fall back to MusicBrainz when all Last.fm lookups fail."""
        _cached_genre_lookup.cache_clear()
        with (
            patch("vdj_manager.analysis.online_genre.LastFmGenreLookup") as MockLfm,
            patch("vdj_manager.analysis.online_genre.MusicBrainzGenreLookup") as MockMb,
        ):
            MockLfm.return_value.get_genre.return_value = None
            MockLfm.return_value.get_genre_from_artist.return_value = None
            MockMb.return_value.get_genre.return_value = "Pop"
            genre, source = lookup_online_genre("Artist", "Title5", "api_key")
            assert genre == "Pop"
            assert source == "musicbrainz"

    def test_all_fail_returns_none(self):
        """Should return (None, 'none') when all services fail."""
        _cached_genre_lookup.cache_clear()
        with (
            patch("vdj_manager.analysis.online_genre.LastFmGenreLookup") as MockLfm,
            patch("vdj_manager.analysis.online_genre.MusicBrainzGenreLookup") as MockMb,
        ):
            MockLfm.return_value.get_genre.return_value = None
            MockLfm.return_value.get_genre_from_artist.return_value = None
            MockMb.return_value.get_genre.return_value = None
            genre, source = lookup_online_genre("Artist", "Title3", "api_key")
            assert genre is None
            assert source == "none"

    def test_no_artist_title_returns_none(self):
        """Should return (None, 'none') when artist/title are missing."""
        genre, source = lookup_online_genre("", "", "api_key")
        assert genre is None
        assert source == "none"

        genre, source = lookup_online_genre("", "Title", "api_key")
        assert genre is None
        assert source == "none"

    def test_no_api_key_skips_lastfm(self):
        """Should skip Last.fm when no API key provided."""
        _cached_genre_lookup.cache_clear()
        with (
            patch("vdj_manager.analysis.online_genre.LastFmGenreLookup") as MockLfm,
            patch("vdj_manager.analysis.online_genre.MusicBrainzGenreLookup") as MockMb,
        ):
            MockMb.return_value.get_genre.return_value = "Jazz"
            genre, source = lookup_online_genre("Artist", "Title4", None)
            assert genre == "Jazz"
            assert source == "musicbrainz"
            MockLfm.return_value.get_genre.assert_not_called()

    def test_cleaning_applied_before_lookup(self):
        """Metadata should be cleaned before querying online services."""
        _cached_genre_lookup.cache_clear()
        with (
            patch("vdj_manager.analysis.online_genre.LastFmGenreLookup") as MockLfm,
            patch("vdj_manager.analysis.online_genre.MusicBrainzGenreLookup"),
        ):
            MockLfm.return_value.get_genre.return_value = "Pop"
            lookup_online_genre("Jason Derulo feat. Nicki Minaj", "Swalla (Remix)", "key")
            MockLfm.return_value.get_genre.assert_called_once_with("Jason Derulo", "Swalla")


# =============================================================================
# TAG_TO_GENRE dict coverage
# =============================================================================


class TestTagToGenreDict:
    """Tests for the TAG_TO_GENRE mapping dictionary."""

    def test_all_keys_are_lowercase(self):
        for tag in TAG_TO_GENRE:
            assert tag == tag.lower(), f"Tag '{tag}' is not lowercase"

    def test_minimum_tag_count(self):
        """Should have a reasonable number of tag mappings."""
        assert len(TAG_TO_GENRE) >= 100

    def test_common_genres_present(self):
        """Key DJ genres should be in the mapping."""
        expected = ["house", "techno", "trance", "hip-hop", "pop", "rock", "jazz", "ambient"]
        for tag in expected:
            assert tag in TAG_TO_GENRE, f"Expected tag '{tag}' not in mapping"

    def test_values_are_title_cased(self):
        """All canonical genre values should be properly cased."""
        for tag, genre in TAG_TO_GENRE.items():
            assert genre == genre.strip(), f"Genre '{genre}' for tag '{tag}' has whitespace"
            assert len(genre) > 0, f"Genre for tag '{tag}' is empty"
