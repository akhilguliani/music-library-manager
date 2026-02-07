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

## Commit History

```
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

Final test count: **240 tests passing**

| Module | Tests |
|--------|-------|
| test_backup.py | 10 |
| test_checkpoint_manager.py | 20 |
| test_database.py | 15 |
| test_mapper.py | 6 |
| test_models.py | 14 |
| test_normalization.py | 8 |
| test_normalization_panel.py | 14 |
| test_normalization_worker.py | 11 |
| test_path_remapper.py | 9 |
| test_pausable_worker.py | 16 |
| test_performance_fixes.py | 39 |
| test_progress_widget.py | 20 |
| test_resume_dialog.py | 17 |
| test_track_model.py | 16 |
| test_ui_app.py | 13 |
| test_validator.py | 10 |

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

Final test count: **240 tests passing** (199 existing + 39 new + 2 newly collected)

#### Lessons Learned

10. **Build indexes during parsing** — When XML elements need both model-level and element-level access, build both maps in a single parse pass.

11. **Cache derived data, invalidate on mutation** — Sorted prefix lists, ffmpeg verification results, etc. should be computed once and invalidated explicitly when inputs change.

12. **Profile before optimizing** — The O(n²) merge was the most impactful fix but wouldn't have been obvious without reading the code carefully. Always trace the full call path.

13. **0 is not None** — Using `0` as a default return value for measurements where `0` is valid (LUFS, BPM) silently hides errors. Use `None` to represent "no data".

---

## Future Improvements

1. **Analysis Panel** - Energy level and mood classification
2. **Serato Export UI** - Visual crate selection and export
3. **Batch Editing** - Select multiple tracks, edit tags in bulk
4. **Cloud Backup** - Optional backup to cloud storage
5. **Diff View** - Show changes before saving database
