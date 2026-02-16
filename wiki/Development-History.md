# Development History

This document captures the development history of VDJ Manager, including prompts used, design decisions, bugs encountered, and lessons learned.

## Project Overview

**VDJ Manager** is a Python tool for managing VirtualDJ music libraries with both CLI and desktop GUI interfaces. The desktop UI was added to provide real-time progress visualization and pause/resume capability for long-running operations.

## Development Timeline

### Phase 1: Core CLI Development (Initial)

The initial CLI was built with:
- Click-based command structure
- lxml for XML parsing/writing
- Pydantic models for data validation
- Rich for terminal output

### Phase 2: Desktop UI Implementation (January 2026)

#### Initial Prompt

The desktop UI was implemented based on this detailed plan:

```
Implement the following plan:

# VDJ Manager Desktop UI Implementation Plan

## Overview
Add a desktop GUI to VDJ Manager using PySide6 (Qt for Python) with:
- Real-time progress visualization for long operations
- Pause/Resume capability for long-running tasks
- Database browsing and status display
- Integration with existing CLI backend

## Requirements Summary
| Requirement | Solution |
|-------------|----------|
| Desktop UI | PySide6 (Qt6) - LGPL licensed, native look, signals/slots |
| Progress display | QProgressBar + QTableView for real-time updates |
| Pause/Resume | Batch-based checkpointing with JSON state persistence |
| 18k tracks | QAbstractTableModel with virtual scrolling |
| Version control | Commits per implementation step with unit tests |
| Documentation | Update MkDocs with UI guide |
```

#### Architecture Decision: PySide6 vs Alternatives

**Chosen: PySide6 (Qt for Python)**

Reasons:
- LGPL license (vs PyQt's GPL)
- Native look and feel on all platforms
- Robust signals/slots mechanism for thread-safe UI updates
- QAbstractTableModel supports virtual scrolling for large datasets
- Well-documented, mature framework

Alternatives considered:
- **Tkinter**: Too basic for complex progress tracking
- **PyQt6**: GPL license complications
- **wxPython**: Less modern, smaller community
- **Kivy**: Better for touch/mobile, overkill for desktop

#### Architecture Decision: Pause/Resume Strategy

**Chosen: Checkpoint-based batch processing**

```
┌─────────────────────────────────────────────────────────────┐
│                    MainWindow (QMainWindow)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ DatabaseTab │  │NormalizeTab │  │    AnalysisTab      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  TaskController   │
                    │ - Manages workers │
                    │ - Checkpoints     │
                    └─────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────┴────┐  ┌──────┴──────┐  ┌─────┴─────┐
    │ NormWorker   │  │AnalysisWorker│ │ DBWorker  │
    │ (QThread)    │  │ (QThread)    │ │(QThread)  │
    └──────────────┘  └──────────────┘  └───────────┘
```

**How it works:**
1. Process files in configurable batches (default: 50)
2. After each batch, save state to `~/.vdj_manager/checkpoints/`
3. On pause: wait for current batch, save checkpoint
4. On resume: load checkpoint, continue from pending items

#### Implementation Steps (9 Commits)

Each step was implemented with corresponding unit tests:

1. **UI Infrastructure** - QApplication setup, entry point
2. **Task State & Checkpointing** - TaskState dataclass, CheckpointManager
3. **Base Worker** - PausableWorker with QThread, signals/slots
4. **Database Panel** - Track table with virtual scrolling
5. **Progress Widget** - Progress bar, pause/resume buttons
6. **Normalization Worker** - Parallel processing with checkpoints
7. **Normalization Panel** - Full workflow integration
8. **Resume Dialog** - Startup dialog for incomplete tasks
9. **Documentation** - MkDocs user guide

## Bugs Encountered and Fixes

### Bug #1: VDJ Database Corruption (Investigation & Correction)

**Initial Symptoms:**
- VirtualDJ reported database as "corrupted" after CLI operations

**Key Lesson Learned:**
**ALWAYS examine actual working files before assuming format requirements!**

We initially assumed VDJ needed double quotes and CRLF, but examining actual VDJ-created files showed lxml's default output was perfectly acceptable.

### Bug #2: Backup Sorting by Wrong Timestamp

**Root Cause:** `shutil.copy2` preserves source file's modification time.
**Fix:** Call `touch()` after copy to update mtime.

### Bug #3: QThread.wait() Keyword Argument

PySide6's `QThread.wait()` doesn't accept keyword arguments, only positional.

### Bug #4: Qt Signals Not Received in Tests

Qt signals are processed in the event loop. Tests need explicit event loop pumping via `processEvents()`.

### Bug #5: Checkpoint Cleanup Test Failure

`CheckpointManager.save()` was always updating `updated_at`, breaking age-based cleanup logic.

### Bug #6: Flaky Qt Segfaults in Full Test Suite

**Root Cause:** macOS `fork()` after Qt threads + cross-test Qt state pollution.
**Fix:** `set_start_method("spawn")` on macOS + autouse `_qt_cleanup` fixture.

## Phase Summary

### Phase 3: Performance Review & Optimization (February 2026)

7 performance fixes across database, path remapper, duplicates, loudness, and validator modules. Key improvements:
- O(1) XML element lookups via `_filepath_to_elem` index
- O(n) merge (was O(n^2))
- Cached sorted prefixes in PathRemapper
- ffmpeg verification cache

39 new tests. Test count: **240 tests passing**

### Phase 4: Full GUI Completion (February 2026)

All 17 CLI commands with GUI equivalents across 5 tabs: Database, Normalization, Files (5 sub-tabs), Analysis (3 sub-tabs), Export.

### Phase 5: Analysis Streaming, Caching & Format Fixes (February 2026)

- SQLite caches (MeasurementCache, AnalysisCache)
- Real-time streaming results via `result_ready` signal
- Tag storage format changes (energy as plain number, mood as hashtags)
- Apostrophe and self-closing tag preservation

### Phase 6: GUI Readability & Results Visibility (February 2026)

- Color-coded status, format column, sortable results table
- Compact database panel layout
- Test count: **477 tests passing**

### Phase 7: Audio Player & Online Mood (February 2026)

- 3-layer player architecture (PlaybackEngine -> PlaybackBridge -> UI)
- Waveform display, editable cue points, star ratings, queue, speed control
- Mini player bar, album art extraction
- Online mood enrichment via Last.fm/MusicBrainz
- Structured logging with rotating file handler
- Test count: **767 tests passing**

### Phase 8: Robustness & Windows-Path Support (February 2026)

- Retry with exponential backoff for online lookups
- Multi-tier mood fallback (never returns "failed")
- Windows-path tracks included in all analysis types
- Test count: **806 tests passing**

### Phase 9: Code Review Fixes — Security, Performance & Quality (February 2026)

Comprehensive code review across all commits. 7 fix commits covering:

- **Security**: XXE protection in XML parser, model download hash verification, Serato crate name sanitization
- **Performance**: Batch SQLite queries in cache `get_batch()`, process-level caching in analysis workers, vectorized waveform peaks, debounced analysis saves
- **Code quality**: File worker thread safety (signal-based mutations), save failure notification, exception logging in analysis modules

34 new tests. Test count: **838 tests passing**

## Lessons Learned

1. **Examine actual working files before fixing format issues** - Always `xxd` or hex-dump working files first
2. **Test with real consumer software** - Unit tests passing doesn't mean the software works
3. **Don't over-engineer** - The simplest solution is often correct
4. **File metadata preservation is tricky** - `shutil.copy2` preserving mtime caused sorting issues
5. **Qt testing requires event loop awareness** - Signals won't be received without processing events
6. **Batch boundaries are natural pause points** - Design for interruptibility from the start
7. **Checkpoint early, checkpoint often** - JSON checkpoints provide crash recovery for free
8. **Separate bugfix commits** - Each bug fix should have its own commit with a test case
9. **When a fix doesn't work, question the hypothesis**
10. **Build indexes during parsing** - Build both model and element maps in a single parse pass
11. **Cache derived data, invalidate on mutation**
12. **Profile before optimizing** - O(n^2) merge was the most impactful but not obvious without reading code
13. **0 is not None** - Using `0` as default for measurements where `0` is valid silently hides errors
14. **On macOS, use `spawn` not `fork` with Qt** - `fork()` after Qt threads causes segfaults
15. **Clean up Qt state between tests** - Autouse fixture with `processEvents()` + `gc.collect()`
16. **Stream results, don't batch them** - Per-file signals give users immediate feedback

## Future Improvements

1. **Batch Editing** - Select multiple tracks, edit tags in bulk
2. **Cloud Backup** - Optional backup to cloud storage
3. **Diff View** - Show changes before saving database
4. **Smart Playlists** - Auto-generate playlists by energy/mood/key
