"""Online mood enrichment via Last.fm and MusicBrainz.

Provides tiered online lookup: Last.fm tags -> MusicBrainz genres -> None.
Maps freeform tags/genres to 7 canonical moods used by VDJ Manager.
"""

import threading
import time
from functools import lru_cache
from typing import Optional


# ---------------------------------------------------------------------------
# Tag-to-mood mapping
# ---------------------------------------------------------------------------

TAG_TO_MOOD: dict[str, str] = {
    # happy
    "happy": "happy",
    "uplifting": "happy",
    "feel good": "happy",
    "feel-good": "happy",
    "joyful": "happy",
    "cheerful": "happy",
    "upbeat": "happy",
    "fun": "happy",
    "sunny": "happy",
    "positive": "happy",
    "euphoric": "happy",
    "euphoria": "happy",
    "optimistic": "happy",
    "feelgood": "happy",
    "summer": "happy",
    # sad
    "sad": "sad",
    "melancholy": "sad",
    "melancholic": "sad",
    "depressing": "sad",
    "heartbreak": "sad",
    "heartbroken": "sad",
    "lonely": "sad",
    "loneliness": "sad",
    "somber": "sad",
    "sombre": "sad",
    "mournful": "sad",
    "grief": "sad",
    "tearful": "sad",
    "gloomy": "sad",
    "wistful": "sad",
    "bittersweet": "sad",
    # aggressive
    "aggressive": "aggressive",
    "anger": "aggressive",
    "angry": "aggressive",
    "intense": "aggressive",
    "heavy": "aggressive",
    "hard": "aggressive",
    "brutal": "aggressive",
    "rage": "aggressive",
    "violent": "aggressive",
    "fierce": "aggressive",
    "dark": "aggressive",
    "metal": "aggressive",
    "hardcore": "aggressive",
    "thrash": "aggressive",
    "death metal": "aggressive",
    "black metal": "aggressive",
    "grindcore": "aggressive",
    "hard rock": "aggressive",
    "punk": "aggressive",
    # relaxed
    "relaxed": "relaxed",
    "chill": "relaxed",
    "calm": "relaxed",
    "mellow": "relaxed",
    "ambient": "relaxed",
    "downtempo": "relaxed",
    "easy listening": "relaxed",
    "lounge": "relaxed",
    "smooth": "relaxed",
    "peaceful": "relaxed",
    "soothing": "relaxed",
    "dreamy": "relaxed",
    "atmospheric": "relaxed",
    "meditative": "relaxed",
    "chillout": "relaxed",
    "new age": "relaxed",
    "trip-hop": "relaxed",
    # acoustic
    "acoustic": "acoustic",
    "folk": "acoustic",
    "singer-songwriter": "acoustic",
    "unplugged": "acoustic",
    "singer songwriter": "acoustic",
    "bluegrass": "acoustic",
    "country": "acoustic",
    "blues": "acoustic",
    "jazz": "acoustic",
    "bossa nova": "acoustic",
    "classical": "acoustic",
    "piano": "acoustic",
    "guitar": "acoustic",
    # electronic
    "electronic": "electronic",
    "edm": "electronic",
    "techno": "electronic",
    "house": "electronic",
    "trance": "electronic",
    "drum and bass": "electronic",
    "dubstep": "electronic",
    "synthwave": "electronic",
    "electronica": "electronic",
    "synth": "electronic",
    "synth-pop": "electronic",
    "synthpop": "electronic",
    "industrial": "electronic",
    "idm": "electronic",
    "deep house": "electronic",
    "progressive house": "electronic",
    "electro": "electronic",
    "minimal": "electronic",
    # party
    "party": "party",
    "dance": "party",
    "danceable": "party",
    "club": "party",
    "dancefloor": "party",
    "groovy": "party",
    "disco": "party",
    "pop": "party",
    "reggaeton": "party",
    "latin": "party",
    "tropical": "party",
    "hip-hop": "party",
    "hip hop": "party",
    "rap": "party",
    "r&b": "party",
    "rnb": "party",
    "funk": "party",
    "soul": "party",
}


class TagToMoodMapper:
    """Maps freeform tags/genres to canonical moods via weighted scoring."""

    def map_tags(self, tags: list[tuple[str, int]]) -> Optional[str]:
        """Map Last.fm tags (name, count) to a mood using weighted scoring.

        Args:
            tags: List of (tag_name, count) tuples from Last.fm.

        Returns:
            Canonical mood string or None if no match.
        """
        if not tags:
            return None

        scores: dict[str, float] = {}
        for tag_name, count in tags:
            mood = TAG_TO_MOOD.get(tag_name.lower().strip())
            if mood:
                scores[mood] = scores.get(mood, 0.0) + count

        if not scores:
            return None
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def map_genres(self, genres: list[str]) -> Optional[str]:
        """Map MusicBrainz genres to a mood using unweighted scoring.

        Args:
            genres: List of genre strings.

        Returns:
            Canonical mood string or None if no match.
        """
        if not genres:
            return None

        scores: dict[str, int] = {}
        for genre in genres:
            mood = TAG_TO_MOOD.get(genre.lower().strip())
            if mood:
                scores[mood] = scores.get(mood, 0) + 1

        if not scores:
            return None
        return max(scores, key=scores.get)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Thread-safe token-bucket rate limiter."""

    def __init__(self, rate: float) -> None:
        """Initialize rate limiter.

        Args:
            rate: Maximum requests per second.
        """
        self._rate = rate
        self._lock = threading.Lock()
        self._last_time = 0.0

    def wait(self) -> None:
        """Block until a request is allowed."""
        with self._lock:
            now = time.monotonic()
            min_interval = 1.0 / self._rate
            elapsed = now - self._last_time
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_time = time.monotonic()


# Module-level rate limiters
_lastfm_limiter = _RateLimiter(rate=5.0)
_musicbrainz_limiter = _RateLimiter(rate=1.0)


# ---------------------------------------------------------------------------
# Last.fm lookup
# ---------------------------------------------------------------------------

class LastFmLookup:
    """Look up mood from Last.fm track tags."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._mapper = TagToMoodMapper()

    def get_mood(self, artist: str, title: str) -> Optional[str]:
        """Get mood for a track from Last.fm top tags.

        Args:
            artist: Artist name.
            title: Track title.

        Returns:
            Canonical mood string or None.
        """
        try:
            import pylast
        except ImportError:
            return None

        try:
            _lastfm_limiter.wait()
            network = pylast.LastFMNetwork(api_key=self._api_key)
            track = network.get_track(artist, title)
            top_tags = track.get_top_tags(limit=15)
            tags = [(t.item.get_name(), int(t.weight)) for t in top_tags]
            return self._mapper.map_tags(tags)
        except (pylast.WSError, pylast.NetworkError, pylast.MalformedResponseError):
            return None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# MusicBrainz lookup
# ---------------------------------------------------------------------------

class MusicBrainzLookup:
    """Look up mood from MusicBrainz genres."""

    def __init__(self) -> None:
        self._mapper = TagToMoodMapper()

    def get_mood(self, artist: str, title: str) -> Optional[str]:
        """Get mood for a track from MusicBrainz genres.

        Args:
            artist: Artist name.
            title: Track title.

        Returns:
            Canonical mood string or None.
        """
        try:
            import musicbrainzngs
        except ImportError:
            return None

        try:
            _musicbrainz_limiter.wait()
            musicbrainzngs.set_useragent("VDJ-Manager", "0.1.0", "")
            result = musicbrainzngs.search_recordings(
                artist=artist, recording=title, limit=1
            )
            recordings = result.get("recording-list", [])
            if not recordings:
                return None

            # Extract genres/tags from the first match
            recording = recordings[0]
            genres: list[str] = []
            for tag in recording.get("tag-list", []):
                genres.append(tag.get("name", ""))
            return self._mapper.map_genres(genres)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Top-level picklable lookup function
# ---------------------------------------------------------------------------

@lru_cache(maxsize=2048)
def _cached_online_lookup(
    artist: str, title: str, lastfm_api_key: Optional[str]
) -> tuple[Optional[str], str]:
    """Cached online lookup (deduplicates identical artist+title pairs).

    Returns:
        (mood, source) where source is "lastfm", "musicbrainz", or "none".
    """
    # Try Last.fm first
    if lastfm_api_key:
        lfm = LastFmLookup(lastfm_api_key)
        mood = lfm.get_mood(artist, title)
        if mood:
            return mood, "lastfm"

    # Fall back to MusicBrainz
    mb = MusicBrainzLookup()
    mood = mb.get_mood(artist, title)
    if mood:
        return mood, "musicbrainz"

    return None, "none"


def lookup_online_mood(
    artist: str,
    title: str,
    lastfm_api_key: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """Look up mood from online databases.

    Tries Last.fm first, then MusicBrainz, returns None if both fail.
    Uses LRU cache internally to deduplicate identical artist+title
    pairs within a batch run.

    Args:
        artist: Artist name.
        title: Track title.
        lastfm_api_key: Optional Last.fm API key.

    Returns:
        (mood, source) tuple. source is "lastfm", "musicbrainz", or "none".
    """
    if not artist or not title:
        return None, "none"
    return _cached_online_lookup(artist, title, lastfm_api_key)
