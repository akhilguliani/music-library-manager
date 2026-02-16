# Testing Guide

This guide covers how to run tests, write new tests, and understand the testing patterns used in VDJ Manager.

## Running Tests

### All Tests

```bash
# Run all tests (838 tests)
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
├── test_mood_analysis.py             # Mood classification + Windows-path track tests
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
├── test_online_mood.py               # Online mood lookup + retry tests
├── test_energy.py                    # EnergyAnalyzer exception logging tests
├── test_serato.py                    # Serato crate sanitization + writer tests
├── test_waveform.py                  # Waveform peak generation + cache tests
├── test_model_downloader.py          # Model download + timeout tests
├── test_ui_app.py                    # Main window tests
├── test_validator.py                 # File validation tests
└── test_waveform_widget.py           # Waveform display + cue point tests
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
    """Tests for VDJ database save format compatibility."""

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
    energy = calculate_energy_from_features(rms=0.01, tempo=60)
    assert energy >= 1


def test_energy_maximum_value(self):
    """Test maximum energy value is 10."""
    energy = calculate_energy_from_features(rms=1.0, tempo=180)
    assert energy <= 10
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

## Test Coverage Goals

| Module | Target Coverage |
|--------|-----------------|
| core/ | 90%+ |
| files/ | 85%+ |
| normalize/ | 80%+ |
| ui/workers/ | 80%+ |
| ui/widgets/ | 70%+ |

Current coverage: **838 tests passing**
