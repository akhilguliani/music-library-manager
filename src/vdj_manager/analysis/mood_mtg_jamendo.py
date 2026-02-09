"""MTG-Jamendo MoodTheme mood classification backend.

Uses Essentia's TensorflowPredictEffnetDiscogs for embeddings
and TensorflowPredict2D for 56-class mood/theme classification.
Full implementation added in a subsequent commit.
"""

from __future__ import annotations

from .mood_backend import select_top_moods


class MTGJamendoBackend:
    """MTG-Jamendo MoodTheme 56-class mood analysis backend.

    Requires essentia-tensorflow and model files to be available.
    """

    @property
    def name(self) -> str:
        return "mtg-jamendo"

    @property
    def is_available(self) -> bool:
        try:
            import essentia  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze(self, file_path: str) -> dict[str, float] | None:
        """Analyze mood — stub, full implementation in later commit."""
        return None

    def get_mood_tags(
        self,
        file_path: str,
        threshold: float = 0.1,
        max_tags: int = 5,
    ) -> list[str] | None:
        scores = self.analyze(file_path)
        if scores is None:
            return None
        return select_top_moods(scores, threshold, max_tags)
