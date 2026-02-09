"""Online mood enrichment via Last.fm and MusicBrainz.

Provides tiered online lookup: Last.fm tags -> MusicBrainz genres -> None.
Maps freeform tags/genres to the 56-class MTG-Jamendo mood vocabulary.
"""

import threading
import time
from functools import lru_cache
from typing import Optional


# ---------------------------------------------------------------------------
# Tag-to-mood mapping
# ---------------------------------------------------------------------------

TAG_TO_MOOD: dict[str, str] = {
    # --- happy ---
    "happy": "happy",
    "joyful": "happy",
    "cheerful": "happy",
    "feel good": "happy",
    "feel-good": "happy",
    "feelgood": "happy",
    "euphoric": "happy",
    "euphoria": "happy",
    "optimistic": "happy",
    "sunny": "happy",
    # uplifting (now a dedicated class)
    "uplifting": "uplifting",
    "inspiring": "inspiring",
    "inspirational": "inspiring",
    "motivational": "motivational",
    "hopeful": "hopeful",
    # upbeat (now a dedicated class)
    "upbeat": "upbeat",
    # positive (now a dedicated class)
    "positive": "positive",
    # fun (now a dedicated class)
    "fun": "fun",
    "funny": "funny",
    "humorous": "funny",
    # summer (now a dedicated class)
    "summer": "summer",
    "holiday": "holiday",
    "christmas": "christmas",
    "xmas": "christmas",
    # --- sad ---
    "sad": "sad",
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
    # melancholic (now a dedicated class)
    "melancholic": "melancholic",
    "melancholy": "melancholic",
    "wistful": "melancholic",
    "bittersweet": "melancholic",
    "nostalgic": "melancholic",
    # emotional (now a dedicated class)
    "emotional": "emotional",
    "emotive": "emotional",
    # --- dark / heavy ---
    "dark": "dark",
    "aggressive": "heavy",
    "anger": "heavy",
    "angry": "heavy",
    "heavy": "heavy",
    "brutal": "heavy",
    "rage": "heavy",
    "violent": "heavy",
    "fierce": "heavy",
    "metal": "heavy",
    "hardcore": "heavy",
    "thrash": "heavy",
    "death metal": "heavy",
    "black metal": "heavy",
    "grindcore": "heavy",
    "hard rock": "heavy",
    "punk": "heavy",
    "hard": "heavy",
    "intense": "powerful",
    # powerful (now a dedicated class)
    "powerful": "powerful",
    # dramatic (now a dedicated class)
    "dramatic": "dramatic",
    "drama": "drama",
    # epic (now a dedicated class)
    "epic": "epic",
    "cinematic": "epic",
    "trailer": "trailer",
    "film": "film",
    "movie": "movie",
    "soundtrack": "film",
    # --- calm / relaxed ---
    "calm": "calm",
    "relaxed": "relaxing",
    "relaxing": "relaxing",
    "chill": "calm",
    "mellow": "calm",
    "ambient": "soundscape",
    "soundscape": "soundscape",
    "atmospheric": "soundscape",
    "downtempo": "slow",
    "easy listening": "soft",
    "lounge": "soft",
    "smooth": "soft",
    "peaceful": "calm",
    "soothing": "relaxing",
    "chillout": "calm",
    "new age": "meditative",
    "trip-hop": "deep",
    "soft": "soft",
    "slow": "slow",
    # dreamy (now maps to dream class)
    "dreamy": "dream",
    "dream": "dream",
    # meditative (now a dedicated class)
    "meditative": "meditative",
    "meditation": "meditative",
    # deep (now a dedicated class)
    "deep": "deep",
    # nature (now a dedicated class)
    "nature": "nature",
    # space (now a dedicated class)
    "space": "space",
    "cosmic": "space",
    # --- romantic / love ---
    "romantic": "romantic",
    "love": "love",
    "sexy": "sexy",
    "sensual": "sexy",
    # ballad (now a dedicated class)
    "ballad": "ballad",
    # melodic (now a dedicated class)
    "melodic": "melodic",
    # --- energetic / party ---
    "energetic": "energetic",
    "energy": "energetic",
    "fast": "fast",
    "party": "party",
    "dance": "party",
    "danceable": "party",
    "club": "party",
    "dancefloor": "party",
    "disco": "party",
    "pop": "party",
    "reggaeton": "party",
    "latin": "party",
    "tropical": "summer",
    "hip-hop": "party",
    "hip hop": "party",
    "rap": "party",
    "r&b": "party",
    "rnb": "party",
    "funk": "groovy",
    "soul": "emotional",
    # groovy (now a dedicated class)
    "groovy": "groovy",
    # cool (now a dedicated class)
    "cool": "cool",
    # retro (now a dedicated class)
    "retro": "retro",
    "vintage": "retro",
    # sport (now a dedicated class)
    "sport": "sport",
    "workout": "sport",
    "gym": "sport",
    "fitness": "sport",
    # --- category-like / production ---
    "acoustic": "soft",
    "folk": "soft",
    "singer-songwriter": "ballad",
    "singer songwriter": "ballad",
    "unplugged": "soft",
    "bluegrass": "background",
    "country": "background",
    "blues": "emotional",
    "jazz": "cool",
    "bossa nova": "relaxing",
    "classical": "melodic",
    "piano": "melodic",
    "guitar": "melodic",
    "electronic": "energetic",
    "edm": "energetic",
    "techno": "energetic",
    "house": "energetic",
    "trance": "energetic",
    "drum and bass": "fast",
    "dubstep": "heavy",
    "synthwave": "retro",
    "electronica": "deep",
    "synth": "retro",
    "synth-pop": "retro",
    "synthpop": "retro",
    "industrial": "dark",
    "idm": "deep",
    "deep house": "deep",
    "progressive house": "deep",
    "electro": "energetic",
    "minimal": "deep",
    # --- commercial / production ---
    "commercial": "commercial",
    "corporate": "corporate",
    "advertising": "advertising",
    "documentary": "documentary",
    "background": "background",
    "children": "children",
    "kids": "children",
    # adventure / action / game
    "adventure": "adventure",
    "action": "action",
    "game": "game",
    "gaming": "game",
    # travel
    "travel": "travel",
    "wanderlust": "travel",
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
