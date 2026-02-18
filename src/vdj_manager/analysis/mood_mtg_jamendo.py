"""MTG-Jamendo MoodTheme mood classification backend.

Uses Essentia's TensorflowPredictEffnetDiscogs for embeddings
and TensorflowPredict2D for 56-class mood/theme classification.

Pipeline: MonoLoader(16kHz) -> EffnetDiscogs embeddings -> MoodTheme 2D classifier
-> average across frames -> 56 confidence scores.
"""

from __future__ import annotations

import logging

from .mood_backend import select_top_moods

logger = logging.getLogger(__name__)

# Official MTG-Jamendo MoodTheme class order from the model metadata.
# These must match the model output ordering exactly.
CLASS_NAMES_RAW = [
    "mood/theme---action",
    "mood/theme---adventure",
    "mood/theme---advertising",
    "mood/theme---background",
    "mood/theme---ballad",
    "mood/theme---calm",
    "mood/theme---children",
    "mood/theme---christmas",
    "mood/theme---commercial",
    "mood/theme---cool",
    "mood/theme---corporate",
    "mood/theme---dark",
    "mood/theme---deep",
    "mood/theme---documentary",
    "mood/theme---drama",
    "mood/theme---dramatic",
    "mood/theme---dream",
    "mood/theme---emotional",
    "mood/theme---energetic",
    "mood/theme---epic",
    "mood/theme---fast",
    "mood/theme---film",
    "mood/theme---fun",
    "mood/theme---funny",
    "mood/theme---game",
    "mood/theme---groovy",
    "mood/theme---happy",
    "mood/theme---heavy",
    "mood/theme---holiday",
    "mood/theme---hopeful",
    "mood/theme---inspiring",
    "mood/theme---love",
    "mood/theme---meditative",
    "mood/theme---melancholic",
    "mood/theme---melodic",
    "mood/theme---motivational",
    "mood/theme---movie",
    "mood/theme---nature",
    "mood/theme---party",
    "mood/theme---positive",
    "mood/theme---powerful",
    "mood/theme---relaxing",
    "mood/theme---retro",
    "mood/theme---romantic",
    "mood/theme---sad",
    "mood/theme---sexy",
    "mood/theme---slow",
    "mood/theme---soft",
    "mood/theme---soundscape",
    "mood/theme---space",
    "mood/theme---sport",
    "mood/theme---summer",
    "mood/theme---trailer",
    "mood/theme---travel",
    "mood/theme---upbeat",
    "mood/theme---uplifting",
]

CLASS_NAMES = [c.replace("mood/theme---", "") for c in CLASS_NAMES_RAW]


class MTGJamendoBackend:
    """MTG-Jamendo MoodTheme 56-class mood analysis backend.

    Requires essentia-tensorflow and model files (~87MB total).
    Model files are auto-downloaded on first use.
    """

    def __init__(self) -> None:
        self._es = None
        self._essentia_available = False
        try:
            import essentia.standard as es

            self._es = es
            self._essentia_available = True
        except ImportError:
            pass

    @property
    def name(self) -> str:
        return "mtg-jamendo"

    @property
    def is_available(self) -> bool:
        return self._essentia_available

    def analyze(self, file_path: str) -> dict[str, float] | None:
        """Analyze mood of an audio file using the MTG-Jamendo model.

        Returns:
            Dict mapping all 56 mood class names to confidence scores
            (0.0-1.0), or None if analysis fails.
        """
        if not self._essentia_available:
            return None

        try:
            from .model_downloader import ensure_model_files

            embedding_path, classifier_path = ensure_model_files()

            audio = self._es.MonoLoader(filename=file_path, sampleRate=16000)()  # type: ignore[union-attr]

            embeddings = self._es.TensorflowPredictEffnetDiscogs(  # type: ignore[union-attr]
                graphFilename=str(embedding_path),
                output="PartitionedCall:1",
            )(audio)

            predictions = self._es.TensorflowPredict2D(  # type: ignore[union-attr]
                graphFilename=str(classifier_path),
                output="model/Sigmoid:0",
            )(embeddings)

            # Average predictions across all frames
            avg = predictions.mean(axis=0)

            return dict(zip(CLASS_NAMES, avg.tolist()))
        except Exception:
            logger.exception("MTG-Jamendo analysis failed for %s", file_path)
            return None

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
