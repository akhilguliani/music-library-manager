# Desktop Application

VDJ Manager includes a desktop GUI application built with PySide6 (Qt for Python), providing a visual interface for long-running operations with progress tracking and pause/resume capability.

## Starting the Desktop App

```bash
# Launch the desktop application
vdj-manager-gui
```

## Features

### Database Panel

The Database tab provides:

- **Merged Header**: Source selection, Load, Backup, Validate, and Clean buttons all in one compact row
- **Compact Statistics**: Inline summary bar showing track/audio/energy/cues counts at a glance
- **Track Browser**: Virtual-scrolling table supporting 18k+ tracks with search/filter
- **Tag Editor**: Collapsible tag editing panel (hidden until a track is selected) for energy, key, and comment fields
- **Operation Log**: Timestamped history of the last 20 operations

### Normalization Panel

The Normalization tab offers:

- **LUFS Measurement**: Measure loudness of your entire library
- **Configurable Target**: Set target LUFS (default: -14.0)
- **Batch Processing**: Adjustable batch size for checkpoint frequency
- **Progress Display**: Real-time progress bar with percentage
- **Pause/Resume**: Pause long operations and resume later
- **Results Table**: View LUFS values and gain adjustments per track

### Files Panel

The Files tab provides 5 sub-tabs:

- **Scan**: Preview audio files in a directory before importing
- **Import**: Add new files to the VDJ database
- **Remove**: Remove missing or invalid entries
- **Remap**: Convert Windows paths to macOS paths with prefix detection
- **Duplicates**: Find duplicate entries by filename, metadata, or file hash

### Analysis Panel

The Analysis tab provides 3 sub-tabs with real-time streaming results:

- **Energy**: Analyze tracks for energy levels (1-10), stored in `Grouping` field as a plain number
- **MIK Import**: Import Mixed In Key tags (key → `Key` field, energy → `Grouping` field)
- **Mood**: Multi-label mood classification with model selection, stored in `User2` as hashtags (e.g., `#happy #uplifting #summer`)
  - **Model selector**: MTG-Jamendo (56-class CNN, recommended) or Heuristic (legacy)
  - **Threshold**: Min confidence to include a mood tag (default 0.10, lower = more tags)
  - **Max tags**: Maximum mood tags per track (default 5)
  - **Re-analyze All**: Clear cache and re-run mood analysis on all tracks
  - **Online enrichment**: Last.fm → MusicBrainz → local model fallback chain

Results stream to the table in real-time as each file is analyzed, with:

- **Format column**: Shows file extension (e.g., `.mp3`, `.flac`) for each result
- **Color-coded status**: Green for success/cached, red for errors (with tooltip details), orange for failures
- **Sortable columns**: Click any column header to sort results
- **Failure summary**: Status bar shows format breakdown on failures (e.g., "3 failed (.flac: 2, .wav: 1)")
- **Row count**: Live result count displayed below the table

A persistent SQLite cache (`~/.vdj_manager/analysis.db`) avoids re-analyzing unchanged files across sessions.

### Export Panel

The Export tab supports:

- **Serato Export**: Export cue points, beatgrid, and metadata to Serato DJ format
- **Playlist/Crate Browser**: Browse and select VDJ playlists for export as Serato crates

### Player Panel

The Player tab provides a full-featured audio player:

- **Waveform Display**: Visual waveform with cue point markers and drag-to-seek
- **Editable Cue Points**: Right-click to add, drag to move, right-click to rename/delete cue points
- **Album Art**: Extracted from embedded audio file tags (APIC, covr, FLAC pictures)
- **Track Metadata**: Title, artist, album, BPM, key, energy, mood
- **Star Rating**: Click-to-rate (1-5 stars), click same star to clear
- **Speed Control**: 0.5x to 2.0x playback speed adjustment
- **Queue Management**: Add tracks, reorder, remove; shuffle and repeat modes
- **Play History**: Last 100 tracks with timestamps
- **Mini Player**: Always-visible 60px bar at bottom of all tabs with transport, progress, volume, and expand button

**Prerequisites:** VLC media player must be installed. The player gracefully degrades when VLC is not found (controls disabled, rest of app works normally).

## Pause and Resume

One of the key features of the desktop app is the ability to pause long-running operations and resume them later, even after closing the application.

### How It Works

1. **Batch Processing**: Files are processed in configurable batches (default: 50)
2. **Checkpoint Saving**: After each batch, progress is saved to `~/.vdj_manager/checkpoints/`
3. **Pause**: Click "Pause" to stop after the current batch and save state
4. **Resume**: On next launch, you'll be prompted to resume incomplete tasks

### Checkpoint Storage

Checkpoints are stored as JSON files containing:

- Task type and configuration
- Completed file paths
- Pending file paths
- Failed files with error messages
- Results from completed operations

### Resume Dialog

When incomplete tasks exist, a dialog appears on startup:

- **Resume**: Continue processing from where you left off
- **Discard Selected**: Delete the selected checkpoint
- **Discard All**: Delete all incomplete checkpoints
- **Later**: Dismiss the dialog and handle tasks later

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+1 | Switch to Database tab |
| Ctrl+2 | Switch to Normalization tab |
| Ctrl+3 | Switch to Files tab |
| Ctrl+4 | Switch to Analysis tab |
| Ctrl+5 | Switch to Export tab |
| Ctrl+6 | Switch to Player tab |
| Space | Play/Pause |
| Ctrl+Right | Next track |
| Ctrl+Left | Previous track |
| Ctrl+O | Open database file |
| Ctrl+Q | Quit application |

## Workflow Example

### Measuring Library Loudness

1. Launch `vdj-manager-gui`
2. Go to **Database** tab
3. Select your database source and click **Load**
4. Go to **Normalization** tab
5. Set target LUFS (default: -14.0)
6. Click **Start Measurement**
7. Monitor progress; pause if needed
8. Review results in the table

### Resuming After Interruption

1. If the app was closed during measurement, restart it
2. The **Resume** dialog appears
3. Select the incomplete task
4. Click **Resume** to continue
5. Previous results are loaded and processing continues

## Configuration

### Checkpoint Directory

Checkpoints are stored in:

```
~/.vdj_manager/checkpoints/
```

### Cleanup

Completed checkpoints are automatically cleaned up. You can also manually delete checkpoints older than a certain age:

```python
from vdj_manager.ui.state.checkpoint_manager import CheckpointManager

manager = CheckpointManager()
manager.cleanup_completed(max_age_days=7)
```

## Architecture

The desktop UI is built with a clean separation of concerns:

```
ui/
├── app.py              # QApplication entry point
├── main_window.py      # Main window with 6 tabs
├── widgets/
│   ├── database_panel.py      # DB load, stats, track browser, tag editing, log
│   ├── normalization_panel.py # Measure, apply, CSV export, limit
│   ├── files_panel.py         # 5 sub-tabs: scan, import, remove, remap, dupes
│   ├── analysis_panel.py      # 3 sub-tabs: energy, MIK import, mood
│   ├── export_panel.py        # Serato export, playlist/crate browser
│   ├── player_panel.py        # Full player with waveform, queue, ratings
│   ├── mini_player.py         # Always-visible mini player bar
│   ├── waveform_widget.py     # Waveform display with cue point editing
│   ├── progress_widget.py     # Progress + pause/resume
│   └── results_table.py       # ConfigurableResultsTable with dynamic columns
├── workers/
│   ├── base_worker.py         # PausableWorker, SimpleWorker, ProgressSimpleWorker
│   ├── database_worker.py     # Load, backup, validate, clean workers
│   ├── normalization_worker.py # Parallel measurement with caching
│   ├── file_workers.py        # Scan, import, remove, remap, duplicate workers
│   ├── analysis_workers.py    # Energy, mood, MIK workers (streaming results)
│   ├── export_workers.py      # Serato export & crate workers
│   └── player_workers.py      # Waveform generation worker
├── models/
│   ├── track_model.py         # QAbstractTableModel for tracks
│   └── task_state.py          # Checkpoint state dataclass
└── state/
    └── checkpoint_manager.py  # Checkpoint persistence
```

### Qt Signals

Workers communicate with the UI through Qt signals:

- `progress(current, total, message)`: Progress updates
- `result_ready(dict)`: Individual streaming results (analysis workers)
- `batch_complete(batch_num, total_batches)`: Batch completion
- `status_changed(status)`: Status changes (running, paused, etc.)
- `finished_work(result)`: Task completion
- `error(message)`: Error reporting

Analysis workers stream results in real-time via `result_ready`, so users see results appear immediately as each file is processed. The database is saved periodically (every 25 results) for crash resilience.

## Troubleshooting

### Application Won't Start

Ensure PySide6 is installed:

```bash
pip install PySide6>=6.6.0
```

### No Database Found

If your database isn't listed, use "Custom..." to browse to the file:

- Local: `~/Library/Application Support/VirtualDJ/database.xml`
- External: `/Volumes/YourDrive/VirtualDJ/database.xml`

### Measurements Slow

For faster processing:

1. Increase batch size (more items per checkpoint)
2. Ensure ffmpeg is in your PATH
3. Close other applications using audio files

### Checking Log Files

VDJ Manager writes detailed logs to `~/.vdj_manager/logs/vdj_manager.log`. To enable verbose console logging:

```bash
VDJ_VERBOSE=1 vdj-manager-gui    # GUI with debug output
vdj-manager --verbose db status   # CLI with debug output
```

Log files rotate at 5MB with 3 backups kept. Check logs to diagnose:
- Analysis failures for specific file formats
- Online mood lookup errors (API rate limits, network issues)
- Database save errors
- Player/VLC initialization problems
