# Player

The Player tab provides a full-featured audio player powered by VLC.

## Prerequisites

VLC media player must be installed on your system. The player gracefully degrades when VLC is not found (controls are disabled but the rest of the app works normally).

```bash
# macOS
brew install vlc

# Or install the python-vlc binding
pip install python-vlc
```

## Features

### Waveform Display

The waveform shows audio peaks for the current track, with:

- **Playhead**: Red vertical line showing current position
- **Cue point markers**: Colored triangles at cue positions
- **Click-to-seek**: Click anywhere on the waveform to seek
- **Drag-to-move cues**: Drag cue markers to reposition them
- **Right-click menu**: Add new cue points, rename or delete existing ones

Waveform data is cached in `~/.vdj_manager/waveforms.db` (SQLite) for instant display on subsequent loads.

### Cue Points

- **Add**: Right-click on the waveform at the desired position
- **Move**: Drag a cue marker to a new position
- **Rename**: Right-click a cue marker and select "Rename"
- **Delete**: Right-click a cue marker and select "Delete"

Changes are persisted to the VDJ database with a 5-second debounced save.

### Album Art

Album art is automatically extracted from embedded audio file tags:

- MP3: ID3 APIC frames
- M4A/MP4: `covr` atoms
- FLAC: Pictures list
- OGG: `metadata_block_picture`

### Star Ratings

Click a star to set the rating (1-5). Click the same star again to clear the rating. Ratings are saved to the VDJ database.

### Queue Management

- **Add to queue**: Double-click a track in the Database tab
- **Reorder**: Drag tracks within the queue
- **Remove**: Right-click and remove from queue
- **Shuffle**: Toggle shuffle mode
- **Repeat**: Cycle through none / repeat one / repeat all

### Speed Control

Adjust playback speed from 0.5x to 2.0x using the speed slider.

### Mini Player

A 60px always-visible bar at the bottom of all tabs provides:

- Play/Pause, Previous, Next buttons
- Progress bar with seek
- Volume control
- "Expand" button to switch to the full Player tab

## Architecture

The player uses a 3-layer architecture:

| Layer | File | Purpose |
|-------|------|---------|
| PlaybackEngine | `player/engine.py` | Pure Python, thread-safe VLC control, queue, history |
| PlaybackBridge | `player/bridge.py` | Qt Signal adapter for engine callbacks |
| UI Widgets | `widgets/player_panel.py`, `mini_player.py` | Visual interface |

This separation allows the engine to be reused in non-Qt contexts (e.g., a web API).
