# Contributing Guide

Thank you for your interest in contributing to VDJ Manager! This guide covers the development process, coding standards, and how to submit changes.

## Development Setup

### Prerequisites

- Python 3.10+
- ffmpeg (for audio processing)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/akhilguliani/music-library-manager.git
cd music-library-manager

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[dev]"

# Verify installation
vdj-manager --version
pytest tests/ -v
```

### Project Structure

```
vdj_manager/
├── cli.py              # Click-based CLI entry point
├── config.py           # Configuration constants
├── core/
│   ├── database.py     # VDJ XML parser/writer
│   ├── models.py       # Pydantic data models
│   └── backup.py       # Backup management
├── analysis/
│   ├── audio_features.py  # librosa + MIK reader
│   ├── energy.py       # Energy classification
│   ├── mood_backend.py # Mood model protocol + factory
│   ├── mood_mtg_jamendo.py # MTG-Jamendo 56-class CNN
│   └── online_mood.py  # Last.fm / MusicBrainz lookup
├── files/
│   ├── validator.py    # File validation
│   ├── scanner.py      # Directory scanning
│   ├── path_remapper.py # Windows path conversion
│   └── duplicates.py   # Duplicate detection
├── normalize/
│   ├── loudness.py     # LUFS measurement
│   └── processor.py    # Parallel normalization
├── export/
│   ├── serato.py       # Serato crate/tag writer
│   └── mapper.py       # VDJ→Serato mapping
├── player/             # Audio playback (VLC)
│   ├── engine.py       # UI-agnostic playback engine
│   ├── bridge.py       # Qt signal bridge
│   ├── waveform.py     # Waveform peak generation
│   └── album_art.py    # Album art extraction
└── ui/                 # Desktop GUI (PySide6)
    ├── app.py          # Application entry point
    ├── main_window.py  # Main window with tabs
    ├── widgets/        # UI components
    ├── workers/        # Background processing
    ├── models/         # Qt data models
    └── state/          # Checkpoint management
```

## Development Process

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 2. Make Changes

Follow these guidelines:

- **One logical change per commit**
- **Write tests for new functionality**
- **Add tests for bug fixes** (to prevent regression)
- **Update documentation** if needed

### 3. Run Tests

```bash
# Run all tests (838 tests)
pytest tests/ -v

# Run specific test file
pytest tests/test_database.py -v

# Run with coverage
pytest tests/ --cov=src/vdj_manager --cov-report=html
```

### 4. Commit with Descriptive Messages

```bash
git commit -m "$(cat <<'EOF'
Short summary (50 chars or less)

Longer description of what changed and why. Wrap at 72 characters.
Include any relevant context or motivation for the change.

Co-Authored-By: Your Name <your@email.com>
EOF
)"
```

### 5. Submit Pull Request

- Push your branch
- Create a PR with clear description
- Link any related issues

## Coding Standards

### Python Style

- Follow PEP 8
- Use type hints for function signatures
- Maximum line length: 100 characters
- Use docstrings for public functions/classes

```python
def calculate_energy(audio_path: Path, sample_rate: int = 22050) -> int:
    """Calculate energy level (1-10) for an audio file.

    Args:
        audio_path: Path to the audio file
        sample_rate: Sample rate for analysis (default: 22050)

    Returns:
        Energy level from 1 (low) to 10 (high)

    Raises:
        FileNotFoundError: If audio file doesn't exist
        AudioProcessingError: If file cannot be processed
    """
    ...
```

### Testing Standards

- Test file naming: `test_<module>.py`
- Use pytest fixtures for setup
- Test both success and failure cases
- Mock external dependencies

```python
class TestEnergyCalculation:
    def test_calculate_energy_returns_valid_range(self, sample_audio):
        """Energy should be between 1 and 10."""
        energy = calculate_energy(sample_audio)
        assert 1 <= energy <= 10

    def test_calculate_energy_missing_file_raises(self):
        """Should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            calculate_energy(Path("/nonexistent/file.mp3"))
```

### Bug Fix Process

When fixing bugs, always:

1. **Write a failing test first** that demonstrates the bug
2. **Fix the bug** with minimal changes
3. **Verify the test passes**
4. **Commit separately**: bugfix commit + test commit (or combined if small)

### UI Development (PySide6)

For desktop UI contributions:

1. **Use Qt signals/slots** for thread communication
2. **Never block the main thread** - use QThread for long operations
3. **Test signal emissions** with event loop processing

See the [Testing](Testing) guide for more details on testing Qt code.

## VirtualDJ Database Format

Understanding VDJ's XML format is crucial for contributions:

### XML Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<VirtualDJ_Database Version="8">
  <Song FilePath="/path/to/track.mp3" FileSize="5000000">
    <Tags Author="Artist" Title="Track" Grouping="7" User2="#happy" />
    <Infos SongLength="180.5" Bitrate="320" />
    <Scan Bpm="0.5" Key="Am" Volume="1.0" />
    <Poi Type="cue" Pos="30.0" Num="1" Name="Drop" />
  </Song>
</VirtualDJ_Database>
```

### Critical Format Requirements

VDJ is sensitive to XML formatting:

| Aspect | Required Format |
|--------|-----------------|
| XML Declaration | Double quotes: `<?xml version="1.0"...?>` |
| Line Endings | CRLF (`\r\n`) on all platforms |
| Self-closing tags | Space before `/>`: `<Tags ... />` |
| Apostrophes | `&apos;` entities (must re-escape after lxml) |
| Encoding | UTF-8 |
| BPM Storage | Seconds per beat (0.5 = 120 BPM) |
| Energy | Plain number in `Grouping` (e.g., `"7"`) |
| Mood | Hashtags in `User2` (e.g., `"#happy"`) |

### BPM Conversion

VDJ stores BPM as seconds-per-beat, not beats-per-minute:

```python
# VDJ value to actual BPM
actual_bpm = 60.0 / vdj_bpm_value  # 0.5 -> 120 BPM

# Actual BPM to VDJ value
vdj_bpm_value = 60.0 / actual_bpm  # 120 BPM -> 0.5
```

## Running the Desktop App

```bash
# Launch GUI
vdj-manager-gui

# Or run directly
python -m vdj_manager.ui.app
```

## Documentation

### Building Docs

```bash
# Install docs dependencies
pip install mkdocs mkdocs-material mkdocstrings[python]

# Serve locally
mkdocs serve

# Build static site
mkdocs build
```

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Include reproduction steps for bugs
- Include VDJ version and OS for compatibility issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
