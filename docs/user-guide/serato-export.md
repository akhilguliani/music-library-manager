# Serato Export

VDJ Manager can export your VirtualDJ library to Serato DJ format.

## CLI Commands

```bash
vdj-manager export serato --all              # Export all tracks
vdj-manager export serato --playlist "My Set" # Export specific playlist
vdj-manager export serato --cues-only        # Export cue points only
```

## What Gets Exported

### Cue Points

VDJ cue points (`<Poi>` elements) are converted to Serato hotcues:
- Up to 8 cue points per track
- Color-coded (Red, Orange, Yellow, Green, Cyan, Blue, Purple, Magenta)
- Written as Serato Markers2 GEOB tags in MP3 files

### Metadata

- BPM (written to TBPM tag)
- Key (written to TKEY tag)
- Comments (written as TXXX frame)

### Crate Files

VDJ playlists are exported as Serato `.crate` files in `~/Music/_Serato_/Subcrates/`.

## Supported Formats

| Format | Cue Points | Metadata |
|--------|-----------|----------|
| MP3 | Yes (Serato Markers2 GEOB) | Yes (ID3 tags) |
| M4A/AAC | No | Yes (MP4 atoms) |
| FLAC | No | Yes (Vorbis comments) |

## Desktop GUI

The **Export** tab provides:

- **Serato Export**: Export cue points, beatgrid, and metadata
- **Playlist/Crate Browser**: Browse and select VDJ playlists for export as Serato crates
