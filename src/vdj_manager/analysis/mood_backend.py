"""Mood model backend protocol and registry.

Defines the MoodBackend protocol that all mood analysis backends must
implement, a MoodModel enum for selecting backends, and shared utilities
for multi-label mood tag selection.
"""

from __future__ import annotations

import enum
from typing import Protocol, runtime_checkable

# All 56 MTG-Jamendo mood/theme classes (cleaned of "mood/theme---" prefix).
# This is the full vocabulary of mood tags used across the application.
MOOD_CLASSES = [
    "action",
    "adventure",
    "advertising",
    "background",
    "ballad",
    "calm",
    "children",
    "christmas",
    "commercial",
    "cool",
    "corporate",
    "dark",
    "deep",
    "documentary",
    "drama",
    "dramatic",
    "dream",
    "emotional",
    "energetic",
    "epic",
    "fast",
    "film",
    "fun",
    "funny",
    "game",
    "groovy",
    "happy",
    "heavy",
    "holiday",
    "hopeful",
    "inspiring",
    "love",
    "meditative",
    "melancholic",
    "melodic",
    "motivational",
    "movie",
    "nature",
    "party",
    "positive",
    "powerful",
    "relaxing",
    "retro",
    "romantic",
    "sad",
    "sexy",
    "slow",
    "soft",
    "soundscape",
    "space",
    "sport",
    "summer",
    "trailer",
    "travel",
    "upbeat",
    "uplifting",
]

MOOD_CLASSES_SET = frozenset(MOOD_CLASSES)


class MoodModel(str, enum.Enum):
    """Available mood analysis models."""

    MTG_JAMENDO = "mtg-jamendo"
    HEURISTIC = "heuristic"
    # Future: MUSIC2EMO = "music2emo"


@runtime_checkable
class MoodBackend(Protocol):
    """Protocol for mood analysis backends.

    Each backend analyzes an audio file and returns confidence scores
    for the mood classes it supports.
    """

    @property
    def name(self) -> str:
        """Short identifier used in cache keys (e.g. 'mtg-jamendo')."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this backend's dependencies are installed."""
        ...

    def analyze(self, file_path: str) -> dict[str, float] | None:
        """Analyze mood of an audio file.

        Returns:
            Dict mapping mood class names to confidence scores (0.0-1.0),
            or None if analysis fails. The number of keys depends on the
            backend (e.g. 56 for MTG-Jamendo, 4 for heuristic).
        """
        ...

    def get_mood_tags(
        self,
        file_path: str,
        threshold: float = 0.1,
        max_tags: int = 5,
    ) -> list[str] | None:
        """Get mood tags for a file using multi-label selection.

        Returns:
            Sorted list of mood tag strings above threshold, or None
            if analysis fails.
        """
        ...


def cache_key_for_model(model: MoodModel) -> str:
    """Return the analysis_type cache key for a given model.

    E.g., 'mood:mtg-jamendo' or 'mood:heuristic'.
    """
    return f"mood:{model.value}"


def select_top_moods(
    scores: dict[str, float],
    threshold: float = 0.1,
    max_tags: int = 5,
) -> list[str]:
    """Select moods above threshold with multi-label logic.

    - Include all moods with confidence >= threshold, up to max_tags.
    - Always include at least the top 1 mood (even if below threshold).
    - Results sorted by confidence, highest first.

    Args:
        scores: Dict mapping mood names to confidence scores.
        threshold: Minimum confidence to include (0.0-1.0).
        max_tags: Maximum number of tags to return.

    Returns:
        List of mood name strings, sorted by confidence descending.
    """
    if not scores:
        return []
    sorted_moods = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result = [m for m, s in sorted_moods if s >= threshold][:max_tags]
    if not result:
        result = [sorted_moods[0][0]]
    return result


def get_backend(model: MoodModel) -> MoodBackend:
    """Factory: instantiate the appropriate backend.

    Uses lazy imports to avoid loading heavy dependencies at startup.

    Args:
        model: The model to instantiate.

    Returns:
        A MoodBackend instance.

    Raises:
        ValueError: If the model is not recognized.
    """
    if model == MoodModel.MTG_JAMENDO:
        from .mood_mtg_jamendo import MTGJamendoBackend

        return MTGJamendoBackend()
    elif model == MoodModel.HEURISTIC:
        from .mood import MoodAnalyzer

        return MoodAnalyzer()
    else:
        raise ValueError(f"Unknown mood model: {model}")
