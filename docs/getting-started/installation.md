# Installation

## Requirements

- Python 3.10 or higher
- ffmpeg (for audio normalization)
- macOS (primary platform)

## Install from PyPI

```bash
pip install vdj-manager
```

## Install from Source

```bash
git clone https://github.com/aguliani/vdj-manager.git
cd vdj-manager
pip install -e .
```

## Install with Optional Dependencies

### For Mood Analysis (Essentia)

```bash
pip install 'vdj-manager[mood]'
```

### For Serato Export

```bash
pip install 'vdj-manager[serato]'
```

### For Development

```bash
pip install 'vdj-manager[dev]'
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

## Verify VDJ Manager Installation

```bash
vdj-manager --version
vdj-manager --help
```

## Database Locations

VDJ Manager automatically detects VirtualDJ databases at these locations:

| Database | Path |
|----------|------|
| Local | `~/Library/Application Support/VirtualDJ/database.xml` |
| MyNVMe | `/Volumes/MyNVMe/VirtualDJ/database.xml` |

Backups are stored in `~/.vdj_manager/backups/`.
