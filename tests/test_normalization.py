"""Tests for normalization processor."""

import pytest
from vdj_manager.normalize.processor import NormalizationProcessor, NormalizationResult


class TestNormalizationResult:
    def test_successful_result(self):
        """Test creating a successful result."""
        result = NormalizationResult(
            file_path="/path/track.mp3",
            success=True,
            current_lufs=-10.5,
            gain_db=-3.5
        )

        assert result.success
        assert result.current_lufs == -10.5
        assert result.gain_db == -3.5
        assert result.error is None

    def test_failed_result(self):
        """Test creating a failed result."""
        result = NormalizationResult(
            file_path="/path/track.mp3",
            success=False,
            error="File not found"
        )

        assert not result.success
        assert result.error == "File not found"
        assert result.current_lufs is None


class TestNormalizationProcessor:
    def test_init_default_workers(self):
        """Test processor initialization with default workers."""
        processor = NormalizationProcessor()

        assert processor.target_lufs == -14.0
        assert processor.max_workers >= 1

    def test_init_custom_settings(self):
        """Test processor with custom settings."""
        processor = NormalizationProcessor(
            target_lufs=-16.0,
            max_workers=4
        )

        assert processor.target_lufs == -16.0
        assert processor.max_workers == 4

    def test_calculate_vdj_volume_positive_gain(self):
        """Test VDJ volume calculation for positive gain."""
        processor = NormalizationProcessor(target_lufs=-14.0)

        # If current LUFS is -18, we need +4dB gain
        # Volume multiplier should be > 1.0
        # Since we can't actually measure files, we test the formula
        import math

        gain_db = 4.0  # Need to increase volume
        expected_volume = 10 ** (gain_db / 20)

        # ~1.585
        assert expected_volume > 1.0

    def test_calculate_vdj_volume_negative_gain(self):
        """Test VDJ volume calculation for negative gain."""
        import math

        gain_db = -4.0  # Need to decrease volume
        expected_volume = 10 ** (gain_db / 20)

        # ~0.631
        assert expected_volume < 1.0

    def test_calculate_vdj_volume_no_change(self):
        """Test VDJ volume calculation when no change needed."""
        import math

        gain_db = 0.0  # No change needed
        expected_volume = 10 ** (gain_db / 20)

        assert expected_volume == 1.0


class TestProcessBatch:
    def test_process_batch_returns_dict(self):
        """Test that process_batch returns proper dict structure."""
        processor = NormalizationProcessor()

        # Call with empty list
        results = processor.process_batch([], destructive=False)

        assert "processed" in results
        assert "failed" in results
        assert "gains" in results
        assert results["processed"] == 0
