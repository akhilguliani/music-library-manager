"""Audio normalization processor using ffmpeg with parallel processing."""

import subprocess
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable
import multiprocessing
import os

from .loudness import LoudnessMeasurer
from ..config import DEFAULT_LUFS_TARGET


@dataclass
class NormalizationResult:
    """Result of a normalization operation."""
    file_path: str
    success: bool
    current_lufs: Optional[float] = None
    gain_db: Optional[float] = None
    error: Optional[str] = None


def _measure_single_file(args: tuple) -> NormalizationResult:
    """Worker function for parallel measurement.

    Args:
        args: Tuple of (file_path, target_lufs, ffmpeg_path)
              or (file_path, target_lufs, ffmpeg_path, cache_db_path)

    Returns:
        NormalizationResult with measurement data
    """
    if len(args) == 4:
        file_path, target_lufs, ffmpeg_path, cache_db_path = args
    else:
        file_path, target_lufs, ffmpeg_path = args
        cache_db_path = None

    try:
        # Check cache first
        if cache_db_path:
            from .measurement_cache import MeasurementCache

            cache = MeasurementCache(db_path=Path(cache_db_path))
            cached = cache.get(file_path, target_lufs)
            if cached is not None:
                return NormalizationResult(
                    file_path=file_path,
                    success=True,
                    current_lufs=cached["integrated_lufs"],
                    gain_db=cached["gain_db"],
                )

        measurer = LoudnessMeasurer(ffmpeg_path)
        lufs = measurer.measure(file_path)

        if lufs is None:
            return NormalizationResult(
                file_path=file_path,
                success=False,
                error="Could not measure loudness"
            )

        gain = target_lufs - lufs

        # Write to cache
        if cache_db_path:
            from .measurement_cache import MeasurementCache

            cache = MeasurementCache(db_path=Path(cache_db_path))
            cache.put(file_path, target_lufs, {
                "integrated_lufs": lufs,
                "gain_db": round(gain, 2),
            })

        return NormalizationResult(
            file_path=file_path,
            success=True,
            current_lufs=lufs,
            gain_db=round(gain, 2)
        )
    except Exception as e:
        return NormalizationResult(
            file_path=file_path,
            success=False,
            error=str(e)
        )


def _normalize_single_file(args: tuple) -> NormalizationResult:
    """Worker function for parallel normalization.

    Args:
        args: Tuple of (file_path, target_lufs, ffmpeg_path, backup)
              or (file_path, target_lufs, ffmpeg_path, backup, cache_db_path)

    Returns:
        NormalizationResult
    """
    if len(args) == 5:
        file_path, target_lufs, ffmpeg_path, backup, cache_db_path = args
    else:
        file_path, target_lufs, ffmpeg_path, backup = args
        cache_db_path = None

    try:
        input_path = Path(file_path)
        if not input_path.exists():
            return NormalizationResult(
                file_path=file_path,
                success=False,
                error="File not found"
            )

        measurer = LoudnessMeasurer(ffmpeg_path)

        # First pass: measure (check cache for detailed metrics)
        measurements = None
        if cache_db_path:
            from .measurement_cache import MeasurementCache

            cache = MeasurementCache(db_path=Path(cache_db_path))
            cached = cache.get(file_path, target_lufs)
            if cached is not None and cached.get("true_peak") is not None:
                measurements = {
                    "integrated": cached["integrated_lufs"],
                    "true_peak": cached["true_peak"],
                    "lra": cached["lra"],
                    "threshold": cached["threshold"],
                }

        if measurements is None:
            measurements = measurer.measure_detailed(file_path)
        if not measurements:
            return NormalizationResult(
                file_path=file_path,
                success=False,
                error="Could not measure loudness"
            )

        current_lufs = measurements['integrated']
        gain = target_lufs - current_lufs

        # Create temp output file
        temp_output = input_path.with_suffix(f".normalized{input_path.suffix}")

        # Second pass: apply normalization
        result = subprocess.run(
            [
                ffmpeg_path,
                "-i", str(input_path),
                "-af", f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11:"
                       f"measured_I={measurements['integrated']}:"
                       f"measured_TP={measurements['true_peak']}:"
                       f"measured_LRA={measurements['lra']}:"
                       f"measured_thresh={measurements['threshold']}:"
                       f"linear=true:print_format=summary",
                "-y",
                str(temp_output),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            if temp_output.exists():
                temp_output.unlink()
            return NormalizationResult(
                file_path=file_path,
                success=False,
                current_lufs=current_lufs,
                gain_db=gain,
                error=f"ffmpeg error: {result.stderr[:200]}"
            )

        # Backup and replace original
        if backup:
            backup_path = input_path.with_suffix(f".backup{input_path.suffix}")
            shutil.copy2(str(input_path), str(backup_path))

        shutil.move(str(temp_output), str(input_path))

        return NormalizationResult(
            file_path=file_path,
            success=True,
            current_lufs=current_lufs,
            gain_db=gain
        )

    except subprocess.TimeoutExpired:
        return NormalizationResult(
            file_path=file_path,
            success=False,
            error="Timeout"
        )
    except Exception as e:
        return NormalizationResult(
            file_path=file_path,
            success=False,
            error=str(e)
        )


class NormalizationProcessor:
    """Process audio files for loudness normalization with parallel support."""

    def __init__(
        self,
        target_lufs: float = DEFAULT_LUFS_TARGET,
        ffmpeg_path: str = "ffmpeg",
        max_workers: Optional[int] = None,
    ):
        """Initialize normalization processor.

        Args:
            target_lufs: Target loudness in LUFS (default -14)
            ffmpeg_path: Path to ffmpeg binary
            max_workers: Max parallel workers (default: CPU count)
        """
        self.target_lufs = target_lufs
        self.ffmpeg_path = ffmpeg_path
        self.max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
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
        return round(self.target_lufs - current_lufs, 2)

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
        result = _normalize_single_file(
            (file_path, self.target_lufs, self.ffmpeg_path, backup)
        )
        return result.success

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

        import math
        linear_gain = 10 ** (gain_db / 20)
        return round(linear_gain, 4)

    def measure_batch_parallel(
        self,
        file_paths: list[str],
        callback: Optional[Callable[[NormalizationResult], None]] = None,
    ) -> list[NormalizationResult]:
        """Measure loudness for multiple files in parallel.

        Args:
            file_paths: List of file paths
            callback: Optional callback for progress updates

        Returns:
            List of NormalizationResult objects
        """
        results = []
        args_list = [
            (fp, self.target_lufs, self.ffmpeg_path)
            for fp in file_paths
        ]

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_measure_single_file, args): args[0]
                for args in args_list
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if callback:
                    callback(result)

        return results

    def normalize_batch_parallel(
        self,
        file_paths: list[str],
        backup: bool = True,
        callback: Optional[Callable[[NormalizationResult], None]] = None,
    ) -> list[NormalizationResult]:
        """Normalize multiple files in parallel.

        Args:
            file_paths: List of file paths
            backup: Whether to backup original files
            callback: Optional callback for progress updates

        Returns:
            List of NormalizationResult objects
        """
        results = []
        args_list = [
            (fp, self.target_lufs, self.ffmpeg_path, backup)
            for fp in file_paths
        ]

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_normalize_single_file, args): args[0]
                for args in args_list
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if callback:
                    callback(result)

        return results

    def process_batch(
        self,
        file_paths: list[str],
        destructive: bool = False,
        callback: Optional[Callable[[str, bool], None]] = None,
    ) -> dict:
        """Process multiple files (legacy interface).

        Args:
            file_paths: List of file paths
            destructive: Whether to modify files
            callback: Optional callback(file_path, success) for progress

        Returns:
            Dict with processing results
        """
        results_dict = {
            "processed": 0,
            "failed": 0,
            "skipped": 0,
            "gains": {},
        }

        def result_callback(result: NormalizationResult):
            if result.success:
                results_dict["processed"] += 1
                if result.gain_db is not None:
                    results_dict["gains"][result.file_path] = result.gain_db
            else:
                results_dict["failed"] += 1

            if callback:
                callback(result.file_path, result.success)

        if destructive:
            self.normalize_batch_parallel(file_paths, callback=result_callback)
        else:
            self.measure_batch_parallel(file_paths, callback=result_callback)

        return results_dict

    def analyze_library(self, file_paths: list[str]) -> dict:
        """Analyze loudness distribution of a library using parallel processing.

        Args:
            file_paths: List of file paths

        Returns:
            Dict with statistics
        """
        results = self.measure_batch_parallel(file_paths)

        successful = [r for r in results if r.success and r.current_lufs is not None]

        if not successful:
            return {"error": "No files could be measured"}

        lufs_values = [r.current_lufs for r in successful]
        gains_needed = [r.gain_db for r in successful]

        import statistics

        return {
            "count": len(successful),
            "failed": len(results) - len(successful),
            "target": self.target_lufs,
            "workers": self.max_workers,
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
