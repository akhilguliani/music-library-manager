# File Management

VDJ Manager provides tools for managing files in your VirtualDJ library.

## CLI Commands

### Scan

Preview audio files in a directory:

```bash
vdj-manager files scan /path/to/music
```

### Import

Add new files to the VDJ database:

```bash
vdj-manager files import /path/to/music --dry-run  # Preview
vdj-manager files import /path/to/music             # Import
```

### Remove

Remove entries for missing or invalid files:

```bash
vdj-manager files remove --missing --dry-run  # Preview
vdj-manager files remove --missing             # Remove
```

### Path Remapping

Convert Windows paths to macOS paths:

```bash
vdj-manager files remap --detect --mynvme     # Detect remappable paths
vdj-manager files remap --apply --mynvme      # Apply remapping
vdj-manager files remap --interactive         # Interactive mode
```

### Duplicate Detection

Find duplicate entries:

```bash
vdj-manager files duplicates                  # By filename
vdj-manager files duplicates --by-hash        # By file content hash
```

## Desktop GUI

The **Files** tab provides 5 sub-tabs:

- **Scan**: Preview audio files in a directory before importing
- **Import**: Add new files to the VDJ database
- **Remove**: Remove missing or invalid entries
- **Remap**: Convert Windows paths to macOS paths with prefix detection
- **Duplicates**: Find duplicate entries by filename, metadata, or file hash

All file operations that modify the database create an automatic backup first.
