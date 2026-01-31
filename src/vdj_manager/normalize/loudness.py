"""LUFS loudness measurement using ffmpeg."""

import json
import subprocess
from pathlib import Path
from typing import Optional


class LoudnessMeasurer:
    """Measure audio loudness in LUFS using ffmpeg."""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        """Initialize loudness measurer.

        Args:
            ffmpeg_path: Path to ffmpeg binary
        """
        self.ffmpeg_path = ffmpeg_path
        self._verify_ffmpeg()

    def _verify_ffmpeg(self) -> None:
        """Verify ffmpeg is available."""
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

    def _parse_loudnorm_output(self, stderr: str) -> Optional[float]:
        """Parse loudnorm JSON output from ffmpeg stderr.

        Args:
            stderr: ffmpeg stderr output

        Returns:
            Integrated loudness in LUFS
        """
        # Find the JSON block in stderr
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
            data = json.loads(json_str)
            return float(data.get("input_i", 0))
        except (json.JSONDecodeError, ValueError):
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

            # Parse JSON from stderr
            stderr = result.stderr
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

            if json_lines:
                json_str = "\n".join(json_lines)
                data = json.loads(json_str)
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
