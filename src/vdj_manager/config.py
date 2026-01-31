"""Configuration management for VDJ Manager."""

from pathlib import Path
from typing import Optional

# Default paths
LOCAL_VDJ_DB = Path.home() / "Library/Application Support/VirtualDJ/database.xml"
MYNVME_VDJ_DB = Path("/Volumes/MyNVMe/VirtualDJ/database.xml")
BACKUP_DIR = Path.home() / ".vdj_manager/backups"
SERATO_LOCAL = Path.home() / "Music/_Serato_"
SERATO_MYNVME = Path("/Volumes/MyNVMe/_Serato_")

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


# Global config instance
config = Config()
