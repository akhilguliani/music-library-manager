# Analysis API

## Energy Analyzer

::: vdj_manager.analysis.energy
    options:
      show_source: true
      members:
        - EnergyAnalyzer

## Audio Features

::: vdj_manager.analysis.audio_features
    options:
      show_source: true
      members:
        - AudioFeatureExtractor
        - MixedInKeyReader

## Mood Backend

::: vdj_manager.analysis.mood_backend
    options:
      show_source: true
      members:
        - MoodBackend
        - MoodModel
        - get_backend

## Online Mood

::: vdj_manager.analysis.online_mood
    options:
      show_source: true
      members:
        - lookup_online_mood
        - LastFmLookup
        - MusicBrainzLookup
        - TagToMoodMapper
