"""Online genre enrichment via Last.fm and MusicBrainz.

Provides tiered online lookup: Last.fm tags -> MusicBrainz genres -> None.
Maps freeform tags/genres to canonical DJ genre names.
Reuses rate limiters and metadata cleaning from online_mood.
"""

import logging
from functools import lru_cache

from .online_mood import (
    _clean_artist,
    _clean_title,
    _lastfm_limiter,
    _musicbrainz_limiter,
    _retry_on_network_error,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tag-to-genre mapping
# ---------------------------------------------------------------------------

TAG_TO_GENRE: dict[str, str] = {
    # --- House family ---
    "house": "House",
    "house music": "House",
    "deep house": "Deep House",
    "deep-house": "Deep House",
    "tech house": "Tech House",
    "tech-house": "Tech House",
    "progressive house": "Progressive House",
    "prog house": "Progressive House",
    "afro house": "Afro House",
    "afro-house": "Afro House",
    "melodic house": "Melodic House",
    "organic house": "Organic House",
    "acid house": "Acid House",
    "funky house": "Funky House",
    "soulful house": "Soulful House",
    "chicago house": "House",
    # --- Techno family ---
    "techno": "Techno",
    "minimal techno": "Minimal Techno",
    "minimal": "Minimal Techno",
    "hard techno": "Hard Techno",
    "industrial techno": "Hard Techno",
    "acid techno": "Techno",
    "detroit techno": "Techno",
    "dub techno": "Techno",
    # --- Trance family ---
    "trance": "Trance",
    "progressive trance": "Progressive Trance",
    "prog trance": "Progressive Trance",
    "psytrance": "Psytrance",
    "psy trance": "Psytrance",
    "psy-trance": "Psytrance",
    "goa trance": "Psytrance",
    "uplifting trance": "Trance",
    "vocal trance": "Trance",
    # --- Bass music ---
    "drum and bass": "Drum & Bass",
    "drum & bass": "Drum & Bass",
    "drum n bass": "Drum & Bass",
    "drum'n'bass": "Drum & Bass",
    "dnb": "Drum & Bass",
    "d&b": "Drum & Bass",
    "jungle": "Drum & Bass",
    "liquid funk": "Drum & Bass",
    "dubstep": "Dubstep",
    "brostep": "Dubstep",
    "bass music": "Bass",
    "bass": "Bass",
    # --- Garage / UK ---
    "garage": "Garage",
    "uk garage": "UK Garage",
    "speed garage": "UK Garage",
    "2-step": "UK Garage",
    "2 step": "UK Garage",
    "grime": "Grime",
    "uk funky": "UK Garage",
    # --- EDM / Electronic ---
    "edm": "EDM",
    "electronic dance music": "EDM",
    "electronic": "Electronic",
    "electronica": "Electronic",
    "electro": "Electro",
    "electro house": "Electro",
    "breakbeat": "Breakbeat",
    "breaks": "Breakbeat",
    "big beat": "Breakbeat",
    "idm": "IDM",
    "intelligent dance music": "IDM",
    "synthwave": "Synthwave",
    "retrowave": "Synthwave",
    "vaporwave": "Vaporwave",
    "future bass": "Future Bass",
    "future house": "Future House",
    "trap": "Trap",
    "trap music": "Trap",
    "hardstyle": "Hardstyle",
    "hard dance": "Hardstyle",
    "gabber": "Hardcore",
    "happy hardcore": "Hardcore",
    "hardcore": "Hardcore",
    # --- Disco / Funk / Soul ---
    "disco": "Disco",
    "nu-disco": "Nu-Disco",
    "nu disco": "Nu-Disco",
    "italo disco": "Disco",
    "funk": "Funk",
    "soul": "Soul",
    "neo-soul": "Soul",
    "neo soul": "Soul",
    "motown": "Soul",
    "northern soul": "Soul",
    # --- Hip-Hop / Rap ---
    "hip-hop": "Hip-Hop",
    "hip hop": "Hip-Hop",
    "hiphop": "Hip-Hop",
    "rap": "Hip-Hop",
    "hip hop/rap": "Hip-Hop",
    "old school hip hop": "Hip-Hop",
    "boom bap": "Hip-Hop",
    "conscious hip hop": "Hip-Hop",
    "gangsta rap": "Hip-Hop",
    "underground hip hop": "Hip-Hop",
    # --- R&B ---
    "r&b": "R&B",
    "rnb": "R&B",
    "rhythm and blues": "R&B",
    "contemporary r&b": "R&B",
    # --- Pop ---
    "pop": "Pop",
    "synth-pop": "Synth-Pop",
    "synthpop": "Synth-Pop",
    "synth pop": "Synth-Pop",
    "indie pop": "Indie Pop",
    "electropop": "Pop",
    "dance-pop": "Pop",
    "dance pop": "Pop",
    "k-pop": "K-Pop",
    "j-pop": "J-Pop",
    # --- Rock ---
    "rock": "Rock",
    "indie": "Indie",
    "indie rock": "Indie",
    "alternative": "Alternative",
    "alternative rock": "Alternative",
    "alt-rock": "Alternative",
    "post-punk": "Post-Punk",
    "post punk": "Post-Punk",
    "new wave": "New Wave",
    "punk": "Punk",
    "punk rock": "Punk",
    "hard rock": "Rock",
    "classic rock": "Rock",
    "psychedelic rock": "Psychedelic",
    "psychedelic": "Psychedelic",
    "grunge": "Grunge",
    "shoegaze": "Shoegaze",
    "dream pop": "Dream Pop",
    "emo": "Emo",
    # --- Metal ---
    "metal": "Metal",
    "heavy metal": "Metal",
    "death metal": "Metal",
    "black metal": "Metal",
    "thrash metal": "Metal",
    "doom metal": "Metal",
    "progressive metal": "Metal",
    "metalcore": "Metal",
    "nu metal": "Metal",
    "nu-metal": "Metal",
    # --- Ambient / Downtempo ---
    "ambient": "Ambient",
    "dark ambient": "Ambient",
    "downtempo": "Downtempo",
    "chillout": "Chillout",
    "chill out": "Chillout",
    "chill-out": "Chillout",
    "lounge": "Chillout",
    "trip-hop": "Trip-Hop",
    "trip hop": "Trip-Hop",
    "chillwave": "Chillwave",
    "new age": "New Age",
    # --- Latin ---
    "latin": "Latin",
    "reggaeton": "Reggaeton",
    "reggaetón": "Reggaeton",
    "dancehall": "Dancehall",
    "reggae": "Reggae",
    "dub": "Dub",
    "ska": "Ska",
    "salsa": "Latin",
    "bachata": "Latin",
    "cumbia": "Latin",
    "bossa nova": "Bossa Nova",
    "samba": "Latin",
    "afrobeats": "Afrobeats",
    "afrobeat": "Afrobeats",
    # --- Jazz ---
    "jazz": "Jazz",
    "acid jazz": "Jazz",
    "jazz fusion": "Jazz",
    "smooth jazz": "Jazz",
    "nu jazz": "Jazz",
    # --- Blues ---
    "blues": "Blues",
    "blues rock": "Blues",
    "delta blues": "Blues",
    # --- Country / Folk ---
    "country": "Country",
    "folk": "Folk",
    "bluegrass": "Country",
    "americana": "Country",
    "singer-songwriter": "Singer-Songwriter",
    "singer songwriter": "Singer-Songwriter",
    # --- Classical ---
    "classical": "Classical",
    "classical music": "Classical",
    "orchestral": "Classical",
    "opera": "Classical",
    "soundtrack": "Soundtrack",
    "film score": "Soundtrack",
    "score": "Soundtrack",
    # --- World / Experimental ---
    "world": "World",
    "world music": "World",
    "experimental": "Experimental",
    "avant-garde": "Experimental",
    "noise": "Experimental",
    # --- Gospel / Spiritual ---
    "gospel": "Gospel",
    "christian": "Gospel",
    "worship": "Gospel",
}


# ---------------------------------------------------------------------------
# Genre mapper
# ---------------------------------------------------------------------------


class TagToGenreMapper:
    """Maps freeform tags/genres to canonical DJ genre names via weighted scoring."""

    def map_tags(self, tags: list[tuple[str, int]]) -> str | None:
        """Map Last.fm tags (name, count) to a genre using weighted scoring.

        Args:
            tags: List of (tag_name, count) tuples from Last.fm.

        Returns:
            Canonical genre string or None if no match.
        """
        if not tags:
            return None

        scores: dict[str, float] = {}
        for tag_name, count in tags:
            genre = TAG_TO_GENRE.get(tag_name.lower().strip())
            if genre:
                scores[genre] = scores.get(genre, 0.0) + count

        if not scores:
            return None
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def map_genres(self, genres: list[str]) -> str | None:
        """Map MusicBrainz genres to a canonical genre using unweighted scoring.

        Args:
            genres: List of genre strings.

        Returns:
            Canonical genre string or None if no match.
        """
        if not genres:
            return None

        scores: dict[str, int] = {}
        for genre in genres:
            canonical = TAG_TO_GENRE.get(genre.lower().strip())
            if canonical:
                scores[canonical] = scores.get(canonical, 0) + 1

        if not scores:
            return None
        return max(scores, key=scores.get)  # type: ignore[arg-type]


def normalize_genre(raw_genre: str) -> str:
    """Normalize a freeform genre string to a canonical DJ genre name.

    Tries exact match (case-insensitive) in TAG_TO_GENRE. Falls back to
    title-casing the input if no mapping found.

    Args:
        raw_genre: Raw genre string from file tags or online lookup.

    Returns:
        Canonical genre name, or title-cased input as fallback.
    """
    if not raw_genre or not raw_genre.strip():
        return ""
    cleaned = raw_genre.strip()
    # Exact match
    canonical = TAG_TO_GENRE.get(cleaned.lower())
    if canonical:
        return canonical
    # No match — return title-cased as-is
    return cleaned.title()


# ---------------------------------------------------------------------------
# Last.fm genre lookup
# ---------------------------------------------------------------------------


class LastFmGenreLookup:
    """Look up genre from Last.fm track tags."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._mapper = TagToGenreMapper()

    def get_genre(self, artist: str, title: str) -> str | None:
        """Get genre for a track from Last.fm top tags.

        Args:
            artist: Artist name.
            title: Track title.

        Returns:
            Canonical genre string or None.
        """
        try:
            import pylast
        except ImportError:
            return None

        def _do_lookup():
            _lastfm_limiter.wait()
            network = pylast.LastFMNetwork(api_key=self._api_key)
            track = network.get_track(artist, title)
            top_tags = track.get_top_tags(limit=15)
            tags = [(t.item.get_name(), int(t.weight)) for t in top_tags]
            return self._mapper.map_tags(tags)

        try:
            return _retry_on_network_error(
                _do_lookup,
                extra_exceptions=(pylast.NetworkError,),
            )
        except (pylast.WSError, pylast.MalformedResponseError):
            return None
        except Exception:
            logger.warning("Last.fm genre lookup failed for %s - %s", artist, title, exc_info=True)
            return None

    def get_genre_from_artist(self, artist: str) -> str | None:
        """Get genre from artist's top tags (fallback).

        Args:
            artist: Artist name.

        Returns:
            Canonical genre string or None.
        """
        try:
            import pylast
        except ImportError:
            return None

        def _do_lookup():
            _lastfm_limiter.wait()
            network = pylast.LastFMNetwork(api_key=self._api_key)
            artist_obj = network.get_artist(artist)
            top_tags = artist_obj.get_top_tags(limit=15)
            tags = [(t.item.get_name(), int(t.weight)) for t in top_tags]
            return self._mapper.map_tags(tags)

        try:
            return _retry_on_network_error(
                _do_lookup,
                extra_exceptions=(pylast.NetworkError,),
            )
        except (pylast.WSError, pylast.MalformedResponseError):
            return None
        except Exception:
            logger.warning("Last.fm artist genre lookup failed for %s", artist, exc_info=True)
            return None


# ---------------------------------------------------------------------------
# MusicBrainz genre lookup
# ---------------------------------------------------------------------------


class MusicBrainzGenreLookup:
    """Look up genre from MusicBrainz genres."""

    def __init__(self) -> None:
        self._mapper = TagToGenreMapper()

    def get_genre(self, artist: str, title: str) -> str | None:
        """Get genre for a track from MusicBrainz genres.

        Args:
            artist: Artist name.
            title: Track title.

        Returns:
            Canonical genre string or None.
        """
        try:
            import musicbrainzngs
        except ImportError:
            return None

        def _do_lookup():
            _musicbrainz_limiter.wait()
            musicbrainzngs.set_useragent("VDJ-Manager", "0.1.0", "")
            result = musicbrainzngs.search_recordings(artist=artist, recording=title, limit=1)
            recordings = result.get("recording-list", [])
            if not recordings:
                return None

            recording = recordings[0]
            genres: list[str] = []
            for tag in recording.get("tag-list", []):
                name = tag.get("name", "")
                if name:
                    genres.append(name)
            return self._mapper.map_genres(genres)

        try:
            return _retry_on_network_error(
                _do_lookup,
                extra_exceptions=(musicbrainzngs.NetworkError,),
            )
        except Exception:
            logger.warning(
                "MusicBrainz genre lookup failed for %s - %s", artist, title, exc_info=True
            )
            return None


# ---------------------------------------------------------------------------
# Top-level picklable lookup function
# ---------------------------------------------------------------------------


@lru_cache(maxsize=2048)
def _cached_genre_lookup(
    artist: str, title: str, lastfm_api_key: str | None
) -> tuple[str | None, str]:
    """Cached online genre lookup (deduplicates identical artist+title pairs).

    Returns:
        (genre, source) where source is "lastfm", "lastfm-artist",
        "musicbrainz", or "none".
    """
    clean_a = _clean_artist(artist)
    clean_t = _clean_title(title)

    # Try Last.fm track tags
    if lastfm_api_key:
        lfm = LastFmGenreLookup(lastfm_api_key)
        genre = lfm.get_genre(clean_a, clean_t)
        if genre:
            return genre, "lastfm"

        # Fall back to Last.fm artist tags
        genre = lfm.get_genre_from_artist(clean_a)
        if genre:
            return genre, "lastfm-artist"

    # Fall back to MusicBrainz
    mb = MusicBrainzGenreLookup()
    genre = mb.get_genre(clean_a, clean_t)
    if genre:
        return genre, "musicbrainz"

    return None, "none"


def lookup_online_genre(
    artist: str,
    title: str,
    lastfm_api_key: str | None = None,
) -> tuple[str | None, str]:
    """Look up genre from online databases.

    Cleans artist/title metadata, then tries Last.fm track tags,
    Last.fm artist tags, and MusicBrainz in order. Uses LRU cache
    internally to deduplicate identical artist+title pairs.

    Args:
        artist: Artist name (may contain feat., commas, etc.).
        title: Track title (may contain remix info, parentheticals, etc.).
        lastfm_api_key: Optional Last.fm API key.

    Returns:
        (genre, source) tuple. source is "lastfm", "lastfm-artist",
        "musicbrainz", or "none".
    """
    if not artist or not title:
        return None, "none"
    return _cached_genre_lookup(artist, title, lastfm_api_key)
