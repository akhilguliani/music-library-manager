# Configuration

VDJ Manager uses sensible defaults but can be configured for your setup.

## Database Paths

Default database locations:

| Database | Default Path |
|----------|--------------|
| Local | `~/Library/Application Support/VirtualDJ/database.xml` |
| MyNVMe | `/Volumes/MyNVMe/VirtualDJ/database.xml` |

Most commands accept `--local` or `--mynvme` flags to select which database to use.

## Backup Directory

Backups are stored in `~/.vdj_manager/backups/`.

## Path Mappings

Default Windows-to-macOS path mappings:

```python
DEFAULT_PATH_MAPPINGS = {
    "D:/Main/": "/Volumes/MyNVMe/Main/",
    "D:/NewMusic/": "/Volumes/MyNVMe/NewMusic/",
    "D:/deezer/": "/Volumes/MyNVMe/deezer/",
    "D:/All December 2022/": "/Volumes/MyNVMe/All December 2022/",
    "D:/Zoukables/": "/Volumes/MyNVMe/Zoukables/",
    "E:/Main/": "/Volumes/MyNVMe/Main/",
    "E:/": "/Volumes/MyNVMe/",
}
```

Add custom mappings using the CLI:

```bash
vdj-manager files remap "D:/CustomFolder/" "/Volumes/MyNVMe/CustomFolder/"
```

## Audio Extensions

Files with these extensions are recognized as audio:

```
.mp3, .m4a, .aac, .flac, .wav, .aiff, .aif, .ogg, .opus, .wma, .alac
```

## Non-Audio Extensions

These extensions are flagged for cleanup:

```
.zip, .rar, .7z, .tar, .gz, .mp4, .mkv, .avi, .mov, .wmv,
.jpg, .jpeg, .png, .gif, .bmp, .pdf, .doc, .docx, .txt,
.exe, .dmg, .pkg, .app, .db, .xml, .json, .nfo
```

## Normalization Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Target LUFS | -14.0 | Streaming standard loudness |
| Workers | CPU count - 1 | Parallel processing threads |

Override via CLI:

```bash
vdj-manager normalize apply -16 --workers 4
```

## Persistent Caches

VDJ Manager uses SQLite caches to avoid redundant work across sessions:

| Cache | Location | Purpose |
|-------|----------|---------|
| Measurement Cache | `~/.vdj_manager/measurements.db` | LUFS loudness measurements |
| Analysis Cache | `~/.vdj_manager/analysis.db` | Energy, mood, MIK analysis results |

Both caches use file mtime + size for invalidation. If a file is modified, its cached results are automatically discarded.

## Tag Storage Format

| Tag | VDJ Field | Format | Example |
|-----|-----------|--------|---------|
| Energy | `Tags/@Grouping` | Plain number (1-10) | `"7"` |
| Mood | `Tags/@User2` | Hashtags | `"#happy"` |
| Key | `Tags/@Key` | Musical key notation | `"Am"` |

The energy parser also supports the legacy `"Energy 7"` format for backward compatibility with older databases.

## Last.fm API Key (Online Mood Enrichment)

To enable online mood lookup via Last.fm, set your API key:

```bash
# Option 1: Environment variable
export LASTFM_API_KEY=your_api_key_here

# Option 2: File (persists across sessions)
echo "your_api_key_here" > ~/.vdj_manager/lastfm_api_key
```

Get a free API key at [last.fm/api/account/create](https://www.last.fm/api/account/create).

Online mood uses a tiered lookup: Last.fm track tags -> Last.fm artist tags -> MusicBrainz genres -> local model fallback.

## Log Files

VDJ Manager writes structured logs to `~/.vdj_manager/logs/`:

| File | Size Limit | Backups |
|------|-----------|---------|
| `vdj_manager.log` | 5 MB | 3 rotated backups |

Enable verbose console output:

```bash
# CLI
vdj-manager --verbose db status

# GUI (via environment variable)
VDJ_VERBOSE=1 vdj-manager-gui
```

The file handler always captures DEBUG-level logs regardless of the verbose flag.

## Model Downloads

AI mood analysis models are auto-downloaded to `~/.vdj_manager/models/` on first use:

| Model | Size | Description |
|-------|------|-------------|
| MTG-Jamendo | ~80 MB | 56-class mood/theme CNN (recommended) |

Models are downloaded from Essentia's model repository and cached locally.

## Energy Analysis Weights

Energy level calculation uses weighted audio features:

```python
ENERGY_WEIGHTS = {
    "tempo": 0.35,      # BPM contribution
    "rms": 0.35,        # Loudness contribution
    "spectral": 0.30,   # Brightness contribution
}
```
