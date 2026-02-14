# Music Mood/Emotion Analysis Models - Research Comparison

*Last updated: February 2026*

This document compares available models and approaches for music mood/emotion recognition (MER), evaluated for use in VDJ Manager's mood classification pipeline.

## Current Implementation

VDJ Manager uses a 3-tier fallback chain with pluggable model backends:
1. **Online: Last.fm tags** -> weighted tag-to-mood mapping (160+ tags to 56-class vocabulary)
2. **Online: MusicBrainz genres** -> genre-to-mood mapping
3. **Local: MTG-Jamendo MoodTheme** (default) -> 56-class multi-label CNN via essentia-tensorflow
4. **Local: Heuristic** (legacy) -> BPM/RMS/spectral-based mood estimation

The 56-class vocabulary (MTG-Jamendo MoodTheme): `action`, `adventure`, `advertising`, `background`, `ballad`, `calm`, `children`, `christmas`, `commercial`, `cool`, `corporate`, `dark`, `deep`, `documentary`, `drama`, `dramatic`, `dream`, `emotional`, `energetic`, `epic`, `fast`, `film`, `fun`, `funny`, `game`, `groovy`, `happy`, `heavy`, `holiday`, `hopeful`, `inspiring`, `love`, `meditative`, `melancholic`, `melodic`, `motivational`, `movie`, `nature`, `party`, `positive`, `powerful`, `relaxing`, `retro`, `romantic`, `sad`, `sexy`, `slow`, `soft`, `soundscape`, `space`, `sport`, `summer`, `trailer`, `travel`, `upbeat`, `uplifting`

Multi-label tagging assigns multiple mood tags per track based on configurable confidence threshold (default 0.10, max 5 tags).

---

## Model Comparison

| Model | Type | Mood Classes | Accuracy | Speed (per track) | GPU Required | Install Size | Python Package |
|-------|------|-------------|----------|-------------------|-------------|-------------|----------------|
| **Essentia EffnetDiscogs** (current) | Supervised CNN | 5 binary (happy/sad/aggressive/relaxed/party) | ~85% ROC-AUC (binary) | ~1-3s CPU | No | ~200MB | `essentia-tensorflow` |
| **Essentia MTG-Jamendo MoodTheme** | Multi-label CNN | 56 classes (calm, dark, happy, melancholic, party, sad, etc.) | PR-AUC varies by class | ~1-3s CPU | No | ~200MB | `essentia-tensorflow` |
| **Music2Emo** | Multitask (MERT + knowledge distillation) | Categorical + Valence/Arousal (1-9 scale) | SOTA on MTG-Jamendo, DEAM, PMEmo, EmoMusic | ~5-10s GPU, ~30s+ CPU | Recommended | ~2GB+ | PyTorch, HuggingFace |
| **CLAP** (LAION/Microsoft) | Zero-shot (text-audio contrastive) | Any text prompt (flexible) | ~57-60% on GTZAN (zero-shot) | ~2-5s CPU | No | ~1GB | `transformers`, `laion-clap` |
| **MERT** | Self-supervised embeddings | Requires fine-tuning head | Best embeddings for music tasks | ~3-5s GPU | Yes | ~1.2GB | `transformers` |
| **MusicNN** | Supervised CNN | 50 tags (MTT/MSD datasets) | Competitive with Essentia | ~1-2s CPU | No | ~100MB | `musicnn` |
| **OpenL3** | Audio embeddings + classifier | Requires training classifier | ~72% F1 with Random Forest | ~2-3s CPU | No | ~500MB | `openl3` |

---

## Detailed Analysis

### 1. Essentia-TensorFlow (Current - Local Fallback)

**What we use now**: Binary mood classifiers (happy/non-happy, sad/non-sad, etc.) via `essentia-tensorflow`.

**Strengths:**
- Lightweight, runs on CPU, real-time capable
- Well-maintained by MTG/UPF (Music Technology Group, Barcelona)
- Multiple embedding backends: EffnetDiscogs, VGGish, YAMNet, MSD-MusicNN
- Also offers `mtg_jamendo_moodtheme` with 56 fine-grained mood/theme classes

**Weaknesses:**
- Binary classifiers only detect one mood at a time (need to run 5+ models)
- Limited to pre-defined mood categories
- Accuracy varies significantly by mood class
- "Unknown" results common on non-mainstream genres

**Upgrade path:** Switch from our basic heuristic approach to using the official `mtg_jamendo_moodtheme` multi-label model, which provides 56 mood/theme predictions in one pass.

### 2. Music2Emo (Recommended Upgrade)

**The most promising model** for our use case. Released February 2025 by AMAAI Lab.

**Architecture:** Uses MERT embeddings combined with musical features (key, chords) and knowledge distillation. Multitask learning framework handles both categorical and dimensional (valence/arousal) predictions simultaneously.

**Strengths:**
- State-of-the-art on MTG-Jamendo, DEAM, PMEmo, and EmoMusic benchmarks
- Outperforms MediaEval 2021 competition winners
- Provides both categorical moods AND valence/arousal scores (1-9 scale)
- Available on HuggingFace with pre-trained weights
- Active development (v1.0, Feb 2025)

**Weaknesses:**
- Requires PyTorch (~2GB+ dependencies)
- Significantly slower on CPU (GPU recommended)
- Newer model, less battle-tested in production
- Valence/arousal may need mapping to our 7 canonical categories

### 3. CLAP (Contrastive Language-Audio Pretraining)

**Zero-shot approach**: encode audio and text ("happy music", "sad music") into same space, classify by cosine similarity.

**Strengths:**
- No training needed -- define moods as text prompts at runtime
- Extremely flexible (add/change mood categories without retraining)
- Can use any mood description ("dreamy Sunday morning music")
- Available via HuggingFace Transformers

**Weaknesses:**
- Zero-shot accuracy is lower than supervised models (~57-60% on GTZAN)
- Needs careful prompt engineering for best results
- Larger model size (~1GB)

### 4. MERT (Music Understanding Model)

**Self-supervised embeddings** trained with Constant-Q Transform (CQT) for pitch/harmonic awareness.

**Best use:** As an embedding backbone if we want to train our own mood classifier on a custom dataset.

### 5. MusicNN

**Pre-trained CNNs** for music audio tagging by Jordi Pons.

**Strengths:**
- Very lightweight and fast
- Pre-trained on MagnaTagATune (19k songs) and Million Song Dataset (200k songs)

**Weaknesses:**
- Older model (2019), surpassed by newer approaches
- TensorFlow 1.x dependency (compatibility issues with modern TF)

---

## Recommendation

### Short-term (low effort, high impact) -- IMPLEMENTED

**Upgraded Essentia to use the `mtg_jamendo_moodtheme` model** with a `MoodBackend` protocol abstraction. The implementation includes:
- 56-class multi-label predictions per track in a single pass
- Configurable confidence threshold (default 0.10) and max tags (default 5)
- Auto-download of model files (~87MB) to `~/.vdj_manager/models/`
- Model-aware cache keys (`mood:mtg-jamendo` vs `mood:heuristic`) for clean re-analysis
- GUI model selector, threshold controls, and "Re-analyze All" button
- CLI `--model`, `--threshold`, `--max-tags` options
- Online tag mappings expanded to 56-class vocabulary (160+ tags)

### Medium-term (best accuracy)

**Add Music2Emo as a new analysis backend.** This is the current state-of-the-art for music emotion recognition with both categorical and valence/arousal predictions. Add it as an optional dependency alongside essentia:

```
music2emo = ["torch>=2.0", "transformers>=4.30"]
```

The fallback chain would become:
1. Online: Last.fm tags
2. Online: MusicBrainz genres
3. Local: Music2Emo (if installed, GPU available)
4. Local: Essentia MTG-Jamendo MoodTheme (CPU fallback)

### Long-term (most flexible)

**CLAP for custom mood taxonomies.** If users want to define their own mood categories beyond our 7 canonical moods, CLAP's zero-shot approach allows runtime-configurable mood labels with no retraining.

---

## Datasets for Evaluation

If we want to benchmark our implementation:

| Dataset | Tracks | Labels | License |
|---------|--------|--------|---------|
| [MTG-Jamendo](https://mtg.github.io/mtg-jamendo-dataset/) | 55,000 | 56 mood/theme tags | CC |
| [DEAM](https://cvml.unige.ch/databases/DEAM/) | 1,802 | Valence/Arousal | Research |
| [PMEmo](https://github.com/HuiZhangDB/PMEmo) | 794 | Valence/Arousal | Research |
| [EmoMusic](http://cvml.unige.ch/databases/emoMusic/) | 744 | Valence/Arousal | Research |
| [MagnaTagATune](https://mirg.city.ac.uk/codeapps/the-magnatagatune-dataset) | 25,863 | 188 tags | Research |
