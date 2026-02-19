"""Album art delegate and cache for the track table."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, QObject, QRect, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

_THUMB_SIZE = 40
_PLACEHOLDER_KEY = "__placeholder__"


class _ArtLoadSignals(QObject):
    """Signals for the art loading runnable (QRunnable can't emit signals directly)."""

    art_loaded = Signal(str, QImage)  # file_path, image (QImage is thread-safe)


class _ArtLoadRunnable(QRunnable):
    """Background runnable that extracts album art from an audio file."""

    def __init__(self, file_path: str, size: int = _THUMB_SIZE) -> None:
        super().__init__()
        self.file_path = file_path
        self.size = size
        self.signals = _ArtLoadSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            from vdj_manager.player.album_art import extract_album_art

            art_bytes = extract_album_art(self.file_path)
            if art_bytes:
                img = QImage()
                img.loadFromData(art_bytes)
                if not img.isNull():
                    # Scale using QImage (thread-safe), NOT QPixmap
                    scaled = img.scaled(
                        self.size,
                        self.size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.signals.art_loaded.emit(self.file_path, scaled)
                    return
        except Exception:
            logger.debug("Failed to load album art for %s", self.file_path)
        # Emit empty image to signal "no art" (so we don't retry)
        self.signals.art_loaded.emit(self.file_path, QImage())


class AlbumArtCache(QObject):
    """FIFO cache for album art pixmaps with async background loading.

    Signals:
        art_ready(str): Emitted when art for a file_path becomes available.
    """

    art_ready = Signal(str)  # file_path

    def __init__(self, max_size: int = 500, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache: dict[str, QPixmap | None] = {}
        self._pending: set[str] = set()
        self._active_runnables: dict[str, _ArtLoadRunnable] = {}
        self._max_size = max_size
        self._pool = QThreadPool.globalInstance()
        self._placeholder: QPixmap | None = None

    def get(self, file_path: str) -> QPixmap | None:
        """Get cached pixmap for file_path, or None if not yet loaded.

        Triggers async loading if not cached and not already pending.
        """
        if file_path in self._cache:
            return self._cache[file_path]

        # Trigger async load
        if file_path not in self._pending:
            self._pending.add(file_path)
            runnable = _ArtLoadRunnable(file_path)
            runnable.signals.art_loaded.connect(self._on_art_loaded)
            # Hold reference to prevent signal object deletion before slot fires
            self._active_runnables[file_path] = runnable
            self._pool.start(runnable)

        return None

    def get_placeholder(self) -> QPixmap:
        """Get or create a placeholder pixmap for tracks without art."""
        if self._placeholder is None:
            self._placeholder = self._create_placeholder()
        return self._placeholder

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._pending.clear()
        self._active_runnables.clear()

    def _on_art_loaded(self, file_path: str, image: QImage) -> None:
        """Handle completed art load. Converts QImage to QPixmap on main thread."""
        self._pending.discard(file_path)
        self._active_runnables.pop(file_path, None)

        # Evict oldest if at capacity
        if len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        # Convert QImage→QPixmap on main thread (QPixmap is NOT thread-safe)
        if not image.isNull():
            self._cache[file_path] = QPixmap.fromImage(image)
        else:
            # Store None for empty image (no art found) to avoid re-fetching
            self._cache[file_path] = None
        self.art_ready.emit(file_path)

    @staticmethod
    def _create_placeholder() -> QPixmap:
        """Create a simple placeholder pixmap with a music note."""
        from vdj_manager.ui.theme import DARK_THEME

        pixmap = QPixmap(_THUMB_SIZE, _THUMB_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.GlobalColor.transparent)
        painter.setPen(Qt.PenStyle.NoPen)

        # Draw rounded rect background
        from PySide6.QtGui import QColor

        painter.setBrush(QColor(DARK_THEME.bg_surface_alt))
        painter.drawRoundedRect(0, 0, _THUMB_SIZE, _THUMB_SIZE, 4, 4)

        # Draw music note
        painter.setPen(QColor(DARK_THEME.text_muted))
        font = painter.font()
        font.setPixelSize(20)
        painter.setFont(font)
        painter.drawText(
            QRect(0, 0, _THUMB_SIZE, _THUMB_SIZE),
            Qt.AlignmentFlag.AlignCenter,
            "\u266b",
        )
        painter.end()
        return pixmap


class AlbumArtDelegate(QStyledItemDelegate):
    """Delegate that paints album art thumbnails in the track table."""

    def __init__(self, cache: AlbumArtCache, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        # Draw selection/focus background
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter)

        file_path = index.data(Qt.ItemDataRole.UserRole + 1)  # AlbumArtRole
        if not file_path:
            return

        pixmap = self._cache.get(file_path)
        if pixmap is None or pixmap.isNull():
            pixmap = self._cache.get_placeholder()

        # Center the pixmap in the cell
        x = option.rect.x() + (option.rect.width() - pixmap.width()) // 2
        y = option.rect.y() + (option.rect.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> Any:
        from PySide6.QtCore import QSize

        return QSize(_THUMB_SIZE + 4, _THUMB_SIZE + 4)
