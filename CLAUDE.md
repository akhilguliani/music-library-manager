# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VDJ Manager is a CLI and desktop GUI application for managing VirtualDJ music libraries. It handles database operations, file management, audio analysis, loudness normalization, and format conversion (e.g., Serato export).

## Build & Development Commands

```bash
# Installation
pip install -e .                    # Standard install
pip install -e '.[dev]'             # With dev dependencies (pytest, black, ruff, mypy)
pip install -e '.[mood]'            # Optional: AI mood analysis (essentia-tensorflow)
pip install -e '.[serato]'          # Optional: Serato export support

# Testing
pytest tests/ -v                    # Run all tests (240 tests)
pytest tests/ -k "pattern"          # Run tests matching pattern
pytest tests/ --cov=src/vdj_manager # With coverage

# Linting & Formatting
black src/ tests/                   # Format (100-char line length)
ruff check src/ tests/              # Lint
mypy src/                           # Type check (strict mode)

# Documentation
mkdocs serve                        # Local preview at http://127.0.0.1:8000
mkdocs build                        # Build static site
```

## Architecture

### Entry Points
- **CLI:** `vdj-manager` → `src/vdj_manager/cli.py:cli()` (Click-based)
- **GUI:** `vdj-manager-gui` → `src/vdj_manager/ui/app.py:main()` (PySide6/Qt)

### Module Structure
```
vdj_manager/
├── cli.py              # Click CLI with command groups: db, files, analyze, normalize, tag, export
├── config.py           # Configuration, paths, constants
├── core/               # VDJ database operations
│   ├── database.py     # VDJDatabase - lxml-based XML parser/writer
│   ├── models.py       # Pydantic models (Song, Tags, Infos, Scan, Poi)
│   └── backup.py       # Backup management
├── files/              # File operations (scanner, validator, path_remapper, duplicates)
├── analysis/           # Audio analysis (energy classification, mood detection)
├── normalize/          # LUFS loudness normalization via ffmpeg
├── export/             # Serato format conversion
└── ui/                 # PySide6 desktop application
    ├── workers/        # QThread-based workers with pause/resume
    ├── state/          # Checkpoint persistence for task recovery
    └── widgets/        # Qt widgets for database browsing, normalization
```

### Key Patterns

**VDJ Database Format:**
- XML with lxml parsing; BPM stored as seconds-per-beat (0.5 = 120 BPM)
- Energy stored in `Tags/@Grouping` (e.g., "Energy 7")
- Use lxml's default output format (single quotes in XML declaration, LF line endings)
- `_filepath_to_elem` dict provides O(1) XML element lookups (built during `load()`)

**Pydantic Models:**
- Use `alias` for XML attribute names, `populate_by_name=True`
- `computed_field` for derived values like `energy_level`

**GUI Threading:**
- `PausableWorker` base class provides pause/resume with QMutex/QWaitCondition
- Checkpoint system saves state at batch boundaries for task recovery
- Qt signals require event loop pumping in tests: `QCoreApplication.processEvents()`

## Configuration Paths

```
~/.vdj_manager/
├── backups/            # Timestamped database backups
└── checkpoints/        # JSON task checkpoints for pause/resume

~/Library/Application Support/VirtualDJ/database.xml  # Primary database (macOS)
/Volumes/MyNVMe/VirtualDJ/database.xml                # Secondary database (external drive)
```

## Testing Notes

- No conftest.py — fixtures are defined per test file
- Qt tests need explicit event loop pumping between signal emissions
- Performance fix tests in `tests/test_performance_fixes.py`
- Each bug fix should have a corresponding test case
