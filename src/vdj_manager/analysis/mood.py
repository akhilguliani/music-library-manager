"""Heuristic mood classification using Essentia audio features.

This is a lightweight backend that uses BPM, RMS, and spectral centroid
to estimate mood via simple heuristics. For better accuracy, use the
MTG-Jamendo backend which employs a pre-trained deep learning model.

Implements the MoodBackend protocol from mood_backend.py.
"""

import logging

logger = logging.getLogger(__name__)

from .mood_backend import select_top_moods


class MoodAnalyzer:
    """Analyze audio files for mood using heuristic features.

    Requires: pip install essentia-tensorflow

    Implements the MoodBackend protocol.
    """

    def __init__(self) -> None:
        self._essentia_available = False
        self._es = None

        try:
            import essentia.standard as es

            self._essentia_available = True
            self._es = es
        except ImportError:
            pass

    @property
    def name(self) -> str:
        """Backend identifier for cache keys."""
        return "heuristic"

    @property
    def is_available(self) -> bool:
        """Check if Essentia is available."""
        return self._essentia_available

    def analyze(self, file_path: str) -> dict[str, float] | None:
        """Analyze mood of an audio file.

        Returns:
            Dict mapping mood names to confidence scores (0.0-1.0),
            or None if unavailable. Keys are a subset of heuristic
            mood categories: energetic, calm, bright, dark.
        """
        if not self._essentia_available:
            return None

        try:
            audio = self._es.MonoLoader(filename=file_path, sampleRate=16000)()
            return self._compute_heuristic_scores(audio)
        except Exception:
            logger.warning("Mood analysis failed for %s", file_path, exc_info=True)
            return None

    def _compute_heuristic_scores(self, audio) -> dict[str, float]:
        """Compute mood scores from audio features.

        Returns dict mapping mood name -> confidence (0.0-1.0).
        On error, returns {"unknown": 0.0} so callers get a valid dict.
        """
        try:
            rhythm_extractor = self._es.RhythmExtractor2013(method="multifeature")
            bpm, beats, beats_confidence, _, _ = rhythm_extractor(audio)

            spectrum = self._es.Spectrum()(audio)
            centroid = self._es.Centroid(range=22050 / 2)(spectrum)

            rms = self._es.RMS()(audio)

            return {
                "energetic": min(1.0, bpm / 140) * 0.5 + min(1.0, rms * 10) * 0.5,
                "calm": max(0.0, 1.0 - bpm / 140) * 0.5 + max(0.0, 1.0 - rms * 10) * 0.5,
                "bright": min(1.0, centroid / 3000),
                "dark": max(0.0, 1.0 - centroid / 3000),
            }
        except Exception:
            logger.warning("Heuristic score computation failed", exc_info=True)
            return {"unknown": 0.0}

    def get_mood_tags(
        self,
        file_path: str,
        threshold: float = 0.1,
        max_tags: int = 5,
    ) -> list[str] | None:
        """Get mood tags using multi-label selection.

        Returns:
            List of mood tag strings sorted by confidence, or None.
        """
        scores = self.analyze(file_path)
        if scores is None:
            return None
        return select_top_moods(scores, threshold, max_tags)

    def get_mood_tag(self, file_path: str) -> str | None:
        """Get the single top mood tag for a file.

        Backward-compatible convenience method.

        Returns:
            Top mood tag string, or None.
        """
        scores = self.analyze(file_path)
        if scores is None:
            return None
        if not scores:
            return "unknown"
        return max(scores, key=scores.get)  # type: ignore[arg-type]
