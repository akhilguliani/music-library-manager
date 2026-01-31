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

- **Database Selection**: Choose between Local, MyNVMe, or a custom database file
- **Statistics Display**: View track counts, audio files, energy tags, cue points
- **Track Browser**: Virtual-scrolling table supporting 18k+ tracks
- **Search/Filter**: Quick filter to find tracks by title, artist, genre

### Normalization Panel

The Normalization tab offers:

- **LUFS Measurement**: Measure loudness of your entire library
- **Configurable Target**: Set target LUFS (default: -14.0)
- **Batch Processing**: Adjustable batch size for checkpoint frequency
- **Progress Display**: Real-time progress bar with percentage
- **Pause/Resume**: Pause long operations and resume later
- **Results Table**: View LUFS values and gain adjustments per track

### Analysis Panel

The Analysis tab will support:

- Energy level analysis (1-10)
- Mood classification
- Mixed In Key tag import

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
| Ctrl+3 | Switch to Analysis tab |
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
├── main_window.py      # Main window with tabs
├── widgets/
│   ├── database_panel.py      # Database browser
│   ├── normalization_panel.py # Normalization controls
│   ├── progress_widget.py     # Progress + pause/resume
│   └── results_table.py       # Results display
├── workers/
│   ├── base_worker.py         # PausableWorker base class
│   ├── database_worker.py     # Async database loading
│   └── normalization_worker.py # Parallel measurement
├── models/
│   ├── track_model.py         # QAbstractTableModel for tracks
│   └── task_state.py          # Checkpoint state dataclass
└── state/
    └── checkpoint_manager.py  # Checkpoint persistence
```

### Qt Signals

Workers communicate with the UI through Qt signals:

- `progress(current, total, percent)`: Progress updates
- `result_ready(path, result_dict)`: Individual results
- `batch_complete(batch_num, total_batches)`: Batch completion
- `status_changed(status)`: Status changes (running, paused, etc.)
- `finished_work(success, message)`: Task completion

This allows the UI to remain responsive during long operations.

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
