"""Command-line interface for VDJ Manager."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

from .config import LOCAL_VDJ_DB, MYNVME_VDJ_DB, config
from .core.backup import BackupManager
from .core.database import VDJDatabase
from .files.validator import FileValidator
from .files.scanner import DirectoryScanner
from .files.path_remapper import PathRemapper
from .files.duplicates import DuplicateDetector

console = Console()


def get_database(db_path: Optional[Path] = None) -> VDJDatabase:
    """Load the VDJ database."""
    path = db_path or config.primary_db
    db = VDJDatabase(path)
    db.load()
    return db


def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """VirtualDJ Library Manager - organize, analyze, and normalize your DJ music library."""
    pass


# ============================================================================
# Database Commands
# ============================================================================


@cli.group()
def db():
    """Database operations."""
    pass


@db.command("status")
@click.option("--local", "db_choice", flag_value="local", help="Use local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", help="Use MyNVMe database")
@click.option("--both", "db_choice", flag_value="both", default=True, help="Show both databases")
@click.option("--check-files", is_flag=True, help="Check if files exist (slower)")
def db_status(db_choice: str, check_files: bool):
    """Show library statistics."""
    databases = []

    if db_choice in ("local", "both"):
        if LOCAL_VDJ_DB.exists():
            databases.append(("Local", LOCAL_VDJ_DB))
        else:
            console.print(f"[yellow]Local database not found: {LOCAL_VDJ_DB}[/yellow]")

    if db_choice in ("mynvme", "both"):
        if MYNVME_VDJ_DB.exists():
            databases.append(("MyNVMe", MYNVME_VDJ_DB))
        else:
            console.print(f"[yellow]MyNVMe database not found: {MYNVME_VDJ_DB}[/yellow]")

    if not databases:
        console.print("[red]No databases found![/red]")
        return

    for name, path in databases:
        console.print(f"\n[bold cyan]Database: {name}[/bold cyan]")
        console.print(f"Path: {path}")
        console.print(f"Size: {format_size(path.stat().st_size)}")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Loading database...", total=None)
            db = VDJDatabase(path)
            db.load()

            progress.add_task("Calculating statistics...", total=None)
            stats = db.get_stats(check_existence=check_files)

        table = Table(show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")

        table.add_row("Total entries", str(stats.total_songs))
        table.add_row("", "")
        table.add_row("[bold]By Location[/bold]", "")
        table.add_row("  Local Mac files", str(stats.local_files))
        table.add_row("    └─ /Users/", str(stats.mac_home_paths))
        table.add_row("    └─ /Volumes/MyNVMe", str(stats.mynvme_paths))
        table.add_row("  Windows paths", str(stats.windows_paths))
        table.add_row("    └─ C:/", str(stats.windows_c_paths))
        table.add_row("    └─ D:/", str(stats.windows_d_paths))
        table.add_row("    └─ E:/", str(stats.windows_e_paths))
        table.add_row("  Netsearch (streaming)", str(stats.netsearch))
        table.add_row("", "")
        table.add_row("[bold]By Type[/bold]", "")
        table.add_row("  Audio files", str(stats.audio_files))
        table.add_row("  Non-audio files", str(stats.non_audio_files))
        table.add_row("", "")
        table.add_row("[bold]Metadata[/bold]", "")
        table.add_row("  With energy tags", str(stats.with_energy))
        table.add_row("  With cue points", str(stats.with_cue_points))

        if check_files:
            table.add_row("", "")
            table.add_row("[bold]File Status[/bold]", "")
            table.add_row("  Missing files", str(stats.missing_files))

        console.print(table)


@db.command("backup")
@click.option("--local", "db_choice", flag_value="local", help="Backup local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", help="Backup MyNVMe database")
@click.option("--both", "db_choice", flag_value="both", default=True, help="Backup both databases")
@click.option("--label", "-l", help="Optional label for the backup")
def db_backup(db_choice: str, label: Optional[str]):
    """Create a backup of the database."""
    backup_mgr = BackupManager()

    databases = []
    if db_choice in ("local", "both") and LOCAL_VDJ_DB.exists():
        databases.append(("Local", LOCAL_VDJ_DB))
    if db_choice in ("mynvme", "both") and MYNVME_VDJ_DB.exists():
        databases.append(("MyNVMe", MYNVME_VDJ_DB))

    if not databases:
        console.print("[red]No databases found to backup![/red]")
        return

    for name, path in databases:
        backup_path = backup_mgr.create_backup(path, label=label)
        console.print(f"[green]✓[/green] Backed up {name} database to:")
        console.print(f"  {backup_path}")

    # Show backup stats
    total_backups = len(backup_mgr.list_backups())
    total_size = backup_mgr.total_backup_size
    console.print(f"\n[dim]Total backups: {total_backups} ({format_size(total_size)})[/dim]")


@db.command("validate")
@click.option("--local", "db_choice", flag_value="local", help="Validate local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", help="Validate MyNVMe database")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
def db_validate(db_choice: str, verbose: bool):
    """Check file existence and validate entries."""
    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    console.print(f"[cyan]Validating database: {path}[/cyan]\n")

    db = get_database(path)
    validator = FileValidator()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Validating files...", total=len(db.songs))

        report = validator.generate_report(list(db.songs.values()))
        progress.update(task, completed=len(db.songs))

    # Summary table
    table = Table(title="Validation Report", show_header=True)
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Status", justify="center")

    table.add_row("Total entries", str(report["total"]), "")
    table.add_row("Audio files (valid)", str(report["audio_valid"]), "[green]✓[/green]")
    table.add_row("Audio files (missing)", str(report["audio_missing"]),
                  "[red]✗[/red]" if report["audio_missing"] > 0 else "[green]✓[/green]")
    table.add_row("Non-audio entries", str(report["non_audio"]),
                  "[yellow]![/yellow]" if report["non_audio"] > 0 else "[green]✓[/green]")
    table.add_row("Windows paths", str(report["windows_paths"]),
                  "[yellow]![/yellow]" if report["windows_paths"] > 0 else "[green]✓[/green]")
    table.add_row("Netsearch entries", str(report["netsearch"]), "[dim]-[/dim]")

    console.print(table)

    # Extensions breakdown
    if verbose and report["extensions"]:
        console.print("\n[bold]Extensions:[/bold]")
        ext_table = Table(show_header=False)
        ext_table.add_column("Extension")
        ext_table.add_column("Count", justify="right")
        for ext, count in list(report["extensions"].items())[:15]:
            ext_table.add_row(ext, str(count))
        console.print(ext_table)

    # Windows drives breakdown
    if report["windows_drives"]:
        console.print("\n[bold]Windows Drives:[/bold]")
        for drive, count in report["windows_drives"].items():
            console.print(f"  {drive}:/ - {count} entries")

    # Show missing files
    if verbose and report["missing_files"]:
        console.print(f"\n[bold red]Missing files ({len(report['missing_files'])}):[/bold red]")
        for path in report["missing_files"][:20]:
            console.print(f"  [dim]{path}[/dim]")
        if len(report["missing_files"]) > 20:
            console.print(f"  [dim]... and {len(report['missing_files']) - 20} more[/dim]")

    # Show non-audio files
    if verbose and report["non_audio_files"]:
        console.print(f"\n[bold yellow]Non-audio files ({len(report['non_audio_files'])}):[/bold yellow]")
        for path in report["non_audio_files"][:20]:
            console.print(f"  [dim]{path}[/dim]")
        if len(report["non_audio_files"]) > 20:
            console.print(f"  [dim]... and {len(report['non_audio_files']) - 20} more[/dim]")


@db.command("clean")
@click.option("--non-audio", is_flag=True, help="Remove non-audio entries (zip, mp4, etc.)")
@click.option("--missing", is_flag=True, help="Remove entries with missing files")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
@click.option("--local", "db_choice", flag_value="local", help="Clean local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", help="Clean MyNVMe database")
def db_clean(non_audio: bool, missing: bool, dry_run: bool, db_choice: str):
    """Remove invalid entries from the database."""
    if not non_audio and not missing:
        console.print("[yellow]Specify --non-audio and/or --missing to clean[/yellow]")
        return

    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    # Create backup first
    if not dry_run:
        backup_mgr = BackupManager()
        backup_path = backup_mgr.create_backup(path, label="pre_clean")
        console.print(f"[green]✓[/green] Created backup: {backup_path}")

    db = get_database(path)
    validator = FileValidator()
    to_remove = []

    if non_audio:
        non_audio_songs = validator.find_non_audio_entries(db.iter_songs())
        to_remove.extend(non_audio_songs)
        console.print(f"Found {len(non_audio_songs)} non-audio entries")

    if missing:
        missing_songs = validator.find_missing_files(db.iter_songs())
        # Avoid duplicates
        existing_paths = {s.file_path for s in to_remove}
        for song in missing_songs:
            if song.file_path not in existing_paths:
                to_remove.append(song)
        console.print(f"Found {len(missing_songs)} entries with missing files")

    if not to_remove:
        console.print("[green]Nothing to clean![/green]")
        return

    console.print(f"\n[bold]Will remove {len(to_remove)} entries[/bold]")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes made[/yellow]")
        for song in to_remove[:20]:
            console.print(f"  [dim]{song.file_path}[/dim]")
        if len(to_remove) > 20:
            console.print(f"  [dim]... and {len(to_remove) - 20} more[/dim]")
        return

    # Confirm
    if not click.confirm(f"Remove {len(to_remove)} entries?"):
        console.print("[yellow]Cancelled[/yellow]")
        return

    # Remove entries
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Removing entries...", total=len(to_remove))

        removed = 0
        for song in to_remove:
            if db.remove_song(song.file_path):
                removed += 1
            progress.advance(task)

    db.save()
    console.print(f"[green]✓[/green] Removed {removed} entries")


# ============================================================================
# Files Commands
# ============================================================================


@cli.group()
def files():
    """File management operations."""
    pass


@files.command("scan")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--recursive/--no-recursive", default=True, help="Scan subdirectories")
def files_scan(directory: str, recursive: bool):
    """Preview new files in a directory."""
    dir_path = Path(directory)
    scanner = DirectoryScanner()

    console.print(f"[cyan]Scanning: {dir_path}[/cyan]")

    counts = scanner.count_files(dir_path, recursive=recursive)

    console.print(f"\nFound [bold]{counts['total']}[/bold] audio files")

    if counts["by_extension"]:
        table = Table(title="By Extension", show_header=True)
        table.add_column("Extension")
        table.add_column("Count", justify="right")

        for ext, count in counts["by_extension"].items():
            table.add_row(ext, str(count))

        console.print(table)


@files.command("import")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--recursive/--no-recursive", default=True, help="Scan subdirectories")
@click.option("--dry-run", is_flag=True, help="Show what would be imported")
@click.option("--local", "db_choice", flag_value="local", help="Import to local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Import to MyNVMe database")
def files_import(directory: str, recursive: bool, dry_run: bool, db_choice: str):
    """Add new files to the database."""
    dir_path = Path(directory)
    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)
    scanner = DirectoryScanner()

    existing_paths = set(db.songs.keys())
    new_files = scanner.find_new_files(dir_path, existing_paths, recursive=recursive)

    if not new_files:
        console.print("[green]No new files to import[/green]")
        return

    console.print(f"Found [bold]{len(new_files)}[/bold] new files to import")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes made[/yellow]")
        for f in new_files[:20]:
            console.print(f"  [dim]{f['file_path']}[/dim]")
        if len(new_files) > 20:
            console.print(f"  [dim]... and {len(new_files) - 20} more[/dim]")
        return

    # Create backup
    backup_mgr = BackupManager()
    backup_mgr.create_backup(path, label="pre_import")

    # Import files
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Importing files...", total=len(new_files))

        for file_info in new_files:
            db.add_song(file_info["file_path"], file_info["file_size"])
            progress.advance(task)

    db.save()
    console.print(f"[green]✓[/green] Imported {len(new_files)} files")


@files.command("remove")
@click.option("--missing", is_flag=True, help="Remove entries with missing files")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.option("--local", "db_choice", flag_value="local", help="Remove from local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Remove from MyNVMe database")
def files_remove(missing: bool, dry_run: bool, db_choice: str):
    """Remove entries from the database."""
    if not missing:
        console.print("[yellow]Specify --missing to remove entries[/yellow]")
        return

    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)
    validator = FileValidator()

    to_remove = validator.find_missing_files(db.iter_songs())

    if not to_remove:
        console.print("[green]No entries to remove[/green]")
        return

    console.print(f"Found [bold]{len(to_remove)}[/bold] entries with missing files")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes made[/yellow]")
        for song in to_remove[:20]:
            console.print(f"  [dim]{song.file_path}[/dim]")
        if len(to_remove) > 20:
            console.print(f"  [dim]... and {len(to_remove) - 20} more[/dim]")
        return

    if not click.confirm(f"Remove {len(to_remove)} entries?"):
        return

    # Create backup
    backup_mgr = BackupManager()
    backup_mgr.create_backup(path, label="pre_remove")

    # Remove entries
    removed = 0
    for song in to_remove:
        if db.remove_song(song.file_path):
            removed += 1

    db.save()
    console.print(f"[green]✓[/green] Removed {removed} entries")


@files.command("remap")
@click.argument("windows_prefix", required=False)
@click.argument("mac_prefix", required=False)
@click.option("--detect", is_flag=True, help="Detect Windows paths and show mappings")
@click.option("--interactive", is_flag=True, help="Interactive mapping mode")
@click.option("--apply", is_flag=True, help="Apply path remappings")
@click.option("--dry-run", is_flag=True, help="Show what would be remapped")
@click.option("--local", "db_choice", flag_value="local", help="Remap in local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Remap in MyNVMe database")
def files_remap(
    windows_prefix: Optional[str],
    mac_prefix: Optional[str],
    detect: bool,
    interactive: bool,
    apply: bool,
    dry_run: bool,
    db_choice: str,
):
    """Remap Windows paths to macOS paths."""
    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)
    remapper = PathRemapper()

    if detect:
        analysis = remapper.detect_mappable_paths(db.iter_songs())

        console.print(f"\n[bold]Windows Path Analysis[/bold]")
        console.print(f"Total Windows paths: {analysis['total_windows_paths']}")
        console.print(f"Mappable: {analysis['mappable']}")
        console.print(f"Unmappable: {analysis['unmappable']}")

        table = Table(title="Detected Prefixes", show_header=True)
        table.add_column("Windows Prefix")
        table.add_column("Count", justify="right")
        table.add_column("Has Mapping")
        table.add_column("Sample Exists")

        for prefix, info in sorted(analysis["by_prefix"].items()):
            has_mapping = "[green]Yes[/green]" if info["has_mapping"] else "[red]No[/red]"
            exists = "[green]Yes[/green]" if info["sample_exists"] else "[red]No[/red]"
            table.add_row(prefix, str(info["count"]), has_mapping, exists)

        console.print(table)
        return

    if interactive:
        # Interactive mapping mode
        prefixes = remapper.detect_windows_prefixes(db.iter_songs())

        for prefix, examples in sorted(prefixes.items()):
            console.print(f"\n[cyan]Prefix: {prefix}[/cyan] ({len(examples)} files)")
            console.print(f"Example: {examples[0]}")

            suggested = remapper.suggest_mapping(examples[0])
            console.print(f"Suggested: {suggested}")

            mac_path = click.prompt("macOS path (or 'skip')", default=suggested)

            if mac_path.lower() != "skip":
                remapper.add_mapping(prefix, mac_path)
                console.print(f"[green]✓[/green] Added mapping: {prefix} -> {mac_path}")

        apply = click.confirm("Apply these mappings?")

    if windows_prefix and mac_prefix:
        remapper.add_mapping(windows_prefix, mac_prefix)
        console.print(f"[green]✓[/green] Added mapping: {windows_prefix} -> {mac_prefix}")
        apply = not dry_run

    if apply:
        if not dry_run:
            backup_mgr = BackupManager()
            backup_mgr.create_backup(path, label="pre_remap")

        remapped = 0
        failed = 0

        # Convert to list first to avoid modifying dict during iteration
        songs_list = list(db.songs.values())
        for old_path, new_path, exists in remapper.remap_songs(iter(songs_list)):
            if dry_run:
                status = "[green]exists[/green]" if exists else "[red]missing[/red]"
                console.print(f"  {old_path}")
                console.print(f"    -> {new_path} ({status})")
            else:
                if db.remap_path(old_path, new_path):
                    remapped += 1
                else:
                    failed += 1

            if remapped + failed >= 10 and dry_run:
                remaining = len(songs_list) - 10
                if remaining > 0:
                    console.print(f"  ... and {remaining} more")
                break

        if not dry_run:
            db.save()
            console.print(f"[green]✓[/green] Remapped {remapped} paths ({failed} failed)")


@files.command("duplicates")
@click.option("--by-hash", is_flag=True, help="Find exact duplicates by file hash (slow)")
@click.option("--local", "db_choice", flag_value="local", help="Check local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Check MyNVMe database")
def files_duplicates(by_hash: bool, db_choice: str):
    """Find duplicate entries."""
    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)
    detector = DuplicateDetector()

    console.print("[cyan]Searching for duplicates...[/cyan]")

    songs_list = list(db.songs.values())
    results = detector.find_all_duplicates(songs_list, include_hash=by_hash)

    console.print(f"\n[bold]Duplicate Analysis[/bold]")
    console.print(f"By artist+title: {results['summary']['metadata_groups']} groups")
    console.print(f"By filename: {results['summary']['filename_groups']} groups")

    if by_hash:
        console.print(f"Exact duplicates: {results['summary']['exact_duplicates']} files")

    # Show metadata duplicates
    if results["by_metadata"]:
        console.print("\n[bold]By Artist + Title:[/bold]")
        for key, songs in list(results["by_metadata"].items())[:10]:
            artist, title = key.split("|")
            console.print(f"  {artist} - {title}")
            for song in songs:
                console.print(f"    [dim]{song.file_path}[/dim]")


# ============================================================================
# Analysis Commands
# ============================================================================


@cli.group()
def analyze():
    """Audio analysis operations."""
    pass


@analyze.command("energy")
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all tracks")
@click.option("--untagged", is_flag=True, help="Only tracks without energy")
@click.option("--dry-run", is_flag=True, help="Show what would be analyzed")
@click.option("--local", "db_choice", flag_value="local", help="Use local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Use MyNVMe database")
def analyze_energy(analyze_all: bool, untagged: bool, dry_run: bool, db_choice: str):
    """Analyze tracks for energy levels."""
    # Import here to avoid slow import on CLI startup
    try:
        from .analysis.energy import EnergyAnalyzer
    except ImportError as e:
        console.print(f"[red]Missing dependency: {e}[/red]")
        console.print("Install with: pip install librosa")
        return

    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)
    analyzer = EnergyAnalyzer()

    # Find tracks to analyze
    to_analyze = []
    for song in db.songs.values():
        if song.is_windows_path or song.is_netsearch:
            continue
        if not Path(song.file_path).exists():
            continue
        if untagged and song.energy is not None:
            continue
        to_analyze.append(song)

    if not to_analyze:
        console.print("[green]No tracks to analyze[/green]")
        return

    console.print(f"Found [bold]{len(to_analyze)}[/bold] tracks to analyze")

    if dry_run:
        console.print("[yellow]Dry run - no analysis performed[/yellow]")
        return

    # Create backup
    if not dry_run:
        backup_mgr = BackupManager()
        backup_mgr.create_backup(path, label="pre_energy")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Analyzing energy...", total=len(to_analyze))

        analyzed = 0
        for song in to_analyze:
            try:
                energy = analyzer.analyze(song.file_path)
                if energy is not None:
                    db.update_song_tags(song.file_path, Grouping=f"Energy {energy}")
                    analyzed += 1
            except Exception as e:
                console.print(f"[red]Error analyzing {song.file_path}: {e}[/red]")
            progress.advance(task)

    db.save()
    console.print(f"[green]✓[/green] Analyzed {analyzed} tracks")


@analyze.command("mood")
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all tracks")
@click.option("--dry-run", is_flag=True, help="Show what would be analyzed")
@click.option("--local", "db_choice", flag_value="local", help="Use local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Use MyNVMe database")
def analyze_mood(analyze_all: bool, dry_run: bool, db_choice: str):
    """Tag tracks with mood/emotion."""
    console.print("[yellow]Mood analysis requires essentia-tensorflow[/yellow]")
    console.print("Install with: pip install 'vdj-manager[mood]'")


@analyze.command("import-mik")
@click.option("--dry-run", is_flag=True, help="Show what would be imported")
@click.option("--local", "db_choice", flag_value="local", help="Use local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Use MyNVMe database")
def analyze_import_mik(dry_run: bool, db_choice: str):
    """Import existing Mixed In Key tags from audio files."""
    try:
        from .analysis.audio_features import MixedInKeyReader
    except ImportError as e:
        console.print(f"[red]Missing dependency: {e}[/red]")
        return

    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)
    reader = MixedInKeyReader()

    # Find tracks to check
    to_check = []
    for song in db.songs.values():
        if song.is_windows_path or song.is_netsearch:
            continue
        if not Path(song.file_path).exists():
            continue
        to_check.append(song)

    console.print(f"Checking [bold]{len(to_check)}[/bold] tracks for MIK data")

    if dry_run:
        console.print("[yellow]Dry run - no changes made[/yellow]")

    found = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Reading MIK tags...", total=len(to_check))

        for song in to_check:
            try:
                mik_data = reader.read_tags(song.file_path)
                if mik_data.get("energy") or mik_data.get("key"):
                    found += 1
                    if not dry_run:
                        updates = {}
                        if mik_data.get("energy") and not song.energy:
                            updates["Grouping"] = f"Energy {mik_data['energy']}"
                        if mik_data.get("key"):
                            updates["Key"] = mik_data["key"]
                        if updates:
                            db.update_song_tags(song.file_path, **updates)
            except Exception:
                pass
            progress.advance(task)

    if not dry_run and found > 0:
        db.save()

    console.print(f"[green]✓[/green] Found MIK data in {found} tracks")


# ============================================================================
# Tag Commands
# ============================================================================


@cli.group()
def tag():
    """Manual tag operations."""
    pass


@tag.command("set")
@click.argument("file_path")
@click.argument("tag_type", type=click.Choice(["energy", "mood", "key"]))
@click.argument("value")
@click.option("--local", "db_choice", flag_value="local", help="Use local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Use MyNVMe database")
def tag_set(file_path: str, tag_type: str, value: str, db_choice: str):
    """Set a tag value manually."""
    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)

    if file_path not in db.songs:
        console.print(f"[red]File not found in database: {file_path}[/red]")
        return

    # Create backup
    backup_mgr = BackupManager()
    backup_mgr.create_backup(path, label="pre_tag")

    if tag_type == "energy":
        try:
            energy = int(value)
            if not 1 <= energy <= 10:
                raise ValueError()
            db.update_song_tags(file_path, Grouping=f"Energy {energy}")
        except ValueError:
            console.print("[red]Energy must be 1-10[/red]")
            return
    elif tag_type == "mood":
        mood_hashtag = f"#{value}"
        song = db.get_song(file_path)
        existing = (song.tags.user2 or "") if song and song.tags else ""
        if mood_hashtag not in existing.split():
            new_user2 = f"{existing} {mood_hashtag}".strip()
        else:
            new_user2 = existing
        db.update_song_tags(file_path, User2=new_user2)
    elif tag_type == "key":
        db.update_song_tags(file_path, Key=value)

    db.save()
    console.print(f"[green]✓[/green] Set {tag_type}={value} for {Path(file_path).name}")


# ============================================================================
# Normalize Commands
# ============================================================================


@cli.group()
def normalize():
    """Audio normalization operations."""
    pass


@normalize.command("measure")
@click.option("--all", "measure_all", is_flag=True, help="Measure all tracks")
@click.option("--export", "export_csv", type=click.Path(), help="Export results to CSV")
@click.option("--workers", "-w", type=int, default=None, help="Number of parallel workers (default: CPU count - 1)")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of tracks to measure")
@click.option("--local", "db_choice", flag_value="local", help="Use local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Use MyNVMe database")
def normalize_measure(measure_all: bool, export_csv: Optional[str], workers: Optional[int], limit: Optional[int], db_choice: str):
    """Measure current loudness levels using parallel processing."""
    try:
        from .normalize.processor import NormalizationProcessor
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)
    processor = NormalizationProcessor(max_workers=workers)

    # Find tracks to measure
    to_measure = []
    for song in db.songs.values():
        if song.is_windows_path or song.is_netsearch:
            continue
        if not Path(song.file_path).exists():
            continue
        to_measure.append(song)

    if limit:
        to_measure = to_measure[:limit]

    console.print(f"Measuring [bold]{len(to_measure)}[/bold] tracks using [bold]{processor.max_workers}[/bold] workers")

    file_paths = [s.file_path for s in to_measure]
    results_data = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[bold blue]{task.fields[status]}"),
    ) as progress:
        task = progress.add_task("Measuring loudness...", total=len(to_measure), status="")

        def on_result(result):
            progress.advance(task)
            if result.success:
                # Find song info
                song = db.songs.get(result.file_path)
                results_data.append({
                    "file_path": result.file_path,
                    "artist": song.tags.author if song and song.tags else "",
                    "title": song.tags.title if song and song.tags else "",
                    "lufs": result.current_lufs,
                    "gain_needed": result.gain_db,
                })
                progress.update(task, status=f"LUFS: {result.current_lufs:.1f}")

        processor.measure_batch_parallel(file_paths, callback=on_result)

    # Show summary
    if results_data:
        lufs_values = [r["lufs"] for r in results_data if r["lufs"] is not None]
        if lufs_values:
            import statistics
            console.print(f"\n[bold]Loudness Summary[/bold]")
            console.print(f"Measured: {len(lufs_values)} tracks")
            console.print(f"Average: {statistics.mean(lufs_values):.1f} LUFS")
            console.print(f"Median: {statistics.median(lufs_values):.1f} LUFS")
            console.print(f"Range: {min(lufs_values):.1f} to {max(lufs_values):.1f} LUFS")
            console.print(f"Target: -14.0 LUFS (streaming standard)")

            # Count tracks needing adjustment
            gains = [r["gain_needed"] for r in results_data if r["gain_needed"] is not None]
            need_adj = sum(1 for g in gains if abs(g) > 1.0)
            console.print(f"Tracks needing adjustment (>1dB): {need_adj}")

    if export_csv and results_data:
        import csv
        with open(export_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file_path", "artist", "title", "lufs", "gain_needed"])
            writer.writeheader()
            writer.writerows(results_data)
        console.print(f"[green]✓[/green] Exported to {export_csv}")


@normalize.command("apply")
@click.argument("target", type=float, default=-14.0)
@click.option("--destructive", is_flag=True, help="Rewrite files (default: adjust VDJ volume)")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.option("--workers", "-w", type=int, default=None, help="Number of parallel workers (default: CPU count - 1)")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of tracks to process")
@click.option("--local", "db_choice", flag_value="local", help="Use local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Use MyNVMe database")
def normalize_apply(target: float, destructive: bool, dry_run: bool, workers: Optional[int], limit: Optional[int], db_choice: str):
    """Apply loudness normalization using parallel processing."""
    try:
        from .normalize.processor import NormalizationProcessor
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    processor = NormalizationProcessor(target_lufs=target, max_workers=workers)

    mode = "destructive" if destructive else "non-destructive"
    console.print(f"[cyan]Normalization mode: {mode}[/cyan]")
    console.print(f"Target: {target} LUFS")
    console.print(f"Workers: {processor.max_workers}")

    if destructive:
        console.print("[yellow]Warning: Destructive mode will modify audio files![/yellow]")
        if not dry_run and not click.confirm("Continue?"):
            return

    db = get_database(path)

    # Find tracks
    to_process = []
    for song in db.songs.values():
        if song.is_windows_path or song.is_netsearch:
            continue
        if not Path(song.file_path).exists():
            continue
        to_process.append(song)

    if limit:
        to_process = to_process[:limit]

    console.print(f"Processing [bold]{len(to_process)}[/bold] tracks")

    if dry_run:
        console.print("[yellow]Dry run - no changes made[/yellow]")
        return

    # Create backup
    backup_mgr = BackupManager()
    backup_mgr.create_backup(path, label="pre_normalize")

    file_paths = [s.file_path for s in to_process]
    successful = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[bold blue]{task.fields[status]}"),
    ) as progress:
        task = progress.add_task("Normalizing...", total=len(to_process), status="")

        def on_result(result):
            nonlocal successful, failed
            progress.advance(task)
            if result.success:
                successful += 1
                if not destructive and result.gain_db is not None:
                    # Store gain in VDJ Volume field for non-destructive mode
                    import math
                    volume = 10 ** (result.gain_db / 20)
                    db.update_song_scan(result.file_path, Volume=round(volume, 4))
                progress.update(task, status=f"OK: {result.gain_db:+.1f}dB")
            else:
                failed += 1
                progress.update(task, status=f"FAIL: {result.error[:30] if result.error else 'Unknown'}")

        if destructive:
            processor.normalize_batch_parallel(file_paths, backup=True, callback=on_result)
        else:
            processor.measure_batch_parallel(file_paths, callback=on_result)

    if not destructive:
        db.save()

    console.print(f"\n[green]✓[/green] Processed {successful} tracks")
    if failed > 0:
        console.print(f"[yellow]![/yellow] Failed: {failed} tracks")


# ============================================================================
# Export Commands
# ============================================================================


@cli.group()
def export():
    """Export to other DJ software."""
    pass


@export.command("serato")
@click.option("--all", "export_all", is_flag=True, help="Export entire library")
@click.option("--playlist", help="Export specific playlist")
@click.option("--cues-only", is_flag=True, help="Only export cue points/beatgrid")
@click.option("--dry-run", is_flag=True, help="Preview what would be exported")
@click.option("--local", "db_choice", flag_value="local", help="Use local database")
@click.option("--mynvme", "db_choice", flag_value="mynvme", default=True, help="Use MyNVMe database")
def export_serato(
    export_all: bool,
    playlist: Optional[str],
    cues_only: bool,
    dry_run: bool,
    db_choice: str,
):
    """Export library to Serato format."""
    try:
        from .export.serato import SeratoExporter
    except ImportError as e:
        console.print(f"[red]Missing dependency: {e}[/red]")
        console.print("Install with: pip install 'vdj-manager[serato]'")
        return

    path = LOCAL_VDJ_DB if db_choice == "local" else MYNVME_VDJ_DB

    if not path.exists():
        console.print(f"[red]Database not found: {path}[/red]")
        return

    db = get_database(path)
    exporter = SeratoExporter()

    if playlist:
        # Find playlist
        found = None
        for pl in db.playlists:
            if pl.name.lower() == playlist.lower():
                found = pl
                break

        if not found:
            console.print(f"[red]Playlist not found: {playlist}[/red]")
            console.print("Available playlists:")
            for pl in db.playlists:
                console.print(f"  - {pl.name}")
            return

        songs = [db.songs[fp] for fp in found.file_paths if fp in db.songs]
        console.print(f"Exporting playlist '{found.name}' ({len(songs)} tracks)")
    else:
        # Export all valid songs
        songs = [
            s for s in db.songs.values()
            if not s.is_windows_path and not s.is_netsearch and Path(s.file_path).exists()
        ]
        console.print(f"Exporting {len(songs)} tracks")

    if dry_run:
        console.print("[yellow]Dry run - no changes made[/yellow]")
        for song in songs[:10]:
            console.print(f"  {song.display_name}")
            if song.cue_points:
                console.print(f"    [dim]{len(song.cue_points)} cue points[/dim]")
        if len(songs) > 10:
            console.print(f"  ... and {len(songs) - 10} more")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Exporting to Serato...", total=len(songs))

        exported = 0
        for song in songs:
            try:
                exporter.export_song(song, cues_only=cues_only)
                exported += 1
            except Exception as e:
                console.print(f"[red]Error: {song.file_path}: {e}[/red]")
            progress.advance(task)

    if playlist:
        crate_path = exporter.create_crate(playlist, [s.file_path for s in songs])
        console.print(f"[green]✓[/green] Created crate: {crate_path}")

    console.print(f"[green]✓[/green] Exported {exported} tracks to Serato")


if __name__ == "__main__":
    cli()
