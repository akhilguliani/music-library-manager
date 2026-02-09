# Database Operations

VDJ Manager provides tools for managing your VirtualDJ database.

## CLI Commands

### Status

View library statistics:

```bash
vdj-manager db status --local        # Local database only
vdj-manager db status --mynvme       # External drive database
vdj-manager db status --both         # Both databases
vdj-manager db status --check-files  # Verify file existence
```

### Backup

Create timestamped backups before making changes:

```bash
vdj-manager db backup --both
vdj-manager db backup --local -l "before_cleanup"
```

Backups are stored in `~/.vdj_manager/backups/`.

### Validate

Check database integrity and file existence:

```bash
vdj-manager db validate --local -v
```

### Clean

Remove invalid entries:

```bash
vdj-manager db clean --non-audio --local        # Remove non-audio files
vdj-manager db clean --missing --local           # Remove missing files
vdj-manager db clean --non-audio --dry-run       # Preview only
```

## Desktop GUI

The **Database** tab in the desktop application provides:

- **Merged Header**: Source selection, Load, Backup, Validate, and Clean buttons
- **Compact Statistics**: Inline summary showing track/audio/energy/cues counts
- **Track Browser**: Virtual-scrolling table supporting 18k+ tracks with search
- **Tag Editor**: Collapsible editor for energy, key, and comment fields
- **Double-click to play**: Opens the track in the Player tab
- **Operation Log**: Timestamped history of the last 20 operations

## VDJ Database Format

VirtualDJ stores library data in XML:

```xml
<Song FilePath="/path/to/track.mp3" FileSize="5000000">
  <Tags Author="Artist" Title="Track" Grouping="7" User2="#happy" />
  <Infos SongLength="180.5" Bitrate="320" />
  <Scan Bpm="0.5" Key="Am" Volume="1.0" />
  <Poi Type="cue" Pos="30.0" Num="1" Name="Drop" />
</Song>
```

**BPM Note:** VDJ stores BPM as seconds per beat (e.g., `0.5` = 120 BPM).
