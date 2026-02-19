"""VDJ Manager Desktop Application entry point."""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from vdj_manager.ui.main_window import MainWindow
from vdj_manager.ui.state.checkpoint_manager import CheckpointManager
from vdj_manager.ui.theme import generate_stylesheet
from vdj_manager.ui.widgets.resume_dialog import check_and_show_resume_dialog


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create and configure the Qt application.

    Args:
        argv: Command line arguments. Uses sys.argv if not provided.

    Returns:
        Configured QApplication instance.
    """
    if argv is None:
        argv = sys.argv

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(argv)
    app.setApplicationName("VDJ Manager")
    app.setApplicationDisplayName("VDJ Manager")
    app.setOrganizationName("VDJ Manager")
    app.setOrganizationDomain("vdj-manager.local")

    return app


def main() -> int:
    """Main entry point for the VDJ Manager GUI.

    Returns:
        Exit code from the application.
    """
    from vdj_manager.config import setup_logging

    setup_logging(verbose=bool(os.environ.get("VDJ_VERBOSE")))

    app = create_application()
    app.setStyleSheet(generate_stylesheet())

    window = MainWindow()
    window.show()

    # Check for incomplete tasks
    checkpoint_manager = CheckpointManager()
    action, task = check_and_show_resume_dialog(checkpoint_manager, window)

    if action == "resume" and task:
        # Resume the task in the appropriate panel
        if task.task_type.value in ("normalize", "measure"):
            window.normalization_panel.resume_task(task)
            from vdj_manager.ui.constants import TabIndex

            window.tab_widget.setCurrentIndex(TabIndex.NORMALIZATION)
    elif action == "discard" and task:
        # Delete the selected checkpoint
        checkpoint_manager.delete(task.task_id)
    elif action == "discard_all":
        # Delete all incomplete checkpoints
        for incomplete in checkpoint_manager.list_incomplete():
            checkpoint_manager.delete(incomplete.task_id)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
