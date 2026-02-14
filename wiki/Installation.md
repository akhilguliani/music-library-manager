# Installation

## Requirements

- Python 3.10 or higher
- ffmpeg (for audio normalization)
- macOS (primary platform)

## Install from Source

```bash
git clone https://github.com/akhilguliani/music-library-manager.git
cd music-library-manager
pip install -e .
```

## Install with Optional Dependencies

```bash
# AI mood analysis (essentia-tensorflow) - MTG-Jamendo 56-class CNN
pip install -e '.[mood]'

# Audio playback (python-vlc) - requires VLC media player installed
pip install -e '.[player]'

# Online mood lookup (pylast, musicbrainzngs) - Last.fm/MusicBrainz enrichment
pip install -e '.[online]'

# Serato export (mutagen) - export cue points and metadata to Serato DJ
pip install -e '.[serato]'

# Development tools (pytest, black, ruff, mypy)
pip install -e '.[dev]'
```

## Installing ffmpeg

ffmpeg is required for audio normalization features.

### macOS (Homebrew)

```bash
brew install ffmpeg
```

### Verify Installation

```bash
ffmpeg -version
```

## Installing VLC (for Player)

VLC is required for audio playback. The player gracefully degrades when VLC is not found (controls are disabled but the rest of the app works normally).

```bash
# macOS
brew install vlc
```

## Verify VDJ Manager Installation

```bash
vdj-manager --version
vdj-manager --help

# Launch the desktop GUI
vdj-manager-gui
```

## Database Locations

VDJ Manager automatically detects VirtualDJ databases at these locations:

| Database | Path |
|----------|------|
| Local | `~/Library/Application Support/VirtualDJ/database.xml` |
| MyNVMe | `/Volumes/MyNVMe/VirtualDJ/database.xml` |

Backups are stored in `~/.vdj_manager/backups/`.
