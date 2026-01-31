"""Audio normalization processor using ffmpeg."""

import subprocess
import shutil
from pathlib import Path
from typing import Optional

from .loudness import LoudnessMeasurer
from ..config import DEFAULT_LUFS_TARGET


class NormalizationProcessor:
    """Process audio files for loudness normalization."""

    def __init__(
        self,
        target_lufs: float = DEFAULT_LUFS_TARGET,
        ffmpeg_path: str = "ffmpeg",
    ):
        """Initialize normalization processor.

        Args:
            target_lufs: Target loudness in LUFS (default -14)
            ffmpeg_path: Path to ffmpeg binary
        """
        self.target_lufs = target_lufs
        self.ffmpeg_path = ffmpeg_path
        self.measurer = LoudnessMeasurer(ffmpeg_path)

    def calculate_gain(self, file_path: str) -> Optional[float]:
        """Calculate gain adjustment needed to reach target loudness.

        Args:
            file_path: Path to audio file

        Returns:
            Gain in dB to apply (positive = louder, negative = quieter)
        """
        current_lufs = self.measurer.measure(file_path)
        if current_lufs is None:
            return None

        # Calculate gain needed
        gain = self.target_lufs - current_lufs
        return round(gain, 2)

    def normalize_file(
        self,
        file_path: str,
        output_path: Optional[str] = None,
        backup: bool = True,
    ) -> bool:
        """Normalize a file to target loudness (destructive).

        Args:
            file_path: Path to audio file
            output_path: Optional output path (default: overwrite original)
            backup: Whether to create backup before overwriting

        Returns:
            True if successful
        """
        input_path = Path(file_path)
        if not input_path.exists():
            return False

        # Create temp output file
        temp_output = input_path.with_suffix(f".normalized{input_path.suffix}")

        try:
            # Two-pass loudnorm for accurate normalization
            # First pass: measure
            measurements = self.measurer.measure_detailed(file_path)
            if not measurements:
                return False

            # Second pass: apply normalization
            result = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-i", str(input_path),
                    "-af", f"loudnorm=I={self.target_lufs}:TP=-1.0:LRA=11:"
                           f"measured_I={measurements['integrated']}:"
                           f"measured_TP={measurements['true_peak']}:"
                           f"measured_LRA={measurements['lra']}:"
                           f"measured_thresh={measurements['threshold']}:"
                           f"linear=true:print_format=summary",
                    "-y",  # Overwrite output
                    str(temp_output),
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes max
            )

            if result.returncode != 0:
                if temp_output.exists():
                    temp_output.unlink()
                return False

            # Handle output
            if output_path:
                shutil.move(str(temp_output), output_path)
            else:
                # Overwrite original
                if backup:
                    backup_path = input_path.with_suffix(f".backup{input_path.suffix}")
                    shutil.copy2(str(input_path), str(backup_path))

                shutil.move(str(temp_output), str(input_path))

            return True

        except subprocess.TimeoutExpired:
            if temp_output.exists():
                temp_output.unlink()
            return False
        except Exception:
            if temp_output.exists():
                temp_output.unlink()
            return False

    def calculate_vdj_volume(self, file_path: str) -> Optional[float]:
        """Calculate VDJ Volume field value for non-destructive normalization.

        VDJ Volume is a multiplier where 1.0 = no change.
        Values > 1.0 increase volume, < 1.0 decrease volume.

        Args:
            file_path: Path to audio file

        Returns:
            VDJ Volume value, or None on error
        """
        gain_db = self.calculate_gain(file_path)
        if gain_db is None:
            return None

        # Convert dB to linear gain
        # dB = 20 * log10(gain) => gain = 10^(dB/20)
        import math
        linear_gain = 10 ** (gain_db / 20)

        return round(linear_gain, 4)

    def process_batch(
        self,
        file_paths: list[str],
        destructive: bool = False,
        callback=None,
    ) -> dict:
        """Process multiple files.

        Args:
            file_paths: List of file paths
            destructive: Whether to modify files
            callback: Optional callback(file_path, success) for progress

        Returns:
            Dict with processing results
        """
        results = {
            "processed": 0,
            "failed": 0,
            "skipped": 0,
            "gains": {},
        }

        for path in file_paths:
            try:
                if destructive:
                    success = self.normalize_file(path)
                    if success:
                        results["processed"] += 1
                    else:
                        results["failed"] += 1
                else:
                    gain = self.calculate_gain(path)
                    if gain is not None:
                        results["gains"][path] = gain
                        results["processed"] += 1
                    else:
                        results["failed"] += 1

                if callback:
                    callback(path, True)

            except Exception:
                results["failed"] += 1
                if callback:
                    callback(path, False)

        return results

    def analyze_library(self, file_paths: list[str]) -> dict:
        """Analyze loudness distribution of a library.

        Args:
            file_paths: List of file paths

        Returns:
            Dict with statistics
        """
        lufs_values = []
        gains_needed = []

        for path in file_paths:
            lufs = self.measurer.measure(path)
            if lufs is not None:
                lufs_values.append(lufs)
                gains_needed.append(self.target_lufs - lufs)

        if not lufs_values:
            return {"error": "No files could be measured"}

        import statistics

        return {
            "count": len(lufs_values),
            "target": self.target_lufs,
            "current": {
                "mean": round(statistics.mean(lufs_values), 1),
                "median": round(statistics.median(lufs_values), 1),
                "min": round(min(lufs_values), 1),
                "max": round(max(lufs_values), 1),
                "stdev": round(statistics.stdev(lufs_values), 1) if len(lufs_values) > 1 else 0,
            },
            "gains": {
                "mean": round(statistics.mean(gains_needed), 1),
                "min": round(min(gains_needed), 1),
                "max": round(max(gains_needed), 1),
            },
            "needs_adjustment": sum(1 for g in gains_needed if abs(g) > 1.0),
        }
