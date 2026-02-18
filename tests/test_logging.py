"""Tests for centralized logging setup."""

import logging
from logging.handlers import RotatingFileHandler
from unittest.mock import patch


class TestSetupLogging:
    """Tests for config.setup_logging()."""

    def setup_method(self):
        # Clear any existing handlers on the vdj_manager logger
        logger = logging.getLogger("vdj_manager")
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)  # Reset

    def teardown_method(self):
        # Clean up after each test
        logger = logging.getLogger("vdj_manager")
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)

    def test_creates_log_directory(self, tmp_path):
        """setup_logging should create the log directory."""
        from vdj_manager.config import setup_logging

        log_dir = tmp_path / "logs"
        with patch("vdj_manager.config.LOG_DIR", log_dir):
            setup_logging()
        assert log_dir.exists()

    def test_attaches_two_handlers(self, tmp_path):
        """Should add console + file handlers."""
        from vdj_manager.config import setup_logging

        log_dir = tmp_path / "logs"
        with patch("vdj_manager.config.LOG_DIR", log_dir):
            setup_logging()

        logger = logging.getLogger("vdj_manager")
        assert len(logger.handlers) == 2
        handler_types = {type(h) for h in logger.handlers}
        assert logging.StreamHandler in handler_types
        assert RotatingFileHandler in handler_types

    def test_idempotent(self, tmp_path):
        """Calling setup_logging twice should not duplicate handlers."""
        from vdj_manager.config import setup_logging

        log_dir = tmp_path / "logs"
        with patch("vdj_manager.config.LOG_DIR", log_dir):
            setup_logging()
            setup_logging()

        logger = logging.getLogger("vdj_manager")
        assert len(logger.handlers) == 2

    def test_verbose_sets_console_debug(self, tmp_path):
        """verbose=True should set console handler to DEBUG."""
        from vdj_manager.config import setup_logging

        log_dir = tmp_path / "logs"
        with patch("vdj_manager.config.LOG_DIR", log_dir):
            setup_logging(verbose=True)

        logger = logging.getLogger("vdj_manager")
        console = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        ][0]
        assert console.level == logging.DEBUG

    def test_non_verbose_sets_console_info(self, tmp_path):
        """verbose=False should set console handler to INFO."""
        from vdj_manager.config import setup_logging

        log_dir = tmp_path / "logs"
        with patch("vdj_manager.config.LOG_DIR", log_dir):
            setup_logging(verbose=False)

        logger = logging.getLogger("vdj_manager")
        console = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        ][0]
        assert console.level == logging.INFO

    def test_file_handler_always_debug(self, tmp_path):
        """File handler should always be DEBUG regardless of verbose flag."""
        from vdj_manager.config import setup_logging

        log_dir = tmp_path / "logs"
        with patch("vdj_manager.config.LOG_DIR", log_dir):
            setup_logging(verbose=False)

        logger = logging.getLogger("vdj_manager")
        file_h = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)][0]
        assert file_h.level == logging.DEBUG

    def test_child_loggers_inherit(self, tmp_path):
        """Child loggers should use parent handlers."""
        from vdj_manager.config import setup_logging

        log_dir = tmp_path / "logs"
        with patch("vdj_manager.config.LOG_DIR", log_dir):
            setup_logging()

        child = logging.getLogger("vdj_manager.analysis.energy")
        # Child should have no handlers of its own but inherit from parent
        assert len(child.handlers) == 0
        assert child.parent.name == "vdj_manager"
        assert len(child.parent.handlers) == 2

    def test_log_file_created(self, tmp_path):
        """A log file should be created in the log directory."""
        from vdj_manager.config import setup_logging

        log_dir = tmp_path / "logs"
        with patch("vdj_manager.config.LOG_DIR", log_dir):
            setup_logging()

        logger = logging.getLogger("vdj_manager")
        logger.info("test message")

        log_file = log_dir / "vdj_manager.log"
        assert log_file.exists()
        assert "test message" in log_file.read_text()
