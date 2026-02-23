"""UI constants for VDJ Manager Desktop Application."""

from enum import IntEnum


class TabIndex(IntEnum):
    """Tab indices for the main window tab widget.

    Using IntEnum so values work directly with QTabWidget.setCurrentIndex().
    Centralizes tab indices to avoid hardcoded magic numbers.
    """

    DATABASE = 0
    NORMALIZATION = 1
    FILES = 2
    ANALYSIS = 3
    EXPORT = 4
    PLAYER = 5
    WORKFLOW = 6
