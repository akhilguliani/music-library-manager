# VDJ Manager

**A powerful Python CLI tool for managing VirtualDJ music libraries**

VDJ Manager helps DJs organize, analyze, and normalize their music libraries. It provides a comprehensive set of tools for:

- **Database Management** - Clean up invalid entries, remap Windows paths to macOS, detect duplicates
- **Audio Analysis** - AI-based energy level detection, Mixed In Key tag import
- **Loudness Normalization** - LUFS-based normalization with parallel processing
- **Cross-Platform Support** - Export to Serato DJ with cue points and metadata

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
- Store results in VDJ's Grouping field

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

# Export to Serato
vdj-manager export serato --all
```

## System Requirements

- **Python** 3.10 or higher
- **ffmpeg** for audio normalization
- **macOS** (primary platform, Windows support planned)

## Getting Started

Check out the [Installation Guide](getting-started/installation.md) to get started.
