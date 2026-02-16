"""Auto-download Essentia model files for MTG-Jamendo mood analysis.

Downloads the EffNet-Discogs embedding model and MTG-Jamendo MoodTheme
classification head to ~/.vdj_manager/models/ on first use.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

MODELS_DIR = Path.home() / ".vdj_manager" / "models"

# Essentia model URLs (official UPF repository)
_BASE_URL = "https://essentia.upf.edu/models"

EMBEDDING_MODEL = {
    "filename": "discogs-effnet-bs64-1.pb",
    "url": f"{_BASE_URL}/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb",
    "sha256": None,  # Skip hash check — file may be updated upstream
}

CLASSIFIER_MODEL = {
    "filename": "mtg_jamendo_moodtheme-discogs-effnet-1.pb",
    "url": (
        f"{_BASE_URL}/classification-heads/mtg_jamendo_moodtheme/"
        "mtg_jamendo_moodtheme-discogs-effnet-1.pb"
    ),
    "sha256": None,
}


def models_available() -> bool:
    """Check if model files already exist locally (no network call)."""
    embedding_path = MODELS_DIR / EMBEDDING_MODEL["filename"]
    classifier_path = MODELS_DIR / CLASSIFIER_MODEL["filename"]
    return embedding_path.exists() and classifier_path.exists()


def ensure_model_files() -> tuple[Path, Path]:
    """Download model files if missing.

    Returns:
        Tuple of (embedding_model_path, classifier_model_path).

    Raises:
        OSError: If download fails.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    embedding_path = _ensure_single_model(EMBEDDING_MODEL)
    classifier_path = _ensure_single_model(CLASSIFIER_MODEL)

    return embedding_path, classifier_path


def _ensure_single_model(model_info: dict) -> Path:
    """Download a single model file if it doesn't exist."""
    dest = MODELS_DIR / model_info["filename"]
    if dest.exists():
        logger.debug("Model already exists: %s", dest)
        return dest

    url = model_info["url"]
    logger.info("Downloading model: %s", url)

    # Download to temp file, then rename (atomic-ish)
    tmp_path = dest.with_suffix(".tmp")
    try:
        # 5-minute timeout prevents hanging on stalled connections
        with urllib.request.urlopen(url, timeout=300) as response:
            with open(tmp_path, "wb") as out:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)

        # Verify hash if provided
        expected_hash = model_info.get("sha256")
        if expected_hash:
            actual_hash = _sha256(tmp_path)
            if actual_hash != expected_hash:
                tmp_path.unlink(missing_ok=True)
                raise OSError(
                    f"Hash mismatch for {model_info['filename']}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )

        tmp_path.rename(dest)
        logger.info("Downloaded model to: %s", dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return dest


def _sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
