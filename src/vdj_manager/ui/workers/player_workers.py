"""Background workers for the player panel."""

import numpy as np
from PySide6.QtCore import QThread, Signal


class WaveformWorker(QThread):
    """Generate waveform peaks in a background thread.

    Signals:
        peaks_ready(str, object): (file_path, numpy peak array)
        error(str, str): (file_path, error message)
    """

    peaks_ready = Signal(str, object)
    error = Signal(str, str)

    def __init__(self, file_path: str, width: int = 800, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self._width = width

    def run(self) -> None:
        try:
            from vdj_manager.player.waveform import generate_waveform_peaks, WaveformCache

            cache = WaveformCache()
            cached = cache.get(self._file_path, self._width)
            if cached is not None:
                self.peaks_ready.emit(self._file_path, cached)
                return

            peaks = generate_waveform_peaks(self._file_path, self._width)
            cache.put(self._file_path, peaks, self._width)
            self.peaks_ready.emit(self._file_path, peaks)
        except Exception as e:
            self.error.emit(self._file_path, str(e))
