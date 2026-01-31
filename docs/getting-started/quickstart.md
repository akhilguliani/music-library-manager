# Quick Start

This guide will help you get started with VDJ Manager in 5 minutes.

## Step 1: Check Your Library Status

First, see what's in your VirtualDJ databases:

```bash
vdj-manager db status --both
```

This shows:
- Total entries in each database
- File locations (local, external drives, Windows paths)
- Metadata statistics (energy tags, cue points)

## Step 2: Create a Backup

Always create a backup before making changes:

```bash
vdj-manager db backup --both
```

Backups are saved to `~/.vdj_manager/backups/` with timestamps.

## Step 3: Validate Your Library

Check for problems in your library:

```bash
vdj-manager db validate --local -v
```

This identifies:
- Missing files
- Non-audio entries (zip, mp4, etc.)
- Windows paths that need remapping

## Step 4: Clean Up

Remove problematic entries:

```bash
# Preview what would be removed
vdj-manager db clean --non-audio --missing --dry-run --local

# Actually remove them
vdj-manager db clean --non-audio --missing --local
```

## Step 5: Remap Windows Paths

If you have Windows paths from a previous setup:

```bash
# See what needs remapping
vdj-manager files remap --detect --mynvme

# Apply remappings
vdj-manager files remap --apply --mynvme
```

## Step 6: Import Mixed In Key Tags

If your files have MIK analysis:

```bash
vdj-manager analyze import-mik --local
```

## Step 7: Measure Loudness

Analyze your library's loudness levels:

```bash
# Quick measurement with parallel processing
vdj-manager normalize measure --workers 8 --limit 100

# Full library with CSV export
vdj-manager normalize measure --export loudness.csv
```

## Common Workflows

### Cleaning Up After Migration

```bash
# 1. Backup
vdj-manager db backup --both

# 2. Remove junk
vdj-manager db clean --non-audio --missing --local

# 3. Remap paths
vdj-manager files remap --detect --mynvme
vdj-manager files remap --apply --mynvme

# 4. Verify
vdj-manager db status --both
```

### Preparing for a Gig

```bash
# 1. Check for missing files
vdj-manager db validate --mynvme

# 2. Export to Serato (if using Serato as backup)
vdj-manager export serato --all --mynvme
```

### Normalizing New Music

```bash
# 1. Scan new folder
vdj-manager files scan ~/Music/NewDownloads

# 2. Import to database
vdj-manager files import ~/Music/NewDownloads

# 3. Measure and normalize
vdj-manager normalize measure --limit 50
vdj-manager normalize apply -14 --limit 50
```
