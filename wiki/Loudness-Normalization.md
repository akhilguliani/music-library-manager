# Loudness Normalization

VDJ Manager provides LUFS-based loudness normalization with parallel processing.

## Measuring Loudness

```bash
vdj-manager normalize measure --workers 8 --export loudness.csv
vdj-manager normalize measure -n 100       # Limit to 100 tracks
```

Measurements are cached in `~/.vdj_manager/measurements.db` (SQLite) to avoid redundant ffmpeg runs.

## Applying Normalization

### Non-Destructive (Default)

Adjusts VirtualDJ's `Volume` field without modifying audio files:

```bash
vdj-manager normalize apply -14            # Target -14 LUFS
```

### Destructive

Rewrites audio files with ffmpeg:

```bash
vdj-manager normalize apply -14 --destructive --workers 4
```

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Target LUFS | -14.0 | Streaming standard loudness |
| Workers | CPU count - 1 | Parallel processing threads |

## Desktop GUI

The **Normalization** tab in the [Desktop Application](Desktop-Application) offers:

- **LUFS Measurement**: Measure loudness of your entire library
- **Configurable Target**: Set target LUFS (default: -14.0)
- **Batch Processing**: Adjustable batch size for checkpoint frequency
- **Progress Display**: Real-time progress bar with percentage
- **Pause/Resume**: Pause long operations and resume later (even after app restart)
- **Results Table**: View LUFS values and gain adjustments per track
- **CSV Export**: Export measurement results

## Requirements

ffmpeg must be installed:

```bash
# macOS
brew install ffmpeg
```

See [CLI Commands](CLI-Commands) for the full command reference.
