"""Tests for online mood enrichment module."""

from unittest.mock import MagicMock, patch

import pytest

from vdj_manager.analysis.online_mood import (
    TAG_TO_MOOD,
    TagToMoodMapper,
    LastFmLookup,
    MusicBrainzLookup,
    lookup_online_mood,
    _cached_online_lookup,
)


# =============================================================================
# TagToMoodMapper tests
# =============================================================================


class TestTagToMoodMapper:
    """Tests for tag-to-mood mapping logic."""

    def setup_method(self):
        self.mapper = TagToMoodMapper()

    def test_map_tags_happy(self):
        tags = [("happy", 100), ("cheerful", 50)]
        assert self.mapper.map_tags(tags) == "happy"

    def test_map_tags_sad(self):
        tags = [("sad", 100), ("somber", 80)]
        assert self.mapper.map_tags(tags) == "sad"

    def test_map_tags_heavy(self):
        tags = [("metal", 100), ("brutal", 90)]
        assert self.mapper.map_tags(tags) == "heavy"

    def test_map_tags_calm(self):
        tags = [("chill", 100), ("peaceful", 80)]
        assert self.mapper.map_tags(tags) == "calm"

    def test_map_tags_party(self):
        tags = [("dance", 100), ("club", 80)]
        assert self.mapper.map_tags(tags) == "party"

    def test_map_tags_energetic(self):
        tags = [("techno", 100), ("edm", 80)]
        assert self.mapper.map_tags(tags) == "energetic"

    def test_map_tags_melancholic(self):
        tags = [("melancholy", 100), ("nostalgic", 80)]
        assert self.mapper.map_tags(tags) == "melancholic"

    def test_map_tags_weighted_scoring(self):
        """Higher count should win when tags map to different moods."""
        tags = [("happy", 10), ("sad", 100)]
        assert self.mapper.map_tags(tags) == "sad"

    def test_map_tags_no_match(self):
        tags = [("unknown_tag", 100), ("random_genre", 50)]
        assert self.mapper.map_tags(tags) is None

    def test_map_tags_empty_list(self):
        assert self.mapper.map_tags([]) is None

    def test_map_tags_case_insensitive(self):
        tags = [("HAPPY", 100), ("CHEERFUL", 50)]
        assert self.mapper.map_tags(tags) == "happy"

    def test_map_genres_success(self):
        genres = ["electronic", "techno", "ambient"]
        # electronic + techno = 2 votes for energetic, ambient -> soundscape = 1
        assert self.mapper.map_genres(genres) == "energetic"

    def test_map_genres_no_match(self):
        genres = ["completely_unknown", "niche_genre"]
        assert self.mapper.map_genres(genres) is None

    def test_map_genres_empty(self):
        assert self.mapper.map_genres([]) is None

    def test_map_genres_case_insensitive(self):
        genres = ["Jazz", "BLUES"]
        # jazz -> cool, blues -> emotional
        result = self.mapper.map_genres(genres)
        assert result in ("cool", "emotional")


# =============================================================================
# LastFmLookup tests
# =============================================================================


class TestLastFmLookup:
    """Tests for Last.fm lookup."""

    def test_get_mood_success(self):
        """Should return mood when Last.fm returns matching tags."""
        mock_tag = MagicMock()
        mock_tag.item.get_name.return_value = "chill"
        mock_tag.weight = "100"

        mock_track = MagicMock()
        mock_track.get_top_tags.return_value = [mock_tag]

        mock_network = MagicMock()
        mock_network.get_track.return_value = mock_track

        with patch.dict("sys.modules", {"pylast": MagicMock()}):
            import pylast
            pylast.LastFMNetwork.return_value = mock_network
            lookup = LastFmLookup(api_key="test_key")
            result = lookup.get_mood("Artist", "Title")
            assert result == "calm"

    def test_get_mood_track_not_found(self):
        """Should return None when track is not found."""
        with patch.dict("sys.modules", {"pylast": MagicMock()}) as mods:
            import pylast
            pylast.WSError = type("WSError", (Exception,), {})
            pylast.NetworkError = type("NetworkError", (Exception,), {})
            pylast.MalformedResponseError = type("MalformedResponseError", (Exception,), {})
            pylast.LastFMNetwork.return_value.get_track.side_effect = pylast.WSError(
                "network", "status", "Track not found"
            )
            lookup = LastFmLookup(api_key="test_key")
            result = lookup.get_mood("Unknown", "Track")
            assert result is None

    def test_get_mood_network_error(self):
        """Should return None on network errors."""
        with patch.dict("sys.modules", {"pylast": MagicMock()}) as mods:
            import pylast
            pylast.WSError = type("WSError", (Exception,), {})
            pylast.NetworkError = type("NetworkError", (Exception,), {})
            pylast.MalformedResponseError = type("MalformedResponseError", (Exception,), {})
            pylast.LastFMNetwork.return_value.get_track.side_effect = pylast.NetworkError(
                "timeout"
            )
            lookup = LastFmLookup(api_key="test_key")
            result = lookup.get_mood("Artist", "Title")
            assert result is None

    def test_get_mood_not_installed(self):
        """Should return None when pylast is not installed."""
        with patch.dict("sys.modules", {"pylast": None}):
            lookup = LastFmLookup(api_key="test_key")
            result = lookup.get_mood("Artist", "Title")
            assert result is None


# =============================================================================
# MusicBrainzLookup tests
# =============================================================================


class TestMusicBrainzLookup:
    """Tests for MusicBrainz lookup."""

    def test_get_mood_success(self):
        """Should return mood when MusicBrainz returns matching genres."""
        mock_result = {
            "recording-list": [
                {
                    "tag-list": [
                        {"name": "electronic"},
                        {"name": "dance"},
                    ]
                }
            ]
        }

        with patch.dict("sys.modules", {"musicbrainzngs": MagicMock()}) as mods:
            import musicbrainzngs
            musicbrainzngs.search_recordings.return_value = mock_result
            lookup = MusicBrainzLookup()
            result = lookup.get_mood("Artist", "Title")
            assert result in ("energetic", "party")

    def test_get_mood_no_results(self):
        """Should return None when no recordings found."""
        with patch.dict("sys.modules", {"musicbrainzngs": MagicMock()}) as mods:
            import musicbrainzngs
            musicbrainzngs.search_recordings.return_value = {"recording-list": []}
            lookup = MusicBrainzLookup()
            result = lookup.get_mood("Unknown", "Track")
            assert result is None

    def test_get_mood_not_installed(self):
        """Should return None when musicbrainzngs is not installed."""
        with patch.dict("sys.modules", {"musicbrainzngs": None}):
            lookup = MusicBrainzLookup()
            result = lookup.get_mood("Artist", "Title")
            assert result is None


# =============================================================================
# lookup_online_mood tests
# =============================================================================


class TestLookupOnlineMood:
    """Tests for the top-level lookup function."""

    def setup_method(self):
        # Clear the LRU cache between tests
        _cached_online_lookup.cache_clear()

    def test_lastfm_success_skips_mb(self):
        """Should return Last.fm result and skip MusicBrainz."""
        with patch("vdj_manager.analysis.online_mood.LastFmLookup") as MockLfm, \
             patch("vdj_manager.analysis.online_mood.MusicBrainzLookup") as MockMb:
            MockLfm.return_value.get_mood.return_value = "happy"
            mood, source = lookup_online_mood("Artist", "Title", "api_key")
            assert mood == "happy"
            assert source == "lastfm"
            MockMb.return_value.get_mood.assert_not_called()

    def test_lastfm_fails_tries_mb(self):
        """Should fall back to MusicBrainz when Last.fm fails."""
        _cached_online_lookup.cache_clear()
        with patch("vdj_manager.analysis.online_mood.LastFmLookup") as MockLfm, \
             patch("vdj_manager.analysis.online_mood.MusicBrainzLookup") as MockMb:
            MockLfm.return_value.get_mood.return_value = None
            MockMb.return_value.get_mood.return_value = "energetic"
            mood, source = lookup_online_mood("Artist", "Title2", "api_key")
            assert mood == "energetic"
            assert source == "musicbrainz"

    def test_both_fail_returns_none(self):
        """Should return (None, 'none') when both services fail."""
        _cached_online_lookup.cache_clear()
        with patch("vdj_manager.analysis.online_mood.LastFmLookup") as MockLfm, \
             patch("vdj_manager.analysis.online_mood.MusicBrainzLookup") as MockMb:
            MockLfm.return_value.get_mood.return_value = None
            MockMb.return_value.get_mood.return_value = None
            mood, source = lookup_online_mood("Artist", "Title3", "api_key")
            assert mood is None
            assert source == "none"

    def test_no_artist_title_returns_none(self):
        """Should return (None, 'none') when artist/title are missing."""
        mood, source = lookup_online_mood("", "", "api_key")
        assert mood is None
        assert source == "none"

        mood, source = lookup_online_mood("", "Title", "api_key")
        assert mood is None
        assert source == "none"

    def test_no_api_key_skips_lastfm(self):
        """Should skip Last.fm when no API key provided."""
        _cached_online_lookup.cache_clear()
        with patch("vdj_manager.analysis.online_mood.LastFmLookup") as MockLfm, \
             patch("vdj_manager.analysis.online_mood.MusicBrainzLookup") as MockMb:
            MockMb.return_value.get_mood.return_value = "relaxing"
            mood, source = lookup_online_mood("Artist", "Title4", None)
            assert mood == "relaxing"
            assert source == "musicbrainz"
            MockLfm.return_value.get_mood.assert_not_called()


# =============================================================================
# TAG_TO_MOOD coverage
# =============================================================================


class TestTagToMoodDict:
    """Tests for the TAG_TO_MOOD mapping dictionary."""

    def test_all_values_are_56_class_moods(self):
        from vdj_manager.analysis.mood_backend import MOOD_CLASSES_SET

        for tag, mood in TAG_TO_MOOD.items():
            assert mood in MOOD_CLASSES_SET, (
                f"Tag '{tag}' maps to '{mood}' which is not in MOOD_CLASSES"
            )

    def test_all_keys_are_lowercase(self):
        for tag in TAG_TO_MOOD:
            assert tag == tag.lower(), f"Tag '{tag}' is not lowercase"

    def test_minimum_tag_count(self):
        """Should have a reasonable number of tag mappings."""
        assert len(TAG_TO_MOOD) >= 100
