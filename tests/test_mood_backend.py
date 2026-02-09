"""Tests for mood backend protocol, registry, and utilities."""

from unittest.mock import patch

import pytest

from vdj_manager.analysis.mood_backend import (
    MOOD_CLASSES,
    MOOD_CLASSES_SET,
    MoodModel,
    cache_key_for_model,
    get_backend,
    select_top_moods,
)


class TestMoodModel:
    """Tests for MoodModel enum."""

    def test_enum_values(self):
        assert MoodModel.MTG_JAMENDO == "mtg-jamendo"
        assert MoodModel.HEURISTIC == "heuristic"

    def test_enum_from_string(self):
        assert MoodModel("mtg-jamendo") == MoodModel.MTG_JAMENDO
        assert MoodModel("heuristic") == MoodModel.HEURISTIC

    def test_unknown_value_raises(self):
        with pytest.raises(ValueError):
            MoodModel("nonexistent")


class TestMoodClasses:
    """Tests for the MOOD_CLASSES vocabulary."""

    def test_has_56_classes(self):
        assert len(MOOD_CLASSES) == 56

    def test_contains_key_moods(self):
        for mood in ["happy", "sad", "party", "calm", "dark", "epic", "romantic"]:
            assert mood in MOOD_CLASSES_SET

    def test_all_lowercase(self):
        for mood in MOOD_CLASSES:
            assert mood == mood.lower()

    def test_no_duplicates(self):
        assert len(MOOD_CLASSES) == len(set(MOOD_CLASSES))

    def test_sorted(self):
        assert MOOD_CLASSES == sorted(MOOD_CLASSES)


class TestCacheKeyForModel:
    """Tests for cache_key_for_model."""

    def test_mtg_jamendo(self):
        assert cache_key_for_model(MoodModel.MTG_JAMENDO) == "mood:mtg-jamendo"

    def test_heuristic(self):
        assert cache_key_for_model(MoodModel.HEURISTIC) == "mood:heuristic"


class TestSelectTopMoods:
    """Tests for select_top_moods multi-label selection."""

    def test_basic_threshold(self):
        scores = {"happy": 0.8, "sad": 0.05, "party": 0.15}
        result = select_top_moods(scores, threshold=0.1)
        assert result == ["happy", "party"]

    def test_always_top_1_even_below_threshold(self):
        scores = {"happy": 0.05, "sad": 0.02}
        result = select_top_moods(scores, threshold=0.1)
        assert result == ["happy"]

    def test_respects_max_tags(self):
        scores = {f"mood{i}": 0.5 for i in range(10)}
        result = select_top_moods(scores, threshold=0.1, max_tags=3)
        assert len(result) == 3

    def test_sorted_by_confidence(self):
        scores = {"party": 0.3, "happy": 0.8, "sad": 0.5}
        result = select_top_moods(scores, threshold=0.1)
        assert result == ["happy", "sad", "party"]

    def test_empty_scores(self):
        assert select_top_moods({}) == []

    def test_all_above_threshold(self):
        scores = {"happy": 0.9, "sad": 0.8, "party": 0.7}
        result = select_top_moods(scores, threshold=0.1, max_tags=5)
        assert len(result) == 3

    def test_threshold_zero_includes_all(self):
        scores = {"a": 0.01, "b": 0.02, "c": 0.5}
        result = select_top_moods(scores, threshold=0.0, max_tags=10)
        assert len(result) == 3

    def test_high_threshold_still_includes_top_1(self):
        scores = {"happy": 0.3, "sad": 0.2}
        result = select_top_moods(scores, threshold=0.5)
        assert result == ["happy"]


class TestGetBackend:
    """Tests for get_backend factory."""

    def test_heuristic_backend(self):
        backend = get_backend(MoodModel.HEURISTIC)
        from vdj_manager.analysis.mood import MoodAnalyzer
        assert isinstance(backend, MoodAnalyzer)

    def test_mtg_jamendo_backend(self):
        from vdj_manager.analysis.mood_mtg_jamendo import MTGJamendoBackend
        backend = get_backend(MoodModel.MTG_JAMENDO)
        assert isinstance(backend, MTGJamendoBackend)

    def test_unknown_model_string_raises(self):
        with pytest.raises(ValueError):
            MoodModel("nonexistent")
