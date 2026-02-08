# Testing Guide

This guide covers how to run tests, write new tests, and understand the testing patterns used in VDJ Manager.

## Running Tests

### All Tests

```bash
# Run all tests
pytest tests/ -v

# Run with short output
pytest tests/ -q

# Run with coverage report
pytest tests/ --cov=src/vdj_manager --cov-report=html
open htmlcov/index.html  # View coverage report
```

### Specific Tests

```bash
# Run a specific test file
pytest tests/test_database.py -v

# Run a specific test class
pytest tests/test_database.py::TestVDJDatabase -v

# Run a specific test method
pytest tests/test_database.py::TestVDJDatabase::test_load_database -v

# Run tests matching a pattern
pytest tests/ -k "save" -v  # All tests with "save" in name
```

### Test Options

```bash
# Stop on first failure
pytest tests/ -x

# Show local variables in tracebacks
pytest tests/ -l

# Run last failed tests only
pytest tests/ --lf

# Run tests in parallel (requires pytest-xdist)
pytest tests/ -n auto
```

## Test Structure

### Directory Layout

```
tests/
├── conftest.py                       # Shared fixtures (macOS spawn, Qt cleanup)
├── test_analysis_cache.py            # AnalysisCache (SQLite) tests
├── test_analysis_panel.py            # Analysis panel + worker tests
├── test_backup.py                    # BackupManager tests
├── test_checkpoint_manager.py        # Checkpoint persistence tests
├── test_database.py                  # VDJ database parser tests
├── test_database_panel_operations.py # Database panel ops (backup/validate/clean/tags)
├── test_export_panel.py              # Serato export panel tests
├── test_files_panel.py               # Files panel (scan/import/remove/remap/dupes)
├── test_gui_integration.py           # Cross-panel integration tests
├── test_mapper.py                    # VDJ→Serato mapping tests
├── test_measurement_cache.py         # MeasurementCache (SQLite) tests
├── test_models.py                    # Pydantic model tests
├── test_mood_analysis.py             # Mood classification tests
├── test_normalization.py             # LUFS measurement tests
├── test_normalization_panel.py       # Normalization UI panel tests
├── test_normalization_panel_enhanced.py # Enhanced normalization tests
├── test_normalization_worker.py      # Worker thread tests
├── test_operation_panel.py           # Operation panel tests
├── test_path_remapper.py             # Path conversion tests
├── test_pausable_worker.py           # Base worker tests
├── test_performance_fixes.py         # Performance optimization tests (39 tests)
├── test_progress_widget.py           # Progress UI tests
├── test_results_table.py             # ConfigurableResultsTable tests
├── test_resume_dialog.py             # Resume dialog tests
├── test_track_model.py               # Qt model tests
├── test_ui_app.py                    # Main window tests
└── test_validator.py                 # File validation tests
```

### Test Organization

Tests are organized by module with consistent naming:

```python
"""Tests for VDJ database parser."""

import pytest
from pathlib import Path

from vdj_manager.core.database import VDJDatabase


class TestVDJDatabase:
    """Tests for VDJDatabase class."""

    def test_load_database(self, temp_db_file):
        """Test loading a database file."""
        ...

    def test_parse_song_with_full_metadata(self, temp_db_file):
        """Test parsing song with complete metadata."""
        ...


class TestVDJDatabaseSaveFormat:
    """Tests for VDJ database save format compatibility."""

    def test_save_uses_double_quotes_in_xml_declaration(self, temp_db_file):
        """Test that saved XML uses double quotes in declaration."""
        ...
```

## Writing Tests

### Fixtures

Use fixtures for common setup:

```python
@pytest.fixture
def temp_db_file():
    """Create a temporary database file for testing."""
    with NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(SAMPLE_DB_XML)
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def sample_audio(tmp_path):
    """Create a sample audio file for testing."""
    audio_path = tmp_path / "test.mp3"
    # Generate or copy test audio
    yield audio_path
```

### Testing Success Cases

```python
def test_calculate_energy_returns_valid_range(self, sample_audio):
    """Energy should be between 1 and 10."""
    energy = calculate_energy(sample_audio)
    assert 1 <= energy <= 10
    assert isinstance(energy, int)
```

### Testing Error Cases

```python
def test_load_nonexistent_file_raises(self):
    """Test loading non-existent file raises error."""
    db = VDJDatabase(Path("/nonexistent/path/database.xml"))

    with pytest.raises(FileNotFoundError):
        db.load()


def test_save_without_load_raises(self, temp_db_file):
    """Test saving without loading raises error."""
    db = VDJDatabase(temp_db_file)

    with pytest.raises(RuntimeError, match="Database not loaded"):
        db.save()
```

### Testing with Mocks

```python
from unittest.mock import Mock, patch

def test_measure_loudness_calls_ffmpeg(self):
    """Test that loudness measurement invokes ffmpeg."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stderr=b'I: -14.0 LUFS'
        )

        result = measure_loudness(Path("/test/file.mp3"))

        assert result.lufs == -14.0
        mock_run.assert_called_once()
```

## Testing Qt/PySide6 Code

### Event Loop Processing

Qt signals are processed asynchronously. Tests must pump the event loop:

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

### Testing Signal Emissions

```python
def test_worker_emits_progress_signals(self, qapp):
    """Test that worker emits progress signals during processing."""
    progress_values = []
    worker = NormalizationWorker(paths=["/test/1.mp3", "/test/2.mp3"])
    worker.progress.connect(lambda cur, tot, pct: progress_values.append(pct))

    worker.start()

    # Wait for worker to complete or emit signals
    success = process_events_until(
        lambda: len(progress_values) > 0 or not worker.isRunning(),
        timeout_ms=5000
    )

    assert len(progress_values) > 0
```

### Testing UI State

```python
def test_pause_button_disabled_initially(self, qapp):
    """Pause button should be disabled when not running."""
    widget = ProgressWidget()

    assert not widget.pause_button.isEnabled()
    assert widget.start_button.isEnabled()


def test_start_enables_pause_button(self, qapp):
    """Starting should enable the pause button."""
    widget = ProgressWidget()
    widget.set_running(True)

    assert widget.pause_button.isEnabled()
    assert not widget.start_button.isEnabled()
```

### Shared Test Fixtures (conftest.py)

`tests/conftest.py` provides two critical shared fixtures:

```python
def pytest_configure(config):
    """Set multiprocessing start method to 'spawn' for macOS Qt compatibility.

    On macOS, fork() after Qt threads are created causes segfaults because
    forked processes inherit the parent's thread state in a broken state.
    """
    if sys.platform == "darwin":
        import multiprocessing
        multiprocessing.set_start_method("spawn", force=True)


@pytest.fixture(autouse=True)
def _qt_cleanup():
    """Clean up Qt state after each test to prevent cross-test segfaults."""
    yield
    # Process pending Qt events and force garbage collection
    app = QCoreApplication.instance()
    if app is not None:
        app.processEvents()
    gc.collect()
```

### QApplication Fixture

Individual test files create module-scoped QApplication fixtures:

```python
@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for the test module."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    return app
```

## Testing Patterns

### Pattern: Test Bug Fixes

Always add a test when fixing a bug:

```python
class TestVDJDatabaseSaveFormat:
    """Tests for VDJ database save format compatibility.

    VirtualDJ expects specific XML formatting:
    - Double quotes in XML declaration (not single quotes)
    - CRLF line endings (Windows style)

    These tests verify the save() method produces compatible output.
    """

    def test_save_uses_double_quotes_in_xml_declaration(self, temp_db_file):
        """Bug fix: lxml outputs single quotes, VDJ expects double quotes."""
        db = VDJDatabase(temp_db_file)
        db.load()
        db.save()

        with open(temp_db_file, "rb") as f:
            content = f.read()

        xml_str = content.decode("UTF-8")
        assert xml_str.startswith('<?xml version="1.0"')
```

### Pattern: Test Boundaries

Test edge cases and boundaries:

```python
def test_energy_minimum_value(self):
    """Test minimum energy value is 1."""
    # Very quiet, slow track
    energy = calculate_energy_from_features(rms=0.01, tempo=60)
    assert energy >= 1


def test_energy_maximum_value(self):
    """Test maximum energy value is 10."""
    # Very loud, fast track
    energy = calculate_energy_from_features(rms=1.0, tempo=180)
    assert energy <= 10
```

### Pattern: Test State Transitions

For stateful objects, test transitions:

```python
class TestPausableWorker:
    def test_pause_resume_cycle(self, qapp):
        """Test pause/resume state transitions."""
        worker = TestWorker(items=list(range(100)))

        # Initial state
        assert worker.status == "pending"

        # Start
        worker.start()
        process_events_until(lambda: worker.status == "running")
        assert worker.status == "running"

        # Pause
        worker.pause()
        process_events_until(lambda: worker.status == "paused")
        assert worker.status == "paused"

        # Resume
        worker.resume()
        process_events_until(lambda: worker.status == "running")
        assert worker.status == "running"

        # Complete
        process_events_until(lambda: worker.status == "completed")
        assert worker.status == "completed"
```

### Pattern: Test Data Integrity

Verify data survives round-trips:

```python
def test_save_and_reload_preserves_data(self, temp_db_file):
    """Test that saving and reloading preserves all data."""
    db = VDJDatabase(temp_db_file)
    db.load()

    # Modify data
    db.update_song_tags("/path/to/track.mp3", Grouping="10")

    # Save
    db.save()

    # Reload
    db2 = VDJDatabase(temp_db_file)
    db2.load()

    # Verify data preserved
    song = db2.get_song("/path/to/track.mp3")
    assert song.tags.grouping == "10"
```

## Test Data

### Sample VDJ Database XML

```python
SAMPLE_DB_XML = """<?xml version="1.0" encoding="utf-8"?>
<VirtualDJ_Database Version="8">
 <Song FilePath="/path/to/track1.mp3" FileSize="5000000">
  <Tags Author="Artist One" Title="Track One" Genre="Dance" Grouping="7" />
  <Infos SongLength="180.5" Bitrate="320" />
  <Scan Bpm="0.5" Key="Am" Volume="1.0" />
  <Poi Type="cue" Pos="0.5" Num="1" Name="Intro" />
  <Poi Type="cue" Pos="30.0" Num="2" Name="Drop" />
 </Song>
</VirtualDJ_Database>
"""
```

### Generating Test Audio

For tests requiring actual audio files:

```python
@pytest.fixture
def sample_audio(tmp_path):
    """Generate a simple test audio file."""
    import numpy as np
    from scipy.io import wavfile

    # Generate 1 second of sine wave
    sample_rate = 22050
    t = np.linspace(0, 1, sample_rate)
    audio = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)

    path = tmp_path / "test.wav"
    wavfile.write(path, sample_rate, audio)

    yield path
```

## Continuous Integration

### GitHub Actions Workflow

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        pip install -e ".[dev]"

    - name: Run tests
      run: |
        pytest tests/ -v --cov=src/vdj_manager

    - name: Upload coverage
      uses: codecov/codecov-action@v4
```

## Debugging Tests

### Verbose Output

```bash
# Show print statements
pytest tests/ -s

# Show local variables on failure
pytest tests/ -l

# Drop into debugger on failure
pytest tests/ --pdb
```

### Debugging Qt Tests

```python
def test_something_qt(self, qapp):
    widget = MyWidget()

    # Add debugging
    print(f"Widget state: {widget.state}")
    print(f"Button enabled: {widget.button.isEnabled()}")

    # Process events and check again
    QCoreApplication.processEvents()
    print(f"After events: {widget.state}")
```

## Test Coverage Goals

| Module | Target Coverage |
|--------|-----------------|
| core/ | 90%+ |
| files/ | 85%+ |
| normalize/ | 80%+ |
| ui/workers/ | 80%+ |
| ui/widgets/ | 70%+ |

Current coverage: **477 tests passing**
