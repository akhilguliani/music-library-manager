"""Energy level classification (1-10 scale)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..config import ENERGY_WEIGHTS

if TYPE_CHECKING:
    from .audio_features import AudioFeatureExtractor

logger = logging.getLogger(__name__)


class EnergyAnalyzer:
    """Analyze audio files and classify energy levels on a 1-10 scale."""

    # Reference values for normalization (typical ranges)
    TEMPO_RANGE = (60, 180)  # BPM
    RMS_RANGE = (0.01, 0.3)  # RMS energy
    SPECTRAL_RANGE = (1000, 5000)  # Spectral centroid in Hz

    def __init__(self, weights: dict | None = None):
        """Initialize energy analyzer.

        Args:
            weights: Optional custom weights for tempo, rms, spectral
        """
        self.weights = weights or ENERGY_WEIGHTS

        # Lazy import to avoid slow startup
        self._extractor: AudioFeatureExtractor | None = None

    @property
    def extractor(self):
        """Get or create audio feature extractor."""
        if self._extractor is None:
            from .audio_features import AudioFeatureExtractor

            self._extractor = AudioFeatureExtractor()
        return self._extractor

    def analyze(self, file_path: str) -> int | None:
        """Analyze a file and return energy level (1-10).

        Args:
            file_path: Path to audio file

        Returns:
            Energy level 1-10, or None on error
        """
        try:
            features = self.extractor.extract_features(file_path)
            return self.calculate_energy(features)
        except Exception:
            logger.warning("Energy analysis failed for %s", file_path, exc_info=True)
            return None

    def calculate_energy(self, features: dict) -> int:
        """Calculate energy level from extracted features.

        Args:
            features: Dict with tempo, rms_energy, spectral_centroid

        Returns:
            Energy level 1-10
        """
        # Normalize each feature to 0-1 range
        tempo_norm = self._normalize(
            features.get("tempo", 120),
            self.TEMPO_RANGE[0],
            self.TEMPO_RANGE[1],
        )

        rms_norm = self._normalize(
            features.get("rms_energy", 0.1),
            self.RMS_RANGE[0],
            self.RMS_RANGE[1],
        )

        spectral_norm = self._normalize(
            features.get("spectral_centroid", 2000),
            self.SPECTRAL_RANGE[0],
            self.SPECTRAL_RANGE[1],
        )

        # Weighted combination
        weighted_score = (
            self.weights["tempo"] * tempo_norm
            + self.weights["rms"] * rms_norm
            + self.weights["spectral"] * spectral_norm
        )

        # Map to 1-10 scale
        energy = int(round(weighted_score * 9 + 1))
        return max(1, min(10, energy))

    @staticmethod
    def _normalize(value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-1 range."""
        if max_val == min_val:
            return 0.5
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))

    def analyze_batch(self, file_paths: list[str]) -> dict[str, int | None]:
        """Analyze multiple files.

        Args:
            file_paths: List of file paths

        Returns:
            Dict mapping file paths to energy levels
        """
        results = {}
        for path in file_paths:
            results[path] = self.analyze(path)
        return results

    def compare_with_existing(
        self,
        file_path: str,
        existing_energy: int,
    ) -> dict:
        """Compare calculated energy with existing tag.

        Args:
            file_path: Path to audio file
            existing_energy: Current energy tag value

        Returns:
            Dict with comparison results
        """
        calculated = self.analyze(file_path)

        return {
            "file_path": file_path,
            "existing": existing_energy,
            "calculated": calculated,
            "difference": abs(calculated - existing_energy) if calculated else None,
            "match": calculated == existing_energy if calculated else None,
        }
