"""Configuration management for VDJ Manager."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Default paths
LOCAL_VDJ_DB = Path.home() / "Library/Application Support/VirtualDJ/database.xml"
MYNVME_VDJ_DB = Path("/Volumes/MyNVMe/VirtualDJ/database.xml")
BACKUP_DIR = Path.home() / ".vdj_manager/backups"
CHECKPOINT_DIR = Path.home() / ".vdj_manager/checkpoints"
LOG_DIR = Path.home() / ".vdj_manager/logs"
SERATO_LOCAL = Path.home() / "Music/_Serato_"
SERATO_MYNVME = Path("/Volumes/MyNVMe/_Serato_")

# Last.fm API key
LASTFM_API_KEY_ENV = "LASTFM_API_KEY"
LASTFM_API_KEY_FILE = Path.home() / ".vdj_manager/lastfm_api_key"


def get_lastfm_api_key() -> Optional[str]:
    """Get the Last.fm API key from environment variable or file.

    Checks the LASTFM_API_KEY environment variable first, then falls
    back to ~/.vdj_manager/lastfm_api_key file.

    Returns:
        API key string, or None if not configured.
    """
    import os

    key = os.environ.get(LASTFM_API_KEY_ENV)
    if key:
        return key.strip()
    if LASTFM_API_KEY_FILE.exists():
        return LASTFM_API_KEY_FILE.read_text().strip() or None
    return None

# Audio file extensions
AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".aac", ".flac", ".wav", ".aiff", ".aif",
    ".ogg", ".opus", ".wma", ".alac"
}

# Non-audio extensions to clean
NON_AUDIO_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".pdf", ".doc", ".docx", ".txt",
    ".exe", ".dmg", ".pkg", ".app",
    ".db", ".xml", ".json", ".nfo",
}

# Windows to macOS path mappings
DEFAULT_PATH_MAPPINGS = {
    # MyNVMe database mappings (D:/ = MyNVMe on Windows)
    "D:/Main/": "/Volumes/MyNVMe/Main/",
    "D:/NewMusic/": "/Volumes/MyNVMe/NewMusic/",
    "D:/deezer/": "/Volumes/MyNVMe/deezer/",
    "D:/All December 2022/": "/Volumes/MyNVMe/All December 2022/",
    "D:/Zoukables/": "/Volumes/MyNVMe/Zoukables/",
    # Local database mappings (E:/ also maps to MyNVMe)
    "E:/Main/": "/Volumes/MyNVMe/Main/",
    "E:/": "/Volumes/MyNVMe/",
}

# Energy analysis parameters
ENERGY_WEIGHTS = {
    "tempo": 0.35,
    "rms": 0.35,
    "spectral": 0.30,
}

# Normalization targets
DEFAULT_LUFS_TARGET = -14.0  # Streaming standard


class Config:
    """Application configuration."""

    def __init__(
        self,
        local_db: Optional[Path] = None,
        mynvme_db: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
    ):
        self.local_db = local_db or LOCAL_VDJ_DB
        self.mynvme_db = mynvme_db or MYNVME_VDJ_DB
        self.backup_dir = backup_dir or BACKUP_DIR

    @property
    def primary_db(self) -> Path:
        """Return the primary (MyNVMe) database if available, else local."""
        if self.mynvme_db.exists():
            return self.mynvme_db
        return self.local_db

    def ensure_backup_dir(self) -> Path:
        """Create backup directory if it doesn't exist."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        return self.backup_dir


def setup_logging(verbose: bool = False) -> None:
    """Configure centralized logging with console and file handlers.

    Sets up the ``vdj_manager`` logger namespace with a rotating file
    handler (``~/.vdj_manager/logs/vdj_manager.log``) and a console
    handler. All child loggers (e.g. ``vdj_manager.analysis.energy``)
    inherit these handlers automatically.

    Args:
        verbose: If True, set console level to DEBUG; otherwise INFO.
                 The file handler always captures DEBUG.
    """
    level = logging.DEBUG if verbose else logging.INFO

    root = logging.getLogger("vdj_manager")
    root.setLevel(logging.DEBUG)

    # Avoid duplicate handlers on repeated calls
    if root.handlers:
        return

    log_format = "%(asctime)s %(name)s %(levelname)s %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root.addHandler(console)

    # Rotating file handler: 5 MB max, keep 3 backups
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_DIR / "vdj_manager.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root.addHandler(file_handler)


# Global config instance
config = Config()
