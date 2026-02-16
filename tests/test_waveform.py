"""Tests for waveform peak generation and caching."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from vdj_manager.player.waveform import (
    WaveformCache,
    generate_waveform_peaks,
)


# =============================================================================
# generate_waveform_peaks tests
# =============================================================================


class TestGenerateWaveformPeaks:
    """Tests for waveform peak generation."""

    def test_generates_correct_width(self):
        """Peaks array should match target_width."""
        fake_audio = np.sin(np.linspace(0, 10 * np.pi, 22050))
        with patch("librosa.load", return_value=(fake_audio, 22050)):
            peaks = generate_waveform_peaks("/fake.mp3", target_width=100, sr=22050)
            assert len(peaks) == 100

    def test_peaks_normalized_0_to_1(self):
        """Peak values should be in [0, 1] range."""
        fake_audio = np.random.randn(44100)
        with patch("librosa.load", return_value=(fake_audio, 22050)):
            peaks = generate_waveform_peaks("/fake.mp3", target_width=200)
            assert peaks.max() <= 1.0
            assert peaks.min() >= 0.0

    def test_empty_audio(self):
        """Should return zeros for empty audio."""
        with patch("librosa.load", return_value=(np.array([]), 22050)):
            peaks = generate_waveform_peaks("/fake.mp3", target_width=50)
            assert len(peaks) == 50
            assert peaks.max() == 0.0

    def test_short_audio_pads(self):
        """Short audio should be padded to target_width."""
        fake_audio = np.ones(10)
        with patch("librosa.load", return_value=(fake_audio, 22050)):
            peaks = generate_waveform_peaks("/fake.mp3", target_width=100)
            assert len(peaks) == 100

    def test_vectorized_peaks_match_loop(self):
        """Vectorized peak extraction should match a naive Python loop."""
        np.random.seed(42)
        fake_audio = np.random.randn(22050).astype(np.float32)
        target_width = 100

        # Compute expected peaks using the old Python loop
        bin_size = max(1, len(fake_audio) // target_width)
        expected = []
        for i in range(0, len(fake_audio), bin_size):
            chunk = fake_audio[i : i + bin_size]
            expected.append(float(np.max(np.abs(chunk))))
        expected = np.array(expected[:target_width])
        if len(expected) < target_width:
            expected = np.pad(expected, (0, target_width - len(expected)))
        peak_max = expected.max()
        if peak_max > 0:
            expected = expected / peak_max

        with patch("librosa.load", return_value=(fake_audio, 22050)):
            actual = generate_waveform_peaks("/fake.mp3", target_width=target_width, sr=22050)

        np.testing.assert_array_almost_equal(actual, expected, decimal=5)


# =============================================================================
# WaveformCache tests
# =============================================================================


class TestWaveformCache:
    """Tests for SQLite waveform cache."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = WaveformCache(db_path=Path(self._tmpdir) / "test_waveforms.db")

    def test_cache_miss_returns_none(self):
        assert self.cache.get("/nonexistent.mp3", width=100) is None

    def test_put_and_get(self, tmp_path):
        """Should store and retrieve waveform peaks."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data" * 100)

        peaks = np.array([0.1, 0.5, 0.9, 0.3, 0.7])
        self.cache.put(str(test_file), peaks, width=5)
        result = self.cache.get(str(test_file), width=5)
        assert result is not None
        np.testing.assert_array_almost_equal(result, peaks)

    def test_cache_invalidation_on_mtime_change(self, tmp_path):
        """Cache should miss when file is modified."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"original")

        peaks = np.array([0.5, 0.5])
        self.cache.put(str(test_file), peaks, width=2)

        # Modify the file (changes mtime and size)
        test_file.write_bytes(b"modified content that is longer")

        result = self.cache.get(str(test_file), width=2)
        assert result is None

    def test_different_widths_separate_entries(self, tmp_path):
        """Different widths should be cached separately."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data" * 100)

        peaks_100 = np.ones(100)
        peaks_200 = np.ones(200) * 0.5
        self.cache.put(str(test_file), peaks_100, width=100)
        self.cache.put(str(test_file), peaks_200, width=200)

        result_100 = self.cache.get(str(test_file), width=100)
        result_200 = self.cache.get(str(test_file), width=200)
        assert len(result_100) == 100
        assert len(result_200) == 200
        assert result_100[0] == 1.0
        assert result_200[0] == 0.5


# =============================================================================
# Soundfile path tests
# =============================================================================


class TestGenerateWaveformPeaksSoundfile:
    """Tests for soundfile-first path (WAV/FLAC/OGG)."""

    def test_wav_uses_soundfile(self):
        """WAV files should use soundfile, not librosa.load."""
        fake_data = np.random.randn(22050, 2).astype(np.float32)
        with patch("soundfile.read", return_value=(fake_data, 22050)) as sf_mock:
            peaks = generate_waveform_peaks("/fake.wav", target_width=100, sr=22050)
            sf_mock.assert_called_once()
            assert len(peaks) == 100

    def test_flac_uses_soundfile(self):
        """FLAC files should use soundfile."""
        fake_data = np.random.randn(22050, 1).astype(np.float32)
        with patch("soundfile.read", return_value=(fake_data, 22050)) as sf_mock:
            peaks = generate_waveform_peaks("/fake.flac", target_width=50, sr=22050)
            sf_mock.assert_called_once()
            assert len(peaks) == 50

    def test_mp3_uses_librosa(self):
        """MP3 files should fall back to librosa."""
        fake_audio = np.sin(np.linspace(0, 10 * np.pi, 22050))
        with patch("librosa.load", return_value=(fake_audio, 22050)) as lib_mock:
            peaks = generate_waveform_peaks("/fake.mp3", target_width=100, sr=22050)
            lib_mock.assert_called_once()
            assert len(peaks) == 100

    def test_soundfile_resamples_if_sr_differs(self):
        """Should resample when file sr differs from target sr."""
        fake_data = np.random.randn(44100, 1).astype(np.float32)
        resampled = np.random.randn(22050).astype(np.float32)
        with patch("soundfile.read", return_value=(fake_data, 44100)), \
             patch("librosa.resample", return_value=resampled) as resample_mock:
            peaks = generate_waveform_peaks("/fake.wav", target_width=100, sr=22050)
            resample_mock.assert_called_once()
            assert len(peaks) == 100
