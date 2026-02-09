"""Audio feature extraction and Mixed In Key tag reader."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4
    from mutagen.flac import FLAC
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


class AudioFeatureExtractor:
    """Extract audio features using librosa."""

    def __init__(self, sample_rate: int = 22050, duration: float = 60.0):
        """Initialize feature extractor.

        Args:
            sample_rate: Sample rate for audio loading
            duration: Duration in seconds to analyze (from middle of track)
        """
        if not LIBROSA_AVAILABLE:
            raise ImportError("librosa is required for audio feature extraction")

        self.sample_rate = sample_rate
        self.duration = duration

    def load_audio(self, file_path: str, offset: Optional[float] = None) -> tuple:
        """Load audio file.

        Uses soundfile directly when possible to avoid librosa's audioread
        fallback, which spawns ffmpeg subprocesses that leak file descriptors
        in long-running ProcessPoolExecutor workers.

        Args:
            file_path: Path to audio file
            offset: Start position in seconds (None = auto-detect middle)

        Returns:
            Tuple of (audio samples, sample rate)
        """
        import soundfile as sf

        # Try soundfile first (handles WAV, FLAC, OGG natively without
        # spawning subprocesses). Fall back to librosa for MP3/M4A/etc.
        try:
            info = sf.info(file_path)
            total_duration = info.duration

            if offset is None:
                offset = max(0, (total_duration - self.duration) / 2)

            start_frame = int(offset * info.samplerate)
            n_frames = int(min(self.duration, total_duration - offset) * info.samplerate)

            data, sr = sf.read(file_path, start=start_frame, frames=n_frames,
                               dtype="float32", always_2d=False)
            # Convert to mono if stereo
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            # Resample if needed
            if sr != self.sample_rate:
                data = librosa.resample(data, orig_sr=sr, target_sr=self.sample_rate)
                sr = self.sample_rate
            return data, sr
        except Exception as e:
            logger.debug("soundfile failed for %s, falling back to librosa: %s", file_path, e)

        # Fallback to librosa (uses audioread for MP3, M4A, etc.)
        total_duration = librosa.get_duration(path=file_path)

        if offset is None:
            offset = max(0, (total_duration - self.duration) / 2)

        y, sr = librosa.load(
            file_path,
            sr=self.sample_rate,
            offset=offset,
            duration=min(self.duration, total_duration - offset),
        )
        return y, sr

    def extract_features(self, file_path: str) -> dict:
        """Extract all audio features from a file.

        Args:
            file_path: Path to audio file

        Returns:
            Dict with extracted features
        """
        y, sr = self.load_audio(file_path)

        features = {
            "tempo": self._extract_tempo(y, sr),
            "rms_energy": self._extract_rms(y),
            "spectral_centroid": self._extract_spectral_centroid(y, sr),
            "spectral_bandwidth": self._extract_spectral_bandwidth(y, sr),
            "onset_strength": self._extract_onset_strength(y, sr),
            "zero_crossing_rate": self._extract_zcr(y),
        }

        return features

    def _extract_tempo(self, y: np.ndarray, sr: int) -> float:
        """Extract tempo (BPM)."""
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        return float(tempo)

    def _extract_rms(self, y: np.ndarray) -> float:
        """Extract RMS energy."""
        rms = librosa.feature.rms(y=y)
        return float(np.mean(rms))

    def _extract_spectral_centroid(self, y: np.ndarray, sr: int) -> float:
        """Extract spectral centroid (brightness)."""
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        return float(np.mean(centroid))

    def _extract_spectral_bandwidth(self, y: np.ndarray, sr: int) -> float:
        """Extract spectral bandwidth."""
        bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
        return float(np.mean(bandwidth))

    def _extract_onset_strength(self, y: np.ndarray, sr: int) -> float:
        """Extract onset strength (percussiveness)."""
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        return float(np.mean(onset_env))

    def _extract_zcr(self, y: np.ndarray) -> float:
        """Extract zero-crossing rate."""
        zcr = librosa.feature.zero_crossing_rate(y)
        return float(np.mean(zcr))


class MixedInKeyReader:
    """Read Mixed In Key tags from audio files."""

    # Mixed In Key tag names
    MIK_TAGS = {
        "energy": ["ENERGYLEVEL", "ENERGY LEVEL", "MIK_ENERGY", "TRAKTOR4.ENERGY"],
        "key": ["INITIALKEY", "KEY", "MIK_KEY"],
        "bpm": ["BPM", "TBPM"],
    }

    def __init__(self):
        if not MUTAGEN_AVAILABLE:
            raise ImportError("mutagen is required for reading audio tags")

    def read_tags(self, file_path: str) -> dict:
        """Read Mixed In Key tags from an audio file.

        Args:
            file_path: Path to audio file

        Returns:
            Dict with MIK data (energy, key, bpm)
        """
        result = {
            "energy": None,
            "key": None,
            "bpm": None,
            "raw_tags": {},
        }

        path = Path(file_path)
        ext = path.suffix.lower()

        try:
            if ext == ".mp3":
                result = self._read_mp3_tags(file_path)
            elif ext in (".m4a", ".aac", ".mp4"):
                result = self._read_mp4_tags(file_path)
            elif ext == ".flac":
                result = self._read_flac_tags(file_path)
            else:
                # Try generic mutagen
                result = self._read_generic_tags(file_path)
        except Exception as e:
            logger.warning("Failed to read tags from %s: %s", file_path, e)

        return result

    def _read_mp3_tags(self, file_path: str) -> dict:
        """Read tags from MP3 file."""
        result = {"energy": None, "key": None, "bpm": None, "raw_tags": {}}

        try:
            audio = ID3(file_path)

            # Check TXXX frames (custom tags where MIK stores data)
            for frame in audio.values():
                frame_id = getattr(frame, "FrameID", "")

                if frame_id == "TXXX":
                    desc = getattr(frame, "desc", "").upper()
                    text = str(frame.text[0]) if frame.text else ""

                    result["raw_tags"][desc] = text

                    # Check for energy
                    for tag_name in self.MIK_TAGS["energy"]:
                        if tag_name in desc:
                            try:
                                result["energy"] = int(text)
                            except ValueError:
                                pass

                    # Check for key
                    for tag_name in self.MIK_TAGS["key"]:
                        if tag_name in desc:
                            result["key"] = text

                elif frame_id == "TKEY":
                    result["key"] = str(frame.text[0]) if frame.text else None

                elif frame_id == "TBPM":
                    try:
                        result["bpm"] = float(frame.text[0]) if frame.text else None
                    except ValueError:
                        pass

        except Exception as e:
            logger.warning("Failed to read MP3 tags from %s: %s", file_path, e)

        return result

    def _read_mp4_tags(self, file_path: str) -> dict:
        """Read tags from M4A/AAC file."""
        result = {"energy": None, "key": None, "bpm": None, "raw_tags": {}}

        try:
            audio = MP4(file_path)

            for key, value in audio.tags.items():
                result["raw_tags"][key] = str(value[0]) if value else ""

                key_upper = key.upper()

                # Check for energy
                for tag_name in self.MIK_TAGS["energy"]:
                    if tag_name in key_upper:
                        try:
                            result["energy"] = int(value[0])
                        except (ValueError, IndexError):
                            pass

                # Check for key (often stored as "----:com.apple.iTunes:initialkey")
                if "INITIALKEY" in key_upper or "KEY" in key_upper:
                    result["key"] = str(value[0]) if value else None

                # BPM
                if key == "tmpo":
                    try:
                        result["bpm"] = float(value[0])
                    except (ValueError, IndexError):
                        pass

        except Exception as e:
            logger.warning("Failed to read MP4 tags from %s: %s", file_path, e)

        return result

    def _read_flac_tags(self, file_path: str) -> dict:
        """Read tags from FLAC file."""
        result = {"energy": None, "key": None, "bpm": None, "raw_tags": {}}

        try:
            audio = FLAC(file_path)

            for key, value in audio.tags:
                result["raw_tags"][key.upper()] = value

                key_upper = key.upper()

                for tag_name in self.MIK_TAGS["energy"]:
                    if tag_name in key_upper:
                        try:
                            result["energy"] = int(value)
                        except ValueError:
                            pass

                for tag_name in self.MIK_TAGS["key"]:
                    if tag_name in key_upper:
                        result["key"] = value

                if key_upper == "BPM":
                    try:
                        result["bpm"] = float(value)
                    except ValueError:
                        pass

        except Exception as e:
            logger.warning("Failed to read FLAC tags from %s: %s", file_path, e)

        return result

    def _read_generic_tags(self, file_path: str) -> dict:
        """Read tags using generic mutagen interface."""
        result = {"energy": None, "key": None, "bpm": None, "raw_tags": {}}

        try:
            audio = MutagenFile(file_path, easy=True)
            if audio is None:
                return result

            for key, value in audio.items():
                result["raw_tags"][key] = str(value[0]) if value else ""

        except Exception as e:
            logger.warning("Failed to read tags from %s: %s", file_path, e)

        return result

    def has_mik_data(self, file_path: str) -> bool:
        """Check if file has any Mixed In Key data."""
        tags = self.read_tags(file_path)
        return tags["energy"] is not None or tags["key"] is not None
