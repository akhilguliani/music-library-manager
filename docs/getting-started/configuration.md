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

## Energy Analysis Weights

Energy level calculation uses weighted audio features:

```python
ENERGY_WEIGHTS = {
    "tempo": 0.35,      # BPM contribution
    "rms": 0.35,        # Loudness contribution
    "spectral": 0.30,   # Brightness contribution
}
```
