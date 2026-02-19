"""Shared test fixtures and configuration."""

import gc
import sys

import pytest


def pytest_configure(config):
    """Set multiprocessing start method to 'spawn' for macOS Qt compatibility.

    On macOS, fork() after Qt threads are created causes segfaults because
    forked processes inherit the parent's thread state (including Qt's
    internal threads) in a broken state. Using 'spawn' avoids this entirely.
    """
    if sys.platform == "darwin":
        import multiprocessing

        try:
            multiprocessing.set_start_method("spawn", force=True)
        except RuntimeError:
            pass  # Already set


@pytest.fixture(autouse=True)
def _qt_cleanup():
    """Clean up Qt state after each test to prevent cross-test segfaults.

    Qt workers started in tests may leave behind queued signals and
    C++ objects. Without cleanup, processEvents() in a later test can
    deliver signals to already-deleted objects, causing segfaults.
    """
    yield
    try:
        from PySide6.QtCore import QCoreApplication

        app = QCoreApplication.instance()
        if app is not None:
            app.processEvents()
    except ImportError:
        pass
    # Force garbage collection to release any Qt wrappers whose
    # C++ counterparts are still alive
    gc.collect()
