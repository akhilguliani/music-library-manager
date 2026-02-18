"""Tests for MTG-Jamendo MoodTheme backend."""

from unittest.mock import MagicMock, patch

import numpy as np

from vdj_manager.analysis.mood_mtg_jamendo import (
    CLASS_NAMES,
    CLASS_NAMES_RAW,
    MTGJamendoBackend,
)


class TestClassNames:
    """Tests for the class name constants."""

    def test_56_raw_class_names(self):
        assert len(CLASS_NAMES_RAW) == 56

    def test_56_cleaned_class_names(self):
        assert len(CLASS_NAMES) == 56

    def test_raw_names_have_prefix(self):
        for name in CLASS_NAMES_RAW:
            assert name.startswith("mood/theme---")

    def test_cleaned_names_no_prefix(self):
        for name in CLASS_NAMES:
            assert "mood/theme---" not in name

    def test_cleaned_names_match_mood_classes(self):
        from vdj_manager.analysis.mood_backend import MOOD_CLASSES

        # CLASS_NAMES is in model output order; MOOD_CLASSES is sorted
        assert sorted(CLASS_NAMES) == MOOD_CLASSES

    def test_all_lowercase(self):
        for name in CLASS_NAMES:
            assert name == name.lower()


class TestMTGJamendoBackend:
    """Tests for MTGJamendoBackend class."""

    def test_name_property(self):
        backend = MTGJamendoBackend()
        assert backend.name == "mtg-jamendo"

    def test_is_available_without_essentia(self):
        """Without essentia installed, should report unavailable."""
        with patch.dict("sys.modules", {"essentia": None, "essentia.standard": None}):
            backend = MTGJamendoBackend()
            assert backend.is_available is False

    def test_analyze_returns_none_when_unavailable(self):
        with patch.dict("sys.modules", {"essentia": None, "essentia.standard": None}):
            backend = MTGJamendoBackend()
            assert backend.analyze("/fake/file.mp3") is None

    def test_get_mood_tags_returns_none_when_unavailable(self):
        with patch.dict("sys.modules", {"essentia": None, "essentia.standard": None}):
            backend = MTGJamendoBackend()
            assert backend.get_mood_tags("/fake/file.mp3") is None


class TestMTGJamendoAnalyzeMocked:
    """Tests for analyze() with mocked essentia pipeline."""

    def _make_backend_with_mock_essentia(self):
        """Create a backend with mocked essentia module."""
        backend = MTGJamendoBackend()
        backend._essentia_available = True
        backend._es = MagicMock()
        return backend

    def test_analyze_returns_56_class_dict(self):
        backend = self._make_backend_with_mock_essentia()

        # Mock audio loader
        fake_audio = np.zeros(16000, dtype=np.float32)
        backend._es.MonoLoader.return_value = MagicMock(return_value=fake_audio)

        # Mock embedding extractor
        fake_embeddings = np.zeros((10, 128), dtype=np.float32)
        backend._es.TensorflowPredictEffnetDiscogs.return_value = MagicMock(
            return_value=fake_embeddings
        )

        # Mock classifier — 10 frames, 56 classes
        fake_predictions = np.random.rand(10, 56).astype(np.float32)
        backend._es.TensorflowPredict2D.return_value = MagicMock(return_value=fake_predictions)

        with patch(
            "vdj_manager.analysis.model_downloader.ensure_model_files",
            return_value=("/fake/embedding.pb", "/fake/classifier.pb"),
        ):
            result = backend.analyze("/fake/file.mp3")

        assert result is not None
        assert len(result) == 56
        assert all(isinstance(k, str) for k in result)
        assert all(isinstance(v, float) for v in result.values())

    def test_analyze_averages_across_frames(self):
        backend = self._make_backend_with_mock_essentia()

        fake_audio = np.zeros(16000, dtype=np.float32)
        backend._es.MonoLoader.return_value = MagicMock(return_value=fake_audio)

        fake_embeddings = np.zeros((2, 128), dtype=np.float32)
        backend._es.TensorflowPredictEffnetDiscogs.return_value = MagicMock(
            return_value=fake_embeddings
        )

        # Two frames with known values
        predictions = np.zeros((2, 56), dtype=np.float32)
        predictions[0, 0] = 0.8  # action frame 0
        predictions[1, 0] = 0.4  # action frame 1
        predictions[0, 26] = 1.0  # happy frame 0
        predictions[1, 26] = 0.6  # happy frame 1
        backend._es.TensorflowPredict2D.return_value = MagicMock(return_value=predictions)

        with patch(
            "vdj_manager.analysis.model_downloader.ensure_model_files",
            return_value=("/fake/embedding.pb", "/fake/classifier.pb"),
        ):
            result = backend.analyze("/fake/file.mp3")

        assert result is not None
        assert abs(result["action"] - 0.6) < 0.001  # avg of 0.8 and 0.4
        assert abs(result["happy"] - 0.8) < 0.001  # avg of 1.0 and 0.6

    def test_analyze_returns_none_on_exception(self):
        backend = self._make_backend_with_mock_essentia()
        backend._es.MonoLoader.side_effect = RuntimeError("load error")

        with patch(
            "vdj_manager.analysis.model_downloader.ensure_model_files",
            return_value=("/fake/embedding.pb", "/fake/classifier.pb"),
        ):
            result = backend.analyze("/fake/file.mp3")

        assert result is None

    def test_analyze_class_names_in_result(self):
        backend = self._make_backend_with_mock_essentia()

        fake_audio = np.zeros(16000, dtype=np.float32)
        backend._es.MonoLoader.return_value = MagicMock(return_value=fake_audio)
        fake_embeddings = np.zeros((1, 128), dtype=np.float32)
        backend._es.TensorflowPredictEffnetDiscogs.return_value = MagicMock(
            return_value=fake_embeddings
        )
        fake_predictions = np.random.rand(1, 56).astype(np.float32)
        backend._es.TensorflowPredict2D.return_value = MagicMock(return_value=fake_predictions)

        with patch(
            "vdj_manager.analysis.model_downloader.ensure_model_files",
            return_value=("/fake/embedding.pb", "/fake/classifier.pb"),
        ):
            result = backend.analyze("/fake/file.mp3")

        assert result is not None
        for name in CLASS_NAMES:
            assert name in result

    def test_get_mood_tags_returns_filtered_list(self):
        backend = self._make_backend_with_mock_essentia()

        fake_audio = np.zeros(16000, dtype=np.float32)
        backend._es.MonoLoader.return_value = MagicMock(return_value=fake_audio)
        fake_embeddings = np.zeros((1, 128), dtype=np.float32)
        backend._es.TensorflowPredictEffnetDiscogs.return_value = MagicMock(
            return_value=fake_embeddings
        )

        # Most classes at 0, a few high
        predictions = np.zeros((1, 56), dtype=np.float32)
        predictions[0, 26] = 0.9  # happy
        predictions[0, 38] = 0.7  # party
        predictions[0, 54] = 0.3  # upbeat
        backend._es.TensorflowPredict2D.return_value = MagicMock(return_value=predictions)

        with patch(
            "vdj_manager.analysis.model_downloader.ensure_model_files",
            return_value=("/fake/embedding.pb", "/fake/classifier.pb"),
        ):
            tags = backend.get_mood_tags("/fake/file.mp3", threshold=0.1)

        assert tags is not None
        assert "happy" in tags
        assert "party" in tags
        assert "upbeat" in tags
        assert tags[0] == "happy"  # highest confidence first

    def test_get_mood_tags_respects_max_tags(self):
        backend = self._make_backend_with_mock_essentia()

        fake_audio = np.zeros(16000, dtype=np.float32)
        backend._es.MonoLoader.return_value = MagicMock(return_value=fake_audio)
        fake_embeddings = np.zeros((1, 128), dtype=np.float32)
        backend._es.TensorflowPredictEffnetDiscogs.return_value = MagicMock(
            return_value=fake_embeddings
        )

        # Many high scores
        predictions = np.full((1, 56), 0.5, dtype=np.float32)
        backend._es.TensorflowPredict2D.return_value = MagicMock(return_value=predictions)

        with patch(
            "vdj_manager.analysis.model_downloader.ensure_model_files",
            return_value=("/fake/embedding.pb", "/fake/classifier.pb"),
        ):
            tags = backend.get_mood_tags("/fake/file.mp3", threshold=0.1, max_tags=3)

        assert tags is not None
        assert len(tags) == 3
