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

Final test count: **199 tests passing**

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

## Future Improvements

1. **Analysis Panel** - Energy level and mood classification
2. **Serato Export UI** - Visual crate selection and export
3. **Batch Editing** - Select multiple tracks, edit tags in bulk
4. **Cloud Backup** - Optional backup to cloud storage
5. **Diff View** - Show changes before saving database
