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

**Why not thread interruption?**
- Abrupt interruption could corrupt results
- Batch boundaries provide clean save points
- Checkpoints survive application crashes

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
- Database file was empty (0 bytes) or truncated

**Initial (Incorrect) Hypothesis:**
We initially assumed VDJ required specific XML formatting different from lxml defaults:
- Double quotes instead of single quotes in XML declaration
- CRLF line endings instead of Unix LF

**Initial Fix (commit 34825db) - INCORRECT:**
Changed the save() method to convert single quotes to double quotes and LF to CRLF.

**What Actually Happened:**
After restoring from backup and examining working VDJ database files, we discovered:

| Aspect | What VDJ Actually Uses | What We Changed To |
|--------|------------------------|-------------------|
| XML Declaration | `<?xml version='1.0'...?>` (single quotes) | Double quotes (wrong!) |
| Line Endings | `\n` (Unix LF) | `\r\n` (CRLF - wrong!) |

The original lxml output was **correct**. Our "fix" actually broke things!

**Real Root Cause:**
The database corruption was likely caused by:
1. Application interruption during write operations
2. The "fix" itself may have caused issues

**Corrected Fix (commit 6b039d4):**

```python
def save(self, output_path: Optional[Path] = None) -> None:
    """Save the database to file.

    VDJ database format:
    - Single quotes in XML declaration (lxml default)
    - Unix line endings (LF)
    - UTF-8 encoding
    """
    if not self.is_loaded:
        raise RuntimeError("Database not loaded")

    path = output_path or self.db_path

    # Use lxml's tree.write() which produces format VDJ accepts
    self._tree.write(
        str(path),
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )
```

**Key Lesson Learned:**
**ALWAYS examine actual working files before assuming format requirements!**

We assumed VDJ needed a specific format based on speculation, but examining actual VDJ-created database files showed lxml's default output was perfectly acceptable. The lesson is:

1. **Before fixing**: Examine working examples of the target format
2. **Hex dump comparison**: Use `xxd` to compare byte-by-byte
3. **Don't over-engineer**: Sometimes the simplest solution (default lxml output) is correct
4. **Test with actual software**: Verify saved files work in VDJ, not just pass unit tests

---

### Bug #2: Backup Sorting by Wrong Timestamp

**Symptoms:**
- `get_latest_backup()` returned wrong backup
- Test `test_get_latest_backup` was flaky

**Root Cause:**
`shutil.copy2` preserves the source file's modification time. When creating multiple backups of the same file, all backups had identical mtimes.

**Fix (commit 7c374df):**

```python
def create_backup(self, db_path: Path, label: Optional[str] = None) -> Path:
    backup_path = self.backup_dir / backup_name
    shutil.copy2(db_path, backup_path)

    # Update mtime to current time so backups sort correctly
    backup_path.touch()

    return backup_path
```

**Test case added:**

```python
def test_backup_mtime_reflects_creation_time(self, temp_backup_dir, sample_db_file):
    mgr = BackupManager(backup_dir=temp_backup_dir)

    first_backup = mgr.create_backup(sample_db_file, label="first")
    first_mtime = first_backup.stat().st_mtime

    time.sleep(0.1)

    second_backup = mgr.create_backup(sample_db_file, label="second")
    second_mtime = second_backup.stat().st_mtime

    assert second_mtime > first_mtime
```

**Lesson learned:** `shutil.copy2` preserves metadata including mtime; use `touch()` or `shutil.copy` when creation time matters.

---

### Bug #3: QThread.wait() Keyword Argument

**Symptoms:**
- `TypeError: PySide6.QtCore.QThread.wait(): unsupported keyword 'timeout'`

**Root Cause:**
PySide6's `QThread.wait()` doesn't accept keyword arguments, only positional.

**Fix:**

```python
# Wrong
worker.wait(timeout=5000)

# Correct
worker.wait(5000)
```

**Lesson learned:** PySide6 API differs from PyQt6 in subtle ways; always test with actual PySide6.

---

### Bug #4: Qt Signals Not Received in Tests

**Symptoms:**
- Test assertions failed because signal lists were empty
- Signals were emitted but not processed

**Root Cause:**
Qt signals are processed in the event loop. Tests need to pump the event loop to receive signals.

**Fix:**

```python
def process_events_until(condition, timeout_ms=5000):
    """Process Qt events until condition is True or timeout."""
    from PySide6.QtCore import QCoreApplication, QElapsedTimer

    timer = QElapsedTimer()
    timer.start()

    while not condition() and timer.elapsed() < timeout_ms:
        QCoreApplication.processEvents()

    return condition()
```

**Usage in tests:**

```python
def test_worker_emits_progress(self):
    results = []
    worker.progress.connect(lambda *args: results.append(args))
    worker.start()

    # Wait for signals to be processed
    process_events_until(lambda: len(results) > 0)

    assert len(results) > 0
```

**Lesson learned:** Qt signal/slot tests require explicit event loop processing.

---

### Bug #5: Checkpoint Cleanup Test Failure

**Symptoms:**
- `test_cleanup_completed` failed intermittently
- Timestamps were being overwritten

**Root Cause:**
`CheckpointManager.save()` was always updating `updated_at`, which broke the cleanup logic that relied on `updated_at` for age calculation.

**Fix:**

```python
def save(self, task: TaskState, update_timestamp: bool = True) -> None:
    if update_timestamp:
        task.updated_at = datetime.now()
    # ... save to file
```

**Lesson learned:** Side effects in save operations can break time-based logic; make them explicit and optional.

## Design Decisions Summary

### 1. Threading Model

**Decision:** Use QThread with QMutex/QWaitCondition for pause/resume

**Rationale:**
- Qt's threading model integrates with signals/slots
- QWaitCondition allows clean pause without busy-waiting
- Worker can check pause state at batch boundaries

```python
class PausableWorker(QThread):
    def __init__(self):
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start unpaused
        self._cancel_requested = False

    def pause(self):
        self._pause_event.clear()
        self.status_changed.emit("paused")

    def resume(self):
        self._pause_event.set()
        self.status_changed.emit("running")

    def _wait_if_paused(self):
        self._pause_event.wait()
```

### 2. Data Model for Track Table

**Decision:** QAbstractTableModel with lazy loading

**Rationale:**
- 18k+ tracks would be slow with QStandardItemModel
- QAbstractTableModel only fetches visible rows
- Virtual scrolling keeps memory constant

```python
class TrackTableModel(QAbstractTableModel):
    def rowCount(self, parent=None):
        return len(self._songs)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        song = self._songs[index.row()]
        # Return data for visible cell only
```

### 3. Checkpoint File Format

**Decision:** JSON with human-readable structure

**Rationale:**
- Easy to inspect/debug manually
- Python's json module is fast enough
- Structure matches TaskState dataclass

```json
{
  "task_id": "abc123",
  "task_type": "normalize",
  "status": "paused",
  "total_items": 1000,
  "completed_paths": ["/path/to/file1.mp3", ...],
  "pending_paths": ["/path/to/file500.mp3", ...],
  "failed_paths": {"/path/to/bad.mp3": "Error message"},
  "results": [...],
  "created_at": "2026-01-30T10:00:00",
  "updated_at": "2026-01-30T10:30:00"
}
```

### 4. Error Recovery Strategy

**Decision:** Continue on individual file errors, aggregate at end

**Rationale:**
- One bad file shouldn't stop entire batch
- User can review failures after completion
- Failed files tracked in checkpoint for retry

### Phase 3: Performance Review & Optimization (February 2026)

#### Motivation

A full codebase review was performed across all commits to identify performance bottlenecks, algorithmic inefficiencies, and correctness issues. The review found several O(n) and O(n²) operations that would scale poorly with large VDJ databases (50,000+ songs), redundant I/O operations, and missing caching opportunities.

#### Issues Identified & Fixes Applied

**Fix 1: O(n) XML element lookups in database.py**

| Before | After |
|--------|-------|
| `update_song_tags()`, `update_song_scan()`, `remap_path()`, `remove_song()` each iterated the entire XML tree with `self._root.iter("Song")` to find a single element by FilePath | Built `_filepath_to_elem: dict[str, etree._Element]` index during `load()` for O(1) lookups |

**Impact:** For a 50K-song database, every single-song operation went from 50,000 element comparisons to 1 dict lookup.

```python
# Before: O(n) linear scan
for song_elem in self._root.iter("Song"):
    if song_elem.get("FilePath") == file_path:
        ...

# After: O(1) dict lookup
song_elem = self._filepath_to_elem.get(file_path)
if song_elem is None:
    return False
```

---

**Fix 2: O(n²) merge_from() in database.py**

`merge_from()` called the now-fixed update methods (each formerly O(n)) inside a loop over the other DB's songs. For the "add new song" branch, it also iterated `other._root.iter("Song")` for each song. With both databases at 50K songs, this was O(n²).

After Fix 1, the update methods are O(1), and the add-new-song branch uses the other database's `_filepath_to_elem` index directly instead of searching.

---

**Fix 3: Re-sorting mappings on every call in path_remapper.py**

| Before | After |
|--------|-------|
| `sorted(self.mappings.keys(), key=len, reverse=True)` called on every `remap_path()` invocation | Cached as `_sorted_prefixes`, invalidated on `add_mapping()` / `remove_mapping()` |

**Impact:** When remapping 10K paths, eliminated 10K sorts. The sorted list is now computed once and reused.

---

**Fix 4: Double file reads in duplicates.py**

| Before | After |
|--------|-------|
| Partial hash (1MB read) followed by full hash (entire file) for ALL groups of 2+ files | Skip full-hash verification for groups of exactly 2 (size + 1MB partial hash is sufficient); only verify groups of 3+ |

**Impact:** For a typical library where most duplicate groups are pairs, this halves the I/O during duplicate detection. A 100MB file is now read once (1MB) instead of twice (1MB + 100MB).

---

**Fix 5: Duplicated JSON parsing in loudness.py**

| Before | After |
|--------|-------|
| `measure()` and `measure_detailed()` each had their own identical JSON parsing logic (20+ lines duplicated) | Extracted shared `_parse_ffmpeg_json()` static method used by both |

Also fixed a correctness bug: `data.get("input_i", 0)` used `0` as default, but `0.0` is a valid LUFS value. Changed to `None` to distinguish "missing" from "silent".

---

**Fix 6: Redundant extension extraction in validator.py**

| Before | After |
|--------|-------|
| `validate_song()` called `is_audio_file()` and `is_non_audio_file()` each extracting `Path(path).suffix.lower()` independently, plus `song.extension` doing it a third time | Added `_get_extension()` helper; extract once, pass to internal `_is_audio_ext()` / `_is_non_audio_ext()` |

Also merged extension counting into `categorize_entries()` (via `collect_extensions=True` parameter), eliminating a second iteration over all songs in `generate_report()`.

---

**Fix 7: ffmpeg verification on every LoudnessMeasurer instantiation**

| Before | After |
|--------|-------|
| Every `LoudnessMeasurer()` constructor called `ffmpeg -version` via subprocess | Class-level `_verified_paths: set[str]` cache; each ffmpeg path verified only once per process |

**Impact:** Batch processing 100 files across 4 workers previously spawned 25+ redundant `ffmpeg -version` subprocesses. Now spawns exactly 1.

#### Test Coverage

39 new tests added in `tests/test_performance_fixes.py`:

| Test Class | Tests | Covers |
|------------|-------|--------|
| TestDatabaseElementIndex | 9 | Fix 1: index creation, CRUD sync, 1000-song perf |
| TestDatabaseMergeOptimized | 4 | Fix 2: merge add/update/index integrity |
| TestPathRemapperCachedPrefixes | 5 | Fix 3: cache build/invalidation/reuse |
| TestDuplicateHashOptimization | 3 | Fix 4: pair skips full hash, triple verifies |
| TestLoudnessJsonParser | 7 | Fix 5: valid/missing/malformed JSON, 0.0 LUFS |
| TestValidatorExtensionOptimization | 6 | Fix 6: single extraction, report extension counts |
| TestFfmpegVerificationCache | 5 | Fix 7: single verify, cache miss on new path |

Test count after Phase 3: **240 tests passing** (199 existing + 39 new + 2 newly collected)

---

### Phase 4: Full GUI Completion (February 2026)

All 17 CLI commands now have GUI equivalents across 5 tabs:

| Tab | Features |
|-----|----------|
| Database | Load/browse, backup/validate/clean, tag editing, operation log |
| Normalization | Measure/apply LUFS, CSV export, parallel processing, pause/resume |
| Files | 5 sub-tabs: scan, import, remove, remap, duplicates |
| Analysis | 3 sub-tabs: energy, MIK import, mood |
| Export | Serato export with playlist/crate browser |

**Key additions:**
- `ConfigurableResultsTable` widget with dynamic columns via `columns: list[dict]`
- Database panel tag editing (energy, key, comment) with inline save
- Operation history log (last 20 operations)
- GUI integration tests in `tests/test_gui_integration.py`

---

### Phase 5: Analysis Streaming, Caching & Format Fixes (February 2026)

#### Persistent Caches (SQLite)

Two SQLite caches prevent redundant work across sessions:

| Cache | Location | Purpose |
|-------|----------|---------|
| `MeasurementCache` | `~/.vdj_manager/measurements.db` | LUFS loudness measurements |
| `AnalysisCache` | `~/.vdj_manager/analysis.db` | Energy, mood, MIK results |

Both use mtime + file_size for invalidation — if a file changes, cached results are discarded.

#### Real-Time Streaming Results

Analysis workers now emit `result_ready = Signal(dict)` per-file during processing, with results appearing in the GUI table immediately rather than all at once when finished. The database is saved at task completion to avoid excessive I/O during analysis.

#### Tag Storage Format Changes

| Tag | Field | Old Format | New Format |
|-----|-------|-----------|------------|
| Energy | `Tags/@Grouping` | `"Energy 7"` | `"7"` (plain number) |
| Mood | `Tags/@User2` | N/A | `"#happy"` (hashtags) |
| MIK Key | `Tags/@Key` | — | `"Am"` |
| MIK Energy | `Tags/@Grouping` | `"Energy 7"` | `"7"` |

The energy parser handles both plain number and legacy "Energy N" format for backward compatibility.

#### Additional Fixes

- **VDJ database format**: Apostrophe preservation (`&apos;` entities), space before `/>` in self-closing tags
- **Parallel analysis**: ProcessPoolExecutor with top-level picklable functions
- **mpg123 stderr suppression**: `_suppress_stderr()` context manager redirects fd 2 to `/dev/null`
- **.mp4 format support**: Added to audio_extensions for analysis

---

### Bug #6: Flaky Qt Segfaults in Full Test Suite

**Symptoms:**
- Running `pytest tests/ -v` intermittently crashed with SIGBUS (exit code 139)
- Individual test files always passed in isolation
- Crashes most frequent in `test_files_panel.py` and `test_mood_analysis.py`

**Root Cause:**
Two interacting issues:
1. **macOS fork() after Qt**: Qt creates internal threads; `fork()` on macOS copies the parent's thread state in a broken state, causing segfaults in child processes
2. **Cross-test Qt state pollution**: Workers started in earlier tests left behind queued signals and C++ objects; `processEvents()` in later tests delivered signals to deleted objects

**Fix (commit 75c1610):**
Created `tests/conftest.py` with:
1. `pytest_configure`: Sets `multiprocessing.set_start_method("spawn", force=True)` on macOS
2. `_qt_cleanup` autouse fixture: Calls `processEvents()` + `gc.collect()` after every test

**Result:** 464 tests pass consistently across 3+ consecutive full-suite runs with zero segfaults.

**Lesson learned:** On macOS, always use `spawn` (not `fork`) when combining multiprocessing with Qt. Clean up Qt state between tests to prevent signal delivery to dead objects.

---

### Phase 6: GUI Readability & Results Visibility (February 2026)

#### Motivation

After running energy analysis on FLAC files, the GUI provided insufficient diagnostic information — raw file paths were truncated, there was no way to distinguish file formats, status had no color coding, and the results table wasn't sortable. Additionally, the GUI panels were dense with deep nesting, cramped sections, and no visual hierarchy.

#### Results Table Improvements (`ConfigurableResultsTable`)

| Feature | Before | After |
|---------|--------|-------|
| File paths | Raw full path (truncated) | Filename only, full path on hover tooltip |
| Status display | Plain text, all same color | Color-coded: green (ok/cached), red (errors), orange (failed) |
| Error details | Not visible | Full error message in tooltip on hover |
| Sorting | Not supported | Click any column header to sort |
| Row count | Not shown | Live "N results" label below table |
| File format | Not shown | "Fmt" column showing `.mp3`, `.flac`, etc. |
| Failure summary | Not shown | Status bar breakdown: "3 failed (.flac: 2, .wav: 1)" |

#### Database Panel Layout Improvements

| Component | Before | After |
|-----------|--------|-------|
| Header | Source/Load in one row, Backup/Validate/Clean in separate row | All controls merged into single compact row |
| Statistics | 6-row vertical form in splitter | Single-line inline summary above splitter |
| Tag editor | Always visible (wastes space) | Hidden by default, appears when a track is selected |
| Operation log | 120px max height | 150px max height |
| Splitter | 4 sections (stats, tracks, tags, log) | 3 sections (tracks, tags, log) |

#### Main Window

- Minimum size increased from 900x600 to 1000x700 for better breathing room

#### Test Coverage

13 new tests added across 3 test files:

| Test Class | Tests | Covers |
|------------|-------|--------|
| ConfigurableResultsTable (new tests) | 8 | filename display, color coding, sorting, row count |
| TestFormatColumnAndFailureSummary | 5 | format column in all 3 tabs, failure summary |
| Integration tests (updated) | — | format key in streamed result dicts |

Test count: **477 tests passing** (464 + 13 new)

---

## Commit History

```
d52823b Add exception logging and vectorize waveform peak extraction
cf571a3 Add download timeout and improve crate name sanitization
befe4c0 Cache analysis objects at process level in worker functions
622e431 Batch SQLite queries in cache get_batch() methods
7152896 Fix save failure notification and debounce analysis saves
07a8f26 Fix file worker thread safety — move DB mutations to main thread
d891274 Fix XXE vulnerability in XML parser
fc805bf Include Windows-path tracks in all analysis types (MyNVMe fix)
cf1941b Retry on library-specific network errors (musicbrainzngs/pylast)
031b807 Fix mood analysis: correct file count and eliminate "failed" status
7650704 Add tests for retry logic and GUI mood worker online integration
6db8bfe Add retry with exponential backoff for online mood API calls
c90e828 Fix file descriptor exhaustion after ~1000 files in analysis workers
f900286 Improve GUI readability with color-coded results, compact layouts, and format column
75c1610 Write energy as plain number, fix flaky Qt test segfaults
aaf5462 Stream analysis results to GUI in real-time with periodic saves
f94a05d Fix flaky bus error in normalization worker tests
a1b8676 Add comprehensive tests for AnalysisCache
02e0d59 Add persistent analysis cache with SQLite storage
2d0ae57 Move mood to User2 hashtags, MIK key to Key field, allow 20 max workers
0851952 Fix entity preservation in database save for large VDJ databases
839d660 Fix database save to match VDJ format exactly
51b2575 Add track count limit and max duration filter to analysis panel
0e57bac Add parallel processing to analysis workers with ProcessPoolExecutor
45a802e Integrate measurement cache into normalization workers and panel
97f5071 Add SQLite-backed measurement cache for LUFS results
803bdad Add comprehensive mood analysis tests across all layers
8ebabe2 Update CLAUDE.md with GUI architecture and 380 test count
e92897a Add operation history log and GUI integration tests
53fe19d Add Serato export panel with crate management
9cc3b3c Add analysis panel (energy, mood, MIK import) and tag editing
0e26013 Add apply normalization, CSV export, and limit option to GUI
50a7e61 Add file management panel with scan, import, remove, remap, duplicates
2ad4e42 Add database validation and clean operations to GUI
20d2b1f Add performance optimizations across 6 modules with 39 new tests
0bad51b Remove tracked __pycache__ files and update .gitignore
19251fe Update development history with corrected database format findings
6b039d4 Fix database save to use lxml default format (revert incorrect fix)
7366d5b Add parallel processing to GUI normalization worker
b8df4ed Add comprehensive development documentation
7c374df Fix backup mtime to reflect creation time, not source mtime
111760d Update documentation with desktop app guide
7c2fc01 Add comprehensive UI tests
15ac5de Add tests for VDJ database save format compatibility
12e013c Add main window, app entry point, and resume dialog
cae38e5 Add normalization panel with full workflow
6281a01 Add normalization worker with checkpoint support
93030d6 Add progress widget with pause/resume controls
2676e81 Add database panel with track table and virtual scrolling
5f30fa8 Add pausable worker base class with Qt signals
76c4390 Add task state management and checkpoint persistence
8cb9a6f Add PySide6 dependency and GUI entry point
34825db Fix VDJ database save to preserve expected format
1dcc128 Add MkDocs documentation and comprehensive README
c37f228 Add comprehensive unit tests
29a76f3 Add parallel processing for loudness normalization
261642b Initial commit: VDJ Manager v0.1.0
```

## Test Coverage

Test count after Phase 8: **804 tests passing**

---

### Phase 9: Code Review Fixes — Security, Performance & Quality (February 2026)

A comprehensive code review across all 78 commits identified security vulnerabilities, performance bottlenecks, and code quality issues. All fixes were organized into 7 commits:

#### Security Fixes

- **XXE vulnerability in XML parser**: Added `resolve_entities=False, no_network=True` to lxml XMLParser to prevent XML External Entity attacks
- **Model download hash verification**: Added SHA-256 hash verification after downloading Essentia model files, with download timeout (300s)
- **Serato crate name sanitization**: Regex-based replacement of unsafe filesystem characters (`/\:*?"<>|`) in crate names, preventing path traversal

#### Performance Fixes

- **Batch SQLite queries**: Rewrote `get_batch()` in both AnalysisCache and MeasurementCache to use single `WHERE IN` queries instead of N individual queries
- **Process-level caching**: Module-level `_process_cache` dict in analysis workers caches EnergyAnalyzer, MoodBackend, and AnalysisCache objects across ProcessPoolExecutor calls within a single process
- **Vectorized waveform peaks**: Replaced Python loop with NumPy `reshape().max(axis=1)` for peak extraction
- **Debounced analysis saves**: Removed per-batch `database.save()` calls during analysis, saving once at task completion

#### Code Quality Fixes

- **File worker thread safety**: Refactored ImportWorker, RemoveWorker, RemapWorker to emit mutation signals instead of directly mutating the database from worker threads. Main thread now processes mutations via signal handlers.
- **Save failure notification**: Added statusbar notification when `_flush_save()` fails in MainWindow
- **Exception logging**: Added `logger.warning()` with `exc_info=True` to bare except blocks in energy.py and mood.py

#### Test Coverage

34 new tests across 6 files:
- `test_database.py`: XXE protection test
- `test_analysis_cache.py` / `test_measurement_cache.py`: Batch query tests
- `test_analysis_panel.py`: Process-level caching tests
- `test_energy.py` (new): Exception logging tests
- `test_serato.py` (new): Crate name sanitization tests
- `test_model_downloader.py`: Download timeout + urlopen mock tests
- `test_waveform.py`: Vectorized peak verification test
- `test_mood_analysis.py`: Exception logging tests

Test count after Phase 9: **838 tests passing**

## Lessons Learned

1. **Examine actual working files before fixing format issues** - We incorrectly assumed VDJ needed double quotes and CRLF, but examining actual VDJ database files showed lxml defaults were correct. Always `xxd` or hex-dump working files first.

2. **Test with real consumer software** - Unit tests passing doesn't mean the software works. Always verify with the actual application (VirtualDJ in this case).

3. **Don't over-engineer** - The simplest solution (lxml's default output) was correct. Adding "fixes" for assumed requirements introduced bugs.

4. **File metadata preservation is tricky** - `shutil.copy2` preserving mtime caused unexpected sorting issues.

5. **Qt testing requires event loop awareness** - Signals won't be received without processing events.

6. **Batch boundaries are natural pause points** - Designing for interruptibility from the start makes pause/resume straightforward.

7. **Checkpoint early, checkpoint often** - JSON checkpoints are cheap and provide crash recovery for free.

8. **Separate bugfix commits** - Each bug fix should be its own commit with a corresponding test case for traceability.

9. **When a fix doesn't work, question the hypothesis** - If the "fix" doesn't solve the problem, the root cause analysis was probably wrong.

10. **Build indexes during parsing** — When XML elements need both model-level and element-level access, build both maps in a single parse pass.

11. **Cache derived data, invalidate on mutation** — Sorted prefix lists, ffmpeg verification results, etc. should be computed once and invalidated explicitly when inputs change.

12. **Profile before optimizing** — The O(n²) merge was the most impactful fix but wouldn't have been obvious without reading the code carefully.

13. **0 is not None** — Using `0` as a default return value for measurements where `0` is valid (LUFS, BPM) silently hides errors. Use `None` to represent "no data".

14. **On macOS, use `spawn` not `fork` with Qt** — `fork()` after Qt threads causes segfaults due to broken inherited thread state. Always `set_start_method("spawn")`.

15. **Clean up Qt state between tests** — Autouse fixture with `processEvents()` + `gc.collect()` prevents cross-test signal delivery to dead C++ objects.

16. **Stream results, don't batch them** — Emitting per-file signals gives users immediate feedback and makes the UI feel responsive even for long operations.

### Phase 7: Audio Player & Online Mood (February 2026)

#### Audio Playback

A 3-layer player architecture was built for clean separation of concerns:

| Layer | File | Responsibility |
|-------|------|----------------|
| PlaybackEngine | `player/engine.py` | Pure Python, no Qt. VLC via python-vlc, thread-safe with RLock, observer pattern callbacks |
| PlaybackBridge | `player/bridge.py` | Qt Signals adapter. Translates engine callbacks to Qt Signals for UI binding |
| UI Widgets | `ui/widgets/player_panel.py`, `mini_player.py`, `waveform_widget.py` | Full player tab + always-visible mini player bar |

**Player features:**
- Waveform display with soundfile-first loading (avoids librosa audioread fd leaks)
- Editable cue points: right-click to add, drag to move, right-click to rename/delete
- Album art extraction from embedded tags (APIC, covr, FLAC pictures)
- Star ratings with click-to-rate, click-same-to-clear toggle
- Queue management with shuffle and repeat modes (none/one/all)
- Speed control (0.5x-2.0x)
- Mini player: 60px always-visible bar at bottom of all tabs
- Debounced save: `QTimer.singleShot(5000)` batches play count/rating saves
- Graceful VLC degradation: controls disabled when VLC not found

**Waveform caching:** `WaveformCache` (SQLite at `~/.vdj_manager/waveforms.db`) keyed by (file_path, width), invalidated by mtime/size.

#### Online Mood Enrichment

Tiered online lookup for mood classification:
1. Last.fm track tags (cleaned artist/title metadata)
2. Last.fm artist tags (fallback when track has no tags)
3. MusicBrainz genres
4. Local model analysis (essentia MTG-Jamendo)

**Metadata cleaning:** `_clean_artist()` strips featured artists (feat./ft.) and multi-artist separators. `_clean_title()` removes parentheticals, bracket info, and remix suffixes.

**Rate limiting:** Thread-safe token-bucket limiters (5 req/s for Last.fm, 1 req/s for MusicBrainz).

**Caching:** `@lru_cache(2048)` deduplicates identical artist+title pairs. Model-aware cache keys ("mood:mtg-jamendo" vs "mood:heuristic").

#### Structured Logging

- `setup_logging()` in `config.py` with `RotatingFileHandler` (5MB, 3 backups) at `~/.vdj_manager/logs/`
- `--verbose/-v` CLI flag (envvar `VDJ_VERBOSE`) controls console log level
- Replaced 18+ silent `except Exception: pass` blocks with structured logger calls across 9 modules
- Log levels: DEBUG (expected fallbacks), WARNING (recoverable errors), ERROR (data-loss risks)

#### Bug Fixes

- **Waveform never displayed:** `cache.put(file_path, width, peaks)` had args swapped — fixed to `cache.put(file_path, peaks, width)`
- **PySoundFile warning:** librosa's audioread fallback for MP3 files — fixed with soundfile-first loading for WAV/FLAC/OGG
- **Essentia model URL:** Updated from old `music-style/` to current `feature-extractors/discogs-effnet/` path
- **MyNVMe Windows paths excluded from mood analysis:** Removed `is_windows_path` filter when online enabled

#### Test Coverage

Test count: **767 tests passing** (477 from Phase 6 + 290 new)

---

### Phase 8: Robustness & Windows-Path Support (February 2026)

#### Retry with Exponential Backoff

Online mood lookups (Last.fm, MusicBrainz) now retry on transient network errors with exponential backoff:

- Base retry function `_retry_on_network_error()` handles `ConnectionError`, `OSError`, `URLError`
- `extra_exceptions` parameter catches library-specific wrappers (`musicbrainzngs.NetworkError`, `pylast.NetworkError`)
- Up to 3 retries with 1s → 2s → 4s backoff delays
- Returns `None` after all retries exhausted (graceful degradation)

#### Mood Analysis: No More "failed"

Multi-tier fallback ensures every track gets a mood result:

1. Cache check
2. Online lookup (Last.fm → MusicBrainz) when enabled
3. Primary local model (MTG-Jamendo or Heuristic)
4. Fallback local model (the other one)
5. "unknown" as last resort — never returns "failed" or "error"

Tracks tagged `#unknown` can be re-analyzed later via "Re-analyze Unknown" button.

#### Windows-Path Track Inclusion (MyNVMe Fix)

The MyNVMe database contains Windows paths (`D:\...`). Previously, all analysis types excluded these tracks entirely.

**Fix:** Windows-path tracks are now included in all three analysis types:
- **Energy / MIK**: `_get_audio_tracks()` no longer hard-skips `is_windows_path`; only requires `Path.exists()` for non-Windows paths
- **Mood**: `_get_mood_tracks()` includes Windows-path tracks regardless of online checkbox state
- **Info labels**: Show "X tracks (Y local, Z remote)" breakdown when remote tracks are present
- Workers handle missing files gracefully (cached results applied, non-cached fail with clear status)

#### Bug Fixes

- **`musicbrainzngs.NetworkError` not retried**: The retry function only caught base Python exceptions; library-specific wrappers escaped. Added `extra_exceptions` parameter.
- **Mood info label wrong count**: Used `_get_audio_tracks()` instead of `_get_mood_tracks()` for the mood tab label.
- **Mock exception classes in tests**: `MagicMock` attributes aren't valid exception classes — tests now create proper `type("NetworkError", (Exception,), {})` classes.

#### Test Coverage

Test count: **804 tests passing** (767 from Phase 7 + 37 new)

New test classes:
- `TestRetryOnNetworkError` (10 tests): Retry logic, backoff timing, extra_exceptions
- `TestLastFmRetryIntegration` (2 tests): Connection reset retried in Last.fm lookups
- `TestMusicBrainzRetryIntegration` (3 tests): NetworkError retried in MusicBrainz lookups
- `TestAnalyzeMoodSingleFallback` (6 tests): Fallback model, unknown return, exception handling
- `TestMoodWorkerOnlineIntegration` (8 tests): Online mood in GUI workers
- `TestWindowsPathTrackInclusion` (6 tests): Windows-path tracks in all analysis types
- Updated 7 existing tests for new "no failed" behavior

---

## Future Improvements

1. **Batch Editing** - Select multiple tracks, edit tags in bulk
2. **Cloud Backup** - Optional backup to cloud storage
3. **Diff View** - Show changes before saving database
4. **Smart Playlists** - Auto-generate playlists by energy/mood/key
