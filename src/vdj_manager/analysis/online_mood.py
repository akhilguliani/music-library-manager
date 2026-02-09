"""Online mood enrichment via Last.fm and MusicBrainz.

Provides tiered online lookup: Last.fm tags -> MusicBrainz genres -> None.
Maps freeform tags/genres to the 56-class MTG-Jamendo mood vocabulary.
Cleans metadata (feat., remix, etc.) before querying for better hit rates.
"""

import logging
import re
import threading
import time
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Metadata cleaning
# ---------------------------------------------------------------------------

_FEAT_SPLIT_RE = re.compile(
    r"\s+feat\.?\s+|\s+ft\.?\s+|\s+featuring\s+",
    re.IGNORECASE,
)

_ARTIST_SPLIT_RE = re.compile(
    r",\s*|\s+&\s+|\s*/\s*",
)


def _clean_artist(author: str) -> str:
    """Extract primary artist name for online lookup.

    Strips featured artists and takes the first from comma/&/slash-separated
    lists.  E.g. ``'Jason Derulo feat. Nicki Minaj & Ty Dolla $ign'``
    becomes ``'Jason Derulo'``.
    """
    # Remove feat/ft portions first
    parts = _FEAT_SPLIT_RE.split(author, maxsplit=1)
    name = parts[0]
    # Then take first artist from comma / & / slash list
    name = _ARTIST_SPLIT_RE.split(name, maxsplit=1)[0]
    cleaned = name.strip()
    return cleaned or author.strip()


def _clean_title(title: str) -> str:
    """Remove noise from title for better online matching.

    Strips parenthetical info ``(Remix)``, bracket info ``[Remix]``,
    ``- feat./ft.`` suffixes, and handles ``'Album - Title'`` duplication
    like ``'Samjho Na - Samjho Na'``.
    """
    t = title
    # Remove (...) and [...] content
    t = re.sub(r"\s*\([^)]*\)", "", t)
    t = re.sub(r"\s*\[[^\]]*\]", "", t)
    # Remove '- feat./ft. ...' suffixes
    t = re.sub(r"\s*[-–]\s*(?:feat\.?|ft\.?).*$", "", t, flags=re.IGNORECASE)
    # Handle 'Album - Title' duplication: take last dash-separated part
    if " - " in t:
        parts = [p.strip() for p in t.split(" - ")]
        # If two identical parts, use just one
        if len(parts) == 2 and parts[0].lower() == parts[1].lower():
            t = parts[0]
    cleaned = t.strip()
    return cleaned or title.strip()


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
            logger.warning("Last.fm track lookup failed for %s - %s", artist, title, exc_info=True)
            return None

    def get_mood_from_artist(self, artist: str) -> Optional[str]:
        """Get mood from artist's top tags (fallback when track has no tags).

        Args:
            artist: Artist name.

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
            artist_obj = network.get_artist(artist)
            top_tags = artist_obj.get_top_tags(limit=15)
            tags = [(t.item.get_name(), int(t.weight)) for t in top_tags]
            return self._mapper.map_tags(tags)
        except (pylast.WSError, pylast.NetworkError, pylast.MalformedResponseError):
            return None
        except Exception:
            logger.warning("Last.fm artist lookup failed for %s", artist, exc_info=True)
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
            logger.warning("MusicBrainz lookup failed for %s - %s", artist, title, exc_info=True)
            return None


# ---------------------------------------------------------------------------
# Top-level picklable lookup function
# ---------------------------------------------------------------------------

@lru_cache(maxsize=2048)
def _cached_online_lookup(
    artist: str, title: str, lastfm_api_key: Optional[str]
) -> tuple[Optional[str], str]:
    """Cached online lookup (deduplicates identical artist+title pairs).

    Cleans metadata before querying and falls back to artist-level tags
    when track-level tags are empty.

    Returns:
        (mood, source) where source is "lastfm", "lastfm-artist",
        "musicbrainz", or "none".
    """
    clean_a = _clean_artist(artist)
    clean_t = _clean_title(title)

    # Try Last.fm track tags (cleaned)
    if lastfm_api_key:
        lfm = LastFmLookup(lastfm_api_key)
        mood = lfm.get_mood(clean_a, clean_t)
        if mood:
            return mood, "lastfm"

        # Fall back to Last.fm artist tags
        mood = lfm.get_mood_from_artist(clean_a)
        if mood:
            return mood, "lastfm-artist"

    # Fall back to MusicBrainz (cleaned)
    mb = MusicBrainzLookup()
    mood = mb.get_mood(clean_a, clean_t)
    if mood:
        return mood, "musicbrainz"

    return None, "none"


def lookup_online_mood(
    artist: str,
    title: str,
    lastfm_api_key: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """Look up mood from online databases.

    Cleans artist/title metadata, then tries Last.fm track tags,
    Last.fm artist tags, and MusicBrainz in order. Uses LRU cache
    internally to deduplicate identical artist+title pairs.

    Args:
        artist: Artist name (may contain feat., commas, etc.).
        title: Track title (may contain remix info, parentheticals, etc.).
        lastfm_api_key: Optional Last.fm API key.

    Returns:
        (mood, source) tuple. source is "lastfm", "lastfm-artist",
        "musicbrainz", or "none".
    """
    if not artist or not title:
        return None, "none"
    return _cached_online_lookup(artist, title, lastfm_api_key)
