"""LUFS loudness measurement using ffmpeg."""

import json
import subprocess
from pathlib import Path
from typing import Optional


class LoudnessMeasurer:
    """Measure audio loudness in LUFS using ffmpeg."""

    _verified_paths: set[str] = set()

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        """Initialize loudness measurer.

        Args:
            ffmpeg_path: Path to ffmpeg binary
        """
        self.ffmpeg_path = ffmpeg_path
        self._verify_ffmpeg()

    def _verify_ffmpeg(self) -> None:
        """Verify ffmpeg is available (cached per path)."""
        if self.ffmpeg_path in LoudnessMeasurer._verified_paths:
            return

        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise RuntimeError("ffmpeg not functional")
        except FileNotFoundError:
            raise RuntimeError(f"ffmpeg not found at: {self.ffmpeg_path}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffmpeg timed out")

        LoudnessMeasurer._verified_paths.add(self.ffmpeg_path)

    def measure(self, file_path: str) -> Optional[float]:
        """Measure integrated loudness of an audio file.

        Args:
            file_path: Path to audio file

        Returns:
            Integrated loudness in LUFS, or None on error
        """
        if not Path(file_path).exists():
            return None

        try:
            # Use ffmpeg with loudnorm filter to measure loudness
            result = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-i", file_path,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                    "-f", "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutes max
            )

            # Parse loudnorm output from stderr
            stderr = result.stderr
            return self._parse_loudnorm_output(stderr)

        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None

    @staticmethod
    def _parse_ffmpeg_json(stderr: str) -> Optional[dict]:
        """Parse JSON block from ffmpeg stderr output.

        Args:
            stderr: ffmpeg stderr output

        Returns:
            Parsed JSON dict, or None if no valid JSON found
        """
        lines = stderr.split("\n")
        json_lines = []
        in_json = False

        for line in lines:
            if "{" in line:
                in_json = True
                json_lines.append(line[line.index("{"):])
            elif in_json:
                json_lines.append(line)
                if "}" in line:
                    break

        if not json_lines:
            return None

        try:
            json_str = "\n".join(json_lines)
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return None

    def _parse_loudnorm_output(self, stderr: str) -> Optional[float]:
        """Parse loudnorm JSON output from ffmpeg stderr.

        Args:
            stderr: ffmpeg stderr output

        Returns:
            Integrated loudness in LUFS
        """
        data = self._parse_ffmpeg_json(stderr)
        if data is None:
            return None

        input_i = data.get("input_i")
        if input_i is None:
            return None

        try:
            return float(input_i)
        except (TypeError, ValueError):
            return None

    def measure_detailed(self, file_path: str) -> Optional[dict]:
        """Get detailed loudness measurements.

        Args:
            file_path: Path to audio file

        Returns:
            Dict with integrated, true peak, LRA values
        """
        if not Path(file_path).exists():
            return None

        try:
            result = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-i", file_path,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                    "-f", "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            data = self._parse_ffmpeg_json(result.stderr)
            if data is not None:
                return {
                    "integrated": float(data.get("input_i", 0)),
                    "true_peak": float(data.get("input_tp", 0)),
                    "lra": float(data.get("input_lra", 0)),
                    "threshold": float(data.get("input_thresh", 0)),
                }

        except Exception:
            pass

        return None

    def measure_batch(self, file_paths: list[str]) -> dict[str, Optional[float]]:
        """Measure loudness for multiple files.

        Args:
            file_paths: List of file paths

        Returns:
            Dict mapping file paths to LUFS values
        """
        results = {}
        for path in file_paths:
            results[path] = self.measure(path)
        return results
