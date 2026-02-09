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
    _clean_artist,
    _clean_title,
    _retry_on_network_error,
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

    def test_lastfm_track_fails_tries_artist(self):
        """Should fall back to artist tags when track tags are empty."""
        _cached_online_lookup.cache_clear()
        with patch("vdj_manager.analysis.online_mood.LastFmLookup") as MockLfm, \
             patch("vdj_manager.analysis.online_mood.MusicBrainzLookup") as MockMb:
            MockLfm.return_value.get_mood.return_value = None
            MockLfm.return_value.get_mood_from_artist.return_value = "party"
            mood, source = lookup_online_mood("Artist", "Title2", "api_key")
            assert mood == "party"
            assert source == "lastfm-artist"
            MockMb.return_value.get_mood.assert_not_called()

    def test_lastfm_all_fail_tries_mb(self):
        """Should fall back to MusicBrainz when all Last.fm lookups fail."""
        _cached_online_lookup.cache_clear()
        with patch("vdj_manager.analysis.online_mood.LastFmLookup") as MockLfm, \
             patch("vdj_manager.analysis.online_mood.MusicBrainzLookup") as MockMb:
            MockLfm.return_value.get_mood.return_value = None
            MockLfm.return_value.get_mood_from_artist.return_value = None
            MockMb.return_value.get_mood.return_value = "energetic"
            mood, source = lookup_online_mood("Artist", "Title5", "api_key")
            assert mood == "energetic"
            assert source == "musicbrainz"

    def test_all_fail_returns_none(self):
        """Should return (None, 'none') when all services fail."""
        _cached_online_lookup.cache_clear()
        with patch("vdj_manager.analysis.online_mood.LastFmLookup") as MockLfm, \
             patch("vdj_manager.analysis.online_mood.MusicBrainzLookup") as MockMb:
            MockLfm.return_value.get_mood.return_value = None
            MockLfm.return_value.get_mood_from_artist.return_value = None
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

    def test_cleaning_applied_before_lookup(self):
        """Metadata should be cleaned before querying online services."""
        _cached_online_lookup.cache_clear()
        with patch("vdj_manager.analysis.online_mood.LastFmLookup") as MockLfm, \
             patch("vdj_manager.analysis.online_mood.MusicBrainzLookup"):
            MockLfm.return_value.get_mood.return_value = "happy"
            lookup_online_mood(
                "Jason Derulo feat. Nicki Minaj", "Swalla (Remix)", "key"
            )
            # Should have been called with cleaned values
            MockLfm.return_value.get_mood.assert_called_once_with(
                "Jason Derulo", "Swalla"
            )


# =============================================================================
# _clean_artist tests
# =============================================================================


class TestCleanArtist:
    """Tests for artist metadata cleaning."""

    def test_strips_feat(self):
        assert _clean_artist("Jason Derulo feat. Nicki Minaj") == "Jason Derulo"

    def test_strips_ft(self):
        assert _clean_artist("Drake ft. Rihanna") == "Drake"

    def test_strips_featuring(self):
        assert _clean_artist("Eminem featuring Dido") == "Eminem"

    def test_strips_comma_separated(self):
        assert _clean_artist("Kenny G, Robin Thicke") == "Kenny G"

    def test_strips_ampersand(self):
        assert _clean_artist("Simon & Garfunkel") == "Simon"

    def test_strips_slash(self):
        assert _clean_artist("Artist1 / Artist2") == "Artist1"

    def test_feat_plus_comma(self):
        assert _clean_artist("DJ Khaled feat. Rihanna, Bryson Tiller") == "DJ Khaled"

    def test_no_change_needed(self):
        assert _clean_artist("Adele") == "Adele"

    def test_empty_returns_original(self):
        assert _clean_artist("") == ""

    def test_preserves_original_if_cleaning_empty(self):
        # Edge case: if splitting produces empty, return original stripped
        assert _clean_artist("  Adele  ") == "Adele"


# =============================================================================
# _clean_title tests
# =============================================================================


class TestCleanTitle:
    """Tests for title metadata cleaning."""

    def test_strips_parenthetical(self):
        assert _clean_title("Swalla (Remix)") == "Swalla"

    def test_strips_brackets(self):
        assert _clean_title("Song [Radio Edit]") == "Song"

    def test_strips_feat_suffix(self):
        assert _clean_title("U Move, I Move - feat. Jhene Aiko") == "U Move, I Move"

    def test_strips_ft_suffix(self):
        assert _clean_title("Song - ft. Someone") == "Song"

    def test_deduplicates_dash_title(self):
        assert _clean_title("Samjho Na - Samjho Na") == "Samjho Na"

    def test_keeps_different_dash_parts(self):
        assert _clean_title("Album - Song Title") == "Album - Song Title"

    def test_strips_multiple_parens(self):
        assert _clean_title("Song (feat. X) (Remix)") == "Song"

    def test_no_change_needed(self):
        assert _clean_title("Normal Title") == "Normal Title"

    def test_empty_returns_original(self):
        assert _clean_title("") == ""

    def test_preserves_original_if_cleaning_empty(self):
        # If everything is in parens, return original
        assert _clean_title("(Remix)") == "(Remix)"

    def test_en_dash_feat(self):
        assert _clean_title("Song \u2013 feat. Artist") == "Song"


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


# =============================================================================
# _retry_on_network_error tests
# =============================================================================


class TestRetryOnNetworkError:
    """Tests for the retry-with-backoff mechanism."""

    def test_success_on_first_try(self):
        """Should return result immediately when no error."""
        result = _retry_on_network_error(lambda: "ok")
        assert result == "ok"

    def test_success_after_connection_error(self):
        """Should retry and succeed after a ConnectionError."""
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection reset by peer")
            return "recovered"

        with patch("vdj_manager.analysis.online_mood.time.sleep"):
            result = _retry_on_network_error(flaky)
        assert result == "recovered"
        assert call_count == 3

    def test_success_after_os_error(self):
        """Should retry on OSError (e.g. errno 54)."""
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError(54, "Connection reset by peer")
            return "ok"

        with patch("vdj_manager.analysis.online_mood.time.sleep"):
            result = _retry_on_network_error(flaky)
        assert result == "ok"
        assert call_count == 2

    def test_success_after_url_error(self):
        """Should retry on URLError."""
        from urllib.error import URLError

        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise URLError("connection refused")
            return "ok"

        with patch("vdj_manager.analysis.online_mood.time.sleep"):
            result = _retry_on_network_error(flaky)
        assert result == "ok"
        assert call_count == 2

    def test_all_retries_exhausted_returns_none(self):
        """Should return None after all retries fail."""
        with patch("vdj_manager.analysis.online_mood.time.sleep"):
            result = _retry_on_network_error(
                lambda: (_ for _ in ()).throw(ConnectionError("fail")),
                max_retries=2,
            )
        assert result is None

    def test_non_network_error_not_retried(self):
        """Non-network errors should propagate immediately."""
        call_count = 0

        def bad():
            nonlocal call_count
            call_count += 1
            raise ValueError("not a network error")

        with pytest.raises(ValueError, match="not a network error"):
            _retry_on_network_error(bad)
        assert call_count == 1

    def test_exponential_backoff_timing(self):
        """Should sleep with exponential backoff between retries."""
        with patch("vdj_manager.analysis.online_mood.time.sleep") as mock_sleep:
            _retry_on_network_error(
                lambda: (_ for _ in ()).throw(ConnectionError("fail")),
                max_retries=3,
                base_delay=1.0,
            )
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(1.0)   # attempt 0: 1.0 * 2^0
        mock_sleep.assert_any_call(2.0)   # attempt 1: 1.0 * 2^1
        mock_sleep.assert_any_call(4.0)   # attempt 2: 1.0 * 2^2

    def test_zero_retries_returns_none_on_error(self):
        """With max_retries=0, should try once and return None on error."""
        call_count = 0

        def fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        result = _retry_on_network_error(fail, max_retries=0)
        assert result is None
        assert call_count == 1

    def test_extra_exceptions_are_retried(self):
        """Custom exception types passed via extra_exceptions should be retried."""
        class LibraryNetworkError(Exception):
            pass

        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise LibraryNetworkError("wrapped connection reset")
            return "recovered"

        with patch("vdj_manager.analysis.online_mood.time.sleep"):
            result = _retry_on_network_error(
                flaky, extra_exceptions=(LibraryNetworkError,)
            )
        assert result == "recovered"
        assert call_count == 3

    def test_extra_exceptions_not_retried_without_param(self):
        """Custom exceptions should NOT be retried if not passed to extra_exceptions."""
        class LibraryNetworkError(Exception):
            pass

        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            raise LibraryNetworkError("not retried")

        with pytest.raises(LibraryNetworkError):
            _retry_on_network_error(flaky)
        assert call_count == 1


class TestLastFmRetryIntegration:
    """Tests verifying retry logic is wired into Last.fm lookups."""

    def test_lastfm_get_mood_retries_on_connection_reset(self):
        """Last.fm get_mood should retry on ConnectionResetError."""
        call_count = 0
        mock_tag = MagicMock()
        mock_tag.item.get_name.return_value = "chill"
        mock_tag.weight = "100"

        mock_track = MagicMock()
        mock_track.get_top_tags.return_value = [mock_tag]

        mock_network = MagicMock()

        def flaky_get_track(artist, title):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionResetError("Connection reset by peer")
            return mock_track

        mock_network.get_track.side_effect = flaky_get_track

        with patch.dict("sys.modules", {"pylast": MagicMock()}), \
             patch("vdj_manager.analysis.online_mood.time.sleep"):
            import pylast
            # Set up real exception classes so except clauses work
            pylast.NetworkError = type("NetworkError", (Exception,), {})
            pylast.WSError = type("WSError", (Exception,), {})
            pylast.MalformedResponseError = type("MalformedResponseError", (Exception,), {})
            pylast.LastFMNetwork.return_value = mock_network
            lookup = LastFmLookup(api_key="test_key")
            result = lookup.get_mood("Artist", "Title")
            assert result == "calm"
            assert call_count == 3

    def test_lastfm_get_mood_from_artist_retries(self):
        """Last.fm get_mood_from_artist should retry on ConnectionError."""
        call_count = 0
        mock_tag = MagicMock()
        mock_tag.item.get_name.return_value = "dance"
        mock_tag.weight = "100"

        mock_artist = MagicMock()
        mock_artist.get_top_tags.return_value = [mock_tag]

        mock_network = MagicMock()

        def flaky_get_artist(artist):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Connection refused")
            return mock_artist

        mock_network.get_artist.side_effect = flaky_get_artist

        with patch.dict("sys.modules", {"pylast": MagicMock()}), \
             patch("vdj_manager.analysis.online_mood.time.sleep"):
            import pylast
            # Set up real exception classes so except clauses work
            pylast.NetworkError = type("NetworkError", (Exception,), {})
            pylast.WSError = type("WSError", (Exception,), {})
            pylast.MalformedResponseError = type("MalformedResponseError", (Exception,), {})
            pylast.LastFMNetwork.return_value = mock_network
            lookup = LastFmLookup(api_key="test_key")
            result = lookup.get_mood_from_artist("Artist")
            assert result == "party"
            assert call_count == 2


class TestMusicBrainzRetryIntegration:
    """Tests verifying retry logic is wired into MusicBrainz lookups."""

    def test_musicbrainz_retries_on_connection_reset(self):
        """MusicBrainz should retry on ConnectionResetError."""
        call_count = 0
        mock_result = {
            "recording-list": [{
                "tag-list": [{"name": "electronic"}, {"name": "dance"}]
            }]
        }

        with patch.dict("sys.modules", {"musicbrainzngs": MagicMock()}) as mods, \
             patch("vdj_manager.analysis.online_mood.time.sleep"):
            import musicbrainzngs
            # Set up real exception class so except clause works
            musicbrainzngs.NetworkError = type("NetworkError", (Exception,), {})

            def flaky_search(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise ConnectionResetError("[Errno 54] Connection reset by peer")
                return mock_result

            musicbrainzngs.search_recordings.side_effect = flaky_search
            lookup = MusicBrainzLookup()
            result = lookup.get_mood("Artist", "Title")
            assert result in ("energetic", "party")
            assert call_count == 2

    def test_musicbrainz_retries_on_library_network_error(self):
        """MusicBrainz should retry on musicbrainzngs.NetworkError (wraps URLError)."""
        call_count = 0
        mock_result = {
            "recording-list": [{
                "tag-list": [{"name": "electronic"}, {"name": "dance"}]
            }]
        }

        with patch.dict("sys.modules", {"musicbrainzngs": MagicMock()}) as mods, \
             patch("vdj_manager.analysis.online_mood.time.sleep"):
            import musicbrainzngs
            # Create a real-ish NetworkError class (like the library does)
            musicbrainzngs.NetworkError = type("NetworkError", (Exception,), {})

            def flaky_search(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise musicbrainzngs.NetworkError(
                        "caused by: <urlopen error [Errno 54] Connection reset by peer>"
                    )
                return mock_result

            musicbrainzngs.search_recordings.side_effect = flaky_search
            lookup = MusicBrainzLookup()
            result = lookup.get_mood("Artist", "Title")
            assert result in ("energetic", "party")
            assert call_count == 3

    def test_musicbrainz_all_retries_exhausted(self):
        """MusicBrainz should return None when all retries fail."""
        with patch.dict("sys.modules", {"musicbrainzngs": MagicMock()}) as mods, \
             patch("vdj_manager.analysis.online_mood.time.sleep"):
            import musicbrainzngs
            musicbrainzngs.NetworkError = type("NetworkError", (Exception,), {})
            musicbrainzngs.search_recordings.side_effect = musicbrainzngs.NetworkError(
                "caused by: <urlopen error [Errno 54] Connection reset by peer>"
            )
            lookup = MusicBrainzLookup()
            result = lookup.get_mood("Artist", "Title")
            assert result is None
