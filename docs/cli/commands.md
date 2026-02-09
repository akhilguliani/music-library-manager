# CLI Commands Reference

## Global Options

```bash
vdj-manager --version    # Show version
vdj-manager --help       # Show help
```

## Database Commands (`db`)

### `db status`

Show library statistics.

```bash
vdj-manager db status [OPTIONS]

Options:
  --local       Use local database only
  --mynvme      Use MyNVMe database only
  --both        Show both databases (default)
  --check-files Check if files exist (slower)
```

**Example:**
```bash
vdj-manager db status --both --check-files
```

### `db backup`

Create a backup of the database.

```bash
vdj-manager db backup [OPTIONS]

Options:
  --local       Backup local database
  --mynvme      Backup MyNVMe database
  --both        Backup both (default)
  -l, --label   Optional label for backup
```

**Example:**
```bash
vdj-manager db backup --both -l "before_cleanup"
```

### `db validate`

Check file existence and validate entries.

```bash
vdj-manager db validate [OPTIONS]

Options:
  --local       Validate local database
  --mynvme      Validate MyNVMe database
  -v, --verbose Show detailed output
```

### `db clean`

Remove invalid entries from the database.

```bash
vdj-manager db clean [OPTIONS]

Options:
  --non-audio   Remove non-audio entries (zip, mp4, etc.)
  --missing     Remove entries with missing files
  --dry-run     Preview without making changes
  --local       Clean local database
  --mynvme      Clean MyNVMe database
```

**Example:**
```bash
# Preview cleanup
vdj-manager db clean --non-audio --missing --dry-run --local

# Execute cleanup
vdj-manager db clean --non-audio --missing --local
```

---

## File Commands (`files`)

### `files scan`

Preview new files in a directory.

```bash
vdj-manager files scan DIRECTORY [OPTIONS]

Options:
  --recursive/--no-recursive  Scan subdirectories (default: recursive)
```

### `files import`

Add new files to the database.

```bash
vdj-manager files import DIRECTORY [OPTIONS]

Options:
  --recursive/--no-recursive
  --dry-run     Preview without importing
  --local       Import to local database
  --mynvme      Import to MyNVMe database
```

### `files remove`

Remove entries from the database.

```bash
vdj-manager files remove [OPTIONS]

Options:
  --missing     Remove entries with missing files
  --dry-run     Preview without removing
  --local       Remove from local database
  --mynvme      Remove from MyNVMe database
```

### `files remap`

Remap Windows paths to macOS paths.

```bash
vdj-manager files remap [WINDOWS_PREFIX] [MAC_PREFIX] [OPTIONS]

Options:
  --detect      Show all Windows paths grouped by prefix
  --interactive Interactive mapping mode
  --apply       Apply configured mappings
  --dry-run     Preview remapping
  --local       Remap in local database
  --mynvme      Remap in MyNVMe database
```

**Examples:**
```bash
# Detect Windows paths
vdj-manager files remap --detect --mynvme

# Add custom mapping
vdj-manager files remap "D:/MyMusic/" "/Volumes/External/MyMusic/"

# Apply all mappings
vdj-manager files remap --apply --mynvme
```

### `files duplicates`

Find duplicate entries.

```bash
vdj-manager files duplicates [OPTIONS]

Options:
  --by-hash     Find exact duplicates by file hash (slow)
  --local       Check local database
  --mynvme      Check MyNVMe database
```

---

## Analysis Commands (`analyze`)

### `analyze energy`

Analyze tracks for energy levels.

```bash
vdj-manager analyze energy [OPTIONS]

Options:
  --all         Analyze all tracks
  --untagged    Only tracks without energy tags
  --dry-run     Preview without tagging
  --local       Use local database
  --mynvme      Use MyNVMe database
```

### `analyze mood`

Tag tracks with mood/emotion using multi-label classification. Supports MTG-Jamendo (56-class CNN) or heuristic backend, with online fallback via Last.fm/MusicBrainz.

```bash
vdj-manager analyze mood [OPTIONS]

Options:
  --all             Analyze all tracks
  --untagged        Only tracks without mood tags
  --update-unknown  Re-analyze tracks with #unknown mood
  --online/--no-online  Enable online mood lookup (default: on)
  --lastfm-key KEY  Last.fm API key (overrides env var)
  --model MODEL     Mood model: mtg-jamendo (default) or heuristic
  --threshold FLOAT Min confidence for mood tags (default: 0.1)
  --max-tags INT    Max mood tags per track (default: 5)
  --dry-run         Preview without tagging
  --local           Use local database
  --mynvme          Use MyNVMe database
```

**Examples:**
```bash
# Analyze all tracks with MTG-Jamendo (default)
vdj-manager analyze mood --all

# Use heuristic backend with lower threshold
vdj-manager analyze mood --all --model heuristic --threshold 0.05

# Re-analyze unknown tracks with online lookup
vdj-manager analyze mood --update-unknown --online
```

### `analyze import-mik`

Import existing Mixed In Key tags from audio files.

```bash
vdj-manager analyze import-mik [OPTIONS]

Options:
  --dry-run     Preview without importing
  --local       Use local database
  --mynvme      Use MyNVMe database
```

---

## Tag Commands (`tag`)

### `tag set`

Set a tag value manually.

```bash
vdj-manager tag set FILE_PATH TAG_TYPE VALUE [OPTIONS]

Arguments:
  FILE_PATH   Path to the file in database
  TAG_TYPE    Type: energy, mood, or key
  VALUE       Tag value

Options:
  --local     Use local database
  --mynvme    Use MyNVMe database
```

**Example:**
```bash
vdj-manager tag set "/path/to/track.mp3" energy 7
```

---

## Normalize Commands (`normalize`)

### `normalize measure`

Measure current loudness levels using parallel processing.

```bash
vdj-manager normalize measure [OPTIONS]

Options:
  --all                 Measure all tracks
  --export PATH         Export results to CSV
  -w, --workers INT     Number of parallel workers
  -n, --limit INT       Limit number of tracks
  --local               Use local database
  --mynvme              Use MyNVMe database
```

**Example:**
```bash
# Fast measurement with 8 workers
vdj-manager normalize measure --workers 8 --export results.csv
```

### `normalize apply`

Apply loudness normalization.

```bash
vdj-manager normalize apply [TARGET] [OPTIONS]

Arguments:
  TARGET      Target LUFS (default: -14.0)

Options:
  --destructive        Rewrite audio files
  --dry-run            Preview without changes
  -w, --workers INT    Number of parallel workers
  -n, --limit INT      Limit number of tracks
  --local              Use local database
  --mynvme             Use MyNVMe database
```

**Examples:**
```bash
# Non-destructive (adjust VDJ Volume field)
vdj-manager normalize apply -14 --workers 8

# Destructive (rewrite files)
vdj-manager normalize apply -14 --destructive
```

---

## Export Commands (`export`)

### `export serato`

Export library to Serato format.

```bash
vdj-manager export serato [OPTIONS]

Options:
  --all             Export entire library
  --playlist NAME   Export specific playlist
  --cues-only       Only export cue points/beatgrid
  --dry-run         Preview without exporting
  --local           Use local database
  --mynvme          Use MyNVMe database
```

**Examples:**
```bash
# Export all tracks
vdj-manager export serato --all

# Export specific playlist
vdj-manager export serato --playlist "Zoukland May"

# Preview only
vdj-manager export serato --all --dry-run
```
