# Audio Analysis

VDJ Manager provides AI-powered audio analysis for energy levels, mood classification, and Mixed In Key tag import.

## Energy Analysis

Calculate energy levels (1-10) for tracks using audio features:

```bash
vdj-manager analyze energy --all              # All tracks
vdj-manager analyze energy --untagged         # Only untagged tracks
```

Energy is calculated from tempo, RMS energy, and spectral centroid, then stored in `Tags/@Grouping` as a plain number (e.g., "7").

## Mood Classification

Multi-label mood classification using AI models:

```bash
vdj-manager analyze mood --all
```

Moods are stored in `Tags/@User2` as space-separated hashtags (e.g., "#happy #uplifting #summer").

### Available Models

| Model | Description |
|-------|-------------|
| MTG-Jamendo | 56-class multi-label CNN (recommended). Auto-downloads ~80MB model. |
| Heuristic | Legacy audio-feature-based classification. No model download needed. |

### Online Mood Enrichment

When enabled, mood lookup uses a multi-tier fallback chain that never gives up:

1. **Last.fm track tags** (cleaned artist/title metadata)
2. **Last.fm artist tags** (fallback when track has no tags)
3. **MusicBrainz genres**
4. **Primary local model** (MTG-Jamendo or Heuristic)
5. **Fallback local model** (the other model)
6. **"unknown"** (last resort — analysis never returns "failed")

All online lookups use **exponential backoff retry** (up to 3 retries) for transient network errors, including library-specific exceptions like `musicbrainzngs.NetworkError` and `pylast.NetworkError`.

Setup:

```bash
# Set Last.fm API key
export LASTFM_API_KEY=your_api_key_here
# Or persist to file
echo "your_api_key_here" > ~/.vdj_manager/lastfm_api_key
```

Get a free API key at [last.fm/api/account/create](https://www.last.fm/api/account/create).

## Mixed In Key Import

Import energy and key data from Mixed In Key tags embedded in audio files:

```bash
vdj-manager analyze import-mik --local
```

MIK energy goes to `Tags/@Grouping`, MIK key to `Tags/@Key`.

## Desktop GUI

The **Analysis** tab provides 3 sub-tabs with real-time streaming results:

- **Energy**: Analyze tracks for energy levels
- **MIK Import**: Import Mixed In Key tags
- **Mood**: Multi-label mood classification with model selection

Features:
- **Windows-path support**: Databases with Windows paths (e.g., MyNVMe `D:\...`) are fully supported — cached results from previous runs are applied, and online mood lookup works for tracks with artist/title metadata
- **Local/remote breakdown**: Info labels show "X tracks (Y local, Z remote)" when the database contains Windows paths
- Format column showing file extension
- Color-coded status (green for success, red for errors)
- Sortable columns
- Pause/Resume/Cancel controls
- Persistent SQLite cache (`~/.vdj_manager/analysis.db`) avoids re-analyzing unchanged files
- **No "failed" status**: Mood analysis always produces a result — uses multi-tier fallback (online → primary model → fallback model → "unknown")
