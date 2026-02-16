"""Tests for EnergyAnalyzer exception logging."""

import logging
from unittest.mock import MagicMock

from vdj_manager.analysis.energy import EnergyAnalyzer


class TestEnergyAnalyzerLogging:
    """Tests that exceptions during analysis are logged."""

    def test_analyze_logs_warning_on_exception(self, caplog):
        """analyze() should log a warning when feature extraction fails."""
        analyzer = EnergyAnalyzer()
        mock_ext = MagicMock()
        mock_ext.extract_features.side_effect = RuntimeError("bad file")
        analyzer._extractor = mock_ext

        with caplog.at_level(logging.WARNING, logger="vdj_manager.analysis.energy"):
            result = analyzer.analyze("/fake/file.mp3")

        assert result is None
        assert "Energy analysis failed" in caplog.text
        assert "/fake/file.mp3" in caplog.text

    def test_analyze_returns_none_on_exception(self):
        """analyze() should return None when feature extraction fails."""
        analyzer = EnergyAnalyzer()
        mock_ext = MagicMock()
        mock_ext.extract_features.side_effect = ValueError("corrupt audio")
        analyzer._extractor = mock_ext

        result = analyzer.analyze("/fake/file.mp3")
        assert result is None
