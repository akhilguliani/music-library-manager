# VDJ Manager

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-806%20passed-brightgreen.svg)]()

A powerful Python tool for managing VirtualDJ music libraries, with both CLI and desktop GUI interfaces.

## Features

- **Database Management** - Clean up invalid entries, validate files, create backups
- **Path Remapping** - Convert Windows paths (D:/, E:/) to macOS paths
- **Duplicate Detection** - Find duplicates by filename, metadata, or file hash
- **Audio Analysis** - Import Mixed In Key tags, calculate energy levels (1-10), AI mood classification
- **Online Mood Enrichment** - Last.fm / MusicBrainz tag lookup with local model fallback
- **Loudness Normalization** - LUFS-based normalization with parallel processing
- **Serato Export** - Export cue points, beatgrid, and metadata to Serato DJ
- **Audio Playback** - VLC-based player with waveform display, cue points, queue, and star ratings
- **Desktop GUI** - Visual interface with real-time streaming results, progress tracking, and pause/resume
- **Structured Logging** - Rotating log files at `~/.vdj_manager/logs/` with `--verbose` flag
- **Persistent Caching** - SQLite caches for measurements, analysis results, and waveform data across sessions
- **Windows-Path Support** - Databases with Windows paths fully supported for analysis and online mood lookup
- **Retry with Backoff** - Online lookups automatically retry on network errors with exponential backoff

## Installation

```bash
# Install from source
git clone https://github.com/akhilguliani/music-library-manager.git
cd music-library-manager
pip install -e .

# With optional dependencies
pip install -e '.[mood]'            # AI mood analysis (essentia-tensorflow)
pip install -e '.[player]'         # Audio playback (python-vlc)
pip install -e '.[online]'         # Online mood lookup (pylast, musicbrainzngs)
pip install -e '.[serato]'         # Serato export (mutagen)

# Verify installation
vdj-manager --version

# Launch desktop GUI
vdj-manager-gui
```

### Requirements

- Python 3.10+
- ffmpeg (for normalization)

```bash
# macOS
brew install ffmpeg
```

## Quick Start

```bash
# Check library status
vdj-manager db status --both

# Create backup
vdj-manager db backup --both

# Clean up non-audio files
vdj-manager db clean --non-audio --local

# Remap Windows paths
vdj-manager files remap --detect --mynvme
vdj-manager files remap --apply --mynvme

# Import Mixed In Key tags
vdj-manager analyze import-mik --local

# Measure loudness (parallel)
vdj-manager normalize measure --workers 8 --export loudness.csv

# Export to Serato
vdj-manager export serato --all
```

## CLI Commands

### Database Operations

```bash
vdj-manager db status [--local|--mynvme|--both] [--check-files]
vdj-manager db backup [--local|--mynvme|--both] [-l LABEL]
vdj-manager db validate [--local|--mynvme] [-v]
vdj-manager db clean [--non-audio] [--missing] [--dry-run]
```

### File Management

```bash
vdj-manager files scan DIRECTORY
vdj-manager files import DIRECTORY [--dry-run]
vdj-manager files remove --missing [--dry-run]
vdj-manager files remap [--detect|--interactive|--apply]
vdj-manager files duplicates [--by-hash]
```

### Audio Analysis

```bash
vdj-manager analyze energy [--all|--untagged]
vdj-manager analyze mood [--all]
vdj-manager analyze import-mik
vdj-manager tag set <file> <type> <value>
```

### Normalization

```bash
vdj-manager normalize measure [-w WORKERS] [-n LIMIT] [--export CSV]
vdj-manager normalize apply TARGET [--destructive] [-w WORKERS]
```

### Export

```bash
vdj-manager export serato [--all|--playlist NAME] [--cues-only]
```

## Desktop Application

For a visual interface with progress tracking and pause/resume support:

```bash
vdj-manager-gui
```

Features:
- **6 tabs**: Database, Normalization, Files, Analysis, Export, Player
- Database browser with virtual scrolling (18k+ tracks)
- Real-time streaming results for energy, mood, and MIK analysis
- Audio playback with waveform, editable cue points, queue, and star ratings
- Pause/Resume long operations with automatic checkpointing
- Persistent SQLite caching avoids redundant analysis

## Database Locations

| Database | Path |
|----------|------|
| Local | `~/Library/Application Support/VirtualDJ/database.xml` |
| MyNVMe | `/Volumes/MyNVMe/VirtualDJ/database.xml` |
| Backups | `~/.vdj_manager/backups/` |
| Measurement Cache | `~/.vdj_manager/measurements.db` |
| Analysis Cache | `~/.vdj_manager/analysis.db` |
| Waveform Cache | `~/.vdj_manager/waveforms.db` |
| Log Files | `~/.vdj_manager/logs/vdj_manager.log` |

## How It Works

### VDJ Database Format

VirtualDJ stores library data in XML:

```xml
<Song FilePath="/path/to/track.mp3" FileSize="5000000">
  <Tags Author="Artist" Title="Track" Grouping="7" User2="#happy" />
  <Infos SongLength="180.5" Bitrate="320" />
  <Scan Bpm="0.5" Key="Am" Volume="1.0" />
  <Poi Type="cue" Pos="30.0" Num="1" Name="Drop" />
</Song>
```

**BPM Note:** VDJ stores BPM as seconds per beat (e.g., `0.5` = 120 BPM).

### Tag Storage

| Tag | VDJ Field | Format | Example |
|-----|-----------|--------|---------|
| Energy | `Tags/@Grouping` | Plain number (1-10) | `"7"` |
| Mood | `Tags/@User2` | Hashtags | `"#happy"` |
| Key | `Tags/@Key` (via MIK import) | Musical key | `"Am"` |

- Energy calculated from tempo, RMS energy, and spectral centroid
- Mood classified via AI (Essentia-TensorFlow)
- Key and energy can be imported from Mixed In Key tags

### Normalization

- **Target:** -14 LUFS (streaming standard)
- **Non-destructive:** Adjusts VDJ's `Volume` field
- **Destructive:** Rewrites audio files with ffmpeg
- **Parallel processing:** Uses multiple CPU cores for speed

### Serato Export

- Converts VDJ cue points to Serato hotcues
- Creates `.crate` files for playlists
- Writes metadata to audio file tags (GEOB for MP3)

## Project Structure

```
vdj_manager/
├── cli.py              # Click-based CLI
├── config.py           # Configuration
├── core/
│   ├── database.py     # VDJ XML parser/writer
│   ├── models.py       # Pydantic data models
│   └── backup.py       # Backup management
├── analysis/
│   ├── audio_features.py  # librosa + MIK reader
│   ├── energy.py       # Energy classification
│   ├── mood_backend.py # Mood model protocol + factory
│   ├── mood_mtg_jamendo.py # MTG-Jamendo 56-class CNN
│   └── online_mood.py  # Last.fm / MusicBrainz lookup
├── files/
│   ├── validator.py    # File validation
│   ├── scanner.py      # Directory scanning
│   ├── path_remapper.py # Windows path conversion
│   └── duplicates.py   # Duplicate detection
├── normalize/
│   ├── loudness.py     # LUFS measurement
│   └── processor.py    # Parallel normalization
├── export/
│   ├── serato.py       # Serato crate/tag writer
│   └── mapper.py       # VDJ→Serato mapping
├── player/             # Audio playback (VLC)
│   ├── engine.py       # UI-agnostic playback engine
│   ├── bridge.py       # Qt signal bridge
│   ├── waveform.py     # Waveform peak generation
│   └── album_art.py    # Album art extraction
└── ui/                 # Desktop GUI (PySide6)
    ├── app.py          # Application entry point
    ├── main_window.py  # Main window
    ├── widgets/        # UI components
    ├── workers/        # Background processing
    └── state/          # Checkpoint management
```

## Development

```bash
# Install dev dependencies
pip install -e '.[dev]'

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/vdj_manager
```

### Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/test_database.py

# With verbose output
pytest -v
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [VirtualDJ](https://www.virtualdj.com/) for the amazing DJ software
- [librosa](https://librosa.org/) for audio analysis
- [Click](https://click.palletsprojects.com/) for CLI framework
- [Rich](https://rich.readthedocs.io/) for beautiful terminal output
