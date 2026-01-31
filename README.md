# VDJ Manager

A Python CLI tool for managing VirtualDJ music libraries.

## Features

- **Organization** - Clean up invalid entries, remap Windows paths, detect duplicates
- **Energy/Mood Tagging** - AI-based analysis with manual override using the `Grouping` field
- **File Management** - Streamlined import/removal with validation
- **Audio Normalization** - LUFS-based loudness normalization using ffmpeg
- **Serato Export** - Export VDJ library to Serato format with cue points

## Installation

```bash
pip install vdj-manager
```

Or install from source:

```bash
pip install -e .
```

## Usage

```bash
# Database operations
vdj-manager db status                    # Show library statistics
vdj-manager db validate                  # Check file existence
vdj-manager db clean --non-audio         # Remove zip/mp4 entries
vdj-manager db backup                    # Create manual backup

# File management
vdj-manager files scan ~/Music/New       # Preview new files
vdj-manager files import ~/Music/New     # Add to database
vdj-manager files remap --detect         # Show Windows paths
vdj-manager files duplicates             # Find duplicates

# Analysis
vdj-manager analyze energy --untagged    # Analyze untagged tracks
vdj-manager tag set <file> energy 7      # Manual override

# Normalization
vdj-manager normalize measure --all      # Show current loudness
vdj-manager normalize apply -14          # Apply -14 LUFS target

# Serato Export
vdj-manager export serato --all          # Export entire library
vdj-manager export serato --playlist "My Playlist"
```

## Requirements

- Python 3.10+
- ffmpeg (for normalization)
