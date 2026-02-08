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
pytest tests/ -v                    # Run all tests (477 tests)
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
    │   ├── base_worker.py         # PausableWorker, SimpleWorker, ProgressSimpleWorker
    │   ├── normalization_worker.py # Measure & apply loudness normalization
    │   ├── database_worker.py     # Load, backup, validate, clean workers
    │   ├── file_workers.py        # Scan, import, remove, remap, duplicate workers
    │   ├── analysis_workers.py    # Energy, mood, MIK import workers
    │   └── export_workers.py      # Serato export & crate workers
    ├── state/          # Checkpoint persistence for task recovery
    └── widgets/        # Qt widgets
        ├── database_panel.py      # DB load, stats, track browser, tag editing, operation log
        ├── normalization_panel.py # Measure, apply, CSV export, limit
        ├── files_panel.py         # 5 sub-tabs: scan, import, remove, remap, duplicates
        ├── analysis_panel.py      # 3 sub-tabs: energy, MIK import, mood
        └── export_panel.py        # Serato export, playlist/crate browser
```

### Key Patterns

**VDJ Database Format:**
- XML with lxml parsing; BPM stored as seconds-per-beat (0.5 = 120 BPM)
- Energy stored in `Tags/@Grouping` as plain number (e.g., "7"); parser also handles legacy "Energy 7" format
- Mood stored in `Tags/@User2` as hashtags (e.g., "#happy")
- MIK key imported to `Tags/@Key`, MIK energy to `Tags/@Grouping`
- Use lxml's default output format (single quotes in XML declaration, LF line endings)
- `_filepath_to_elem` dict provides O(1) XML element lookups (built during `load()`)

**Pydantic Models:**
- Use `alias` for XML attribute names, `populate_by_name=True`
- `computed_field` for derived values like `energy_level`

**GUI Architecture (5 tabs):**
- Database(0), Normalization(1), Files(2), Analysis(3), Export(4)
- `PausableWorker` for long operations with pause/resume (QMutex/QWaitCondition)
- `SimpleWorker`/`ProgressSimpleWorker` for quick operations (backup, clean, analysis)
- Analysis workers stream results via `result_ready = Signal(dict)` for real-time GUI updates
- Checkpoint system saves state at batch boundaries for task recovery
- All destructive operations auto-backup the database first
- Qt signals require event loop pumping in tests: `QCoreApplication.processEvents()`

## Configuration Paths

```
~/.vdj_manager/
├── backups/            # Timestamped database backups
├── checkpoints/        # JSON task checkpoints for pause/resume
├── measurements.db     # SQLite cache for loudness measurements
└── analysis.db         # SQLite cache for energy/mood/MIK results

~/Library/Application Support/VirtualDJ/database.xml  # Primary database (macOS)
/Volumes/MyNVMe/VirtualDJ/database.xml                # Secondary database (external drive)
```

## Testing Notes

- `tests/conftest.py` has shared fixtures: `pytest_configure` (sets `multiprocessing.set_start_method("spawn")` on macOS) and `_qt_cleanup` (autouse fixture running `processEvents()` + `gc.collect()` after each test)
- Module-scoped `qapp` fixture in individual test files for Qt tests
- Qt tests need explicit event loop pumping between signal emissions
- Analysis workers stream results — tests must simulate streaming via `result_ready` before calling `_on_*_finished`
- Workers with lazy imports need patching at the source module (e.g., `vdj_manager.analysis.energy.EnergyAnalyzer`)
- ProcessPoolExecutor tests: patch with ThreadPoolExecutor so mocks are visible in same process
- Each bug fix should have a corresponding test case
