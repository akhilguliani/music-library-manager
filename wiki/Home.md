# VDJ Manager

**A powerful Python tool for managing VirtualDJ music libraries with CLI and desktop GUI interfaces**

VDJ Manager helps DJs organize, analyze, and normalize their music libraries. It provides a comprehensive set of tools for:

- **Database Management** - Clean up invalid entries, remap Windows paths to macOS, detect duplicates
- **Audio Analysis** - AI-based energy level detection, Mixed In Key tag import, multi-label mood classification (56 mood classes)
- **Online Mood Enrichment** - Last.fm / MusicBrainz tag lookup with local model fallback and exponential backoff retry
- **Audio Playback** - VLC-based player with waveform display, editable cue points, queue, and star ratings
- **Loudness Normalization** - LUFS-based normalization with parallel processing
- **Serato Export** - Export cue points, beatgrid, and metadata to Serato DJ
- **Desktop GUI** - Visual interface with real-time streaming results, progress tracking, and pause/resume
- **Structured Logging** - Rotating log files with `--verbose` CLI flag for troubleshooting
- **Persistent Caching** - SQLite caches for measurements, analysis results, and waveform data across sessions
- **Windows-Path Support** - Databases with Windows paths (e.g., `D:\...`) are fully supported for analysis and online mood lookup

## Features

### Database Operations
- View library statistics across multiple databases
- Validate file existence and detect missing entries
- Remove non-audio files (zip, mp4, etc.)
- Create timestamped backups before any changes

### Path Remapping
- Automatically detect Windows paths (C:/, D:/, E:/)
- Interactive mapping mode for custom path conversions
- Batch remapping with existence verification

### Audio Analysis
- Import existing Mixed In Key tags from audio files
- Calculate energy levels (1-10 scale) using audio features
- Multi-label mood classification with MTG-Jamendo (56-class CNN) or heuristic model
- Online mood enrichment via Last.fm and MusicBrainz with retry and backoff
- Store results in VDJ's Grouping and User2 fields

### Desktop GUI
- **6 tabs**: Database, Normalization, Files, Analysis, Export, Player
- Database browser with virtual scrolling (18k+ tracks)
- Real-time streaming results for energy, mood, and MIK analysis
- Audio playback with waveform, editable cue points, queue, and star ratings
- Pause/Resume long operations with automatic checkpointing
- Persistent SQLite caching avoids redundant analysis

See the [Desktop Application](Desktop-Application) page for full details.

### Loudness Normalization
- Measure LUFS loudness using ffmpeg
- Parallel processing for fast batch measurement
- Non-destructive mode (adjust VDJ Volume field)
- Destructive mode (rewrite audio files)

### Serato Export
- Export cue points and beatgrid to Serato format
- Create Serato crates from VDJ playlists
- Write metadata to audio file tags

## Quick Example

```bash
# Check your library status
vdj-manager db status --both

# Clean up non-audio files
vdj-manager db clean --non-audio --local

# Remap Windows paths
vdj-manager files remap --detect --mynvme
vdj-manager files remap --apply --mynvme

# Measure loudness (parallel processing)
vdj-manager normalize measure --workers 8 --export loudness.csv

# Analyze mood with AI
vdj-manager analyze mood --all

# Export to Serato
vdj-manager export serato --all

# Launch the desktop GUI
vdj-manager-gui
```

## System Requirements

- **Python** 3.10 or higher
- **ffmpeg** for audio normalization
- **macOS** (primary platform; handles Windows-path databases from external drives)

## Getting Started

Check out the [Installation](Installation) guide to get started.
