"""Base operation panel with standard layout for database operations."""

from abc import abstractmethod
from typing import Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QGroupBox,
    QLabel,
    QSplitter,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from vdj_manager.core.database import VDJDatabase
from vdj_manager.ui.widgets.progress_widget import ProgressWidget


class OperationPanel(QWidget):
    """Base class for operation panels with standard layout.

    Provides a consistent layout pattern:
    - Configuration group (subclass-defined controls)
    - Start/Cancel buttons
    - Progress widget
    - Status label

    Subclasses must implement:
    - _create_config_widgets(): Return the config widget(s)
    - _start_operation(): Start the background worker
    - _operation_name(): Return the name of the operation

    Signals:
        operation_started: Emitted when an operation begins
        operation_finished: Emitted when an operation completes (success, message)
    """

    operation_started = Signal()
    operation_finished = Signal(bool, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._database: VDJDatabase | None = None
        self._worker: Any = None
        self._setup_ui()

    @property
    def database(self) -> VDJDatabase | None:
        return self._database

    def set_database(self, database: VDJDatabase | None) -> None:
        """Set the database for this panel.

        Args:
            database: VDJDatabase instance, or None to clear.
        """
        self._database = database
        self._on_database_changed()

    def _on_database_changed(self) -> None:
        """Called when the database is set or cleared. Override to update UI."""
        has_db = self._database is not None
        self.start_btn.setEnabled(has_db)

    @abstractmethod
    def _operation_name(self) -> str:
        """Return the name of this operation (e.g., 'Backup', 'Validate')."""
        raise NotImplementedError

    @abstractmethod
    def _create_config_widgets(self) -> QWidget | None:
        """Create configuration widgets for this operation.

        Returns:
            A widget containing config controls, or None for no config.
        """
        raise NotImplementedError

    @abstractmethod
    def _start_operation(self) -> None:
        """Start the background operation. Should create and start the worker."""
        raise NotImplementedError

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Config group
        config_widget = self._create_config_widgets()
        if config_widget is not None:
            config_group = QGroupBox("Configuration")
            config_layout = QVBoxLayout(config_group)
            config_layout.addWidget(config_widget)
            layout.addWidget(config_group)

        # Button row
        button_layout = QHBoxLayout()

        self.start_btn = QPushButton(f"Start {self._operation_name()}")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start_clicked)
        button_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        button_layout.addWidget(self.cancel_btn)

        button_layout.addStretch()

        # Status label
        self.status_label = QLabel("")
        button_layout.addWidget(self.status_label)

        layout.addLayout(button_layout)

        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        self.progress_widget = ProgressWidget()
        progress_layout.addWidget(self.progress_widget)
        layout.addWidget(progress_group)

        layout.addStretch()

    def _on_start_clicked(self) -> None:
        if self._database is None:
            QMessageBox.warning(self, "No Database", "Please load a database first.")
            return
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(
                self, "Already Running",
                f"{self._operation_name()} is already in progress.",
            )
            return

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText("Running...")
        self.operation_started.emit()
        self._start_operation()

    def _on_cancel_clicked(self) -> None:
        if self._worker is not None and hasattr(self._worker, "cancel"):
            self._worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Cancelling...")

    @Slot(bool, str)
    def _on_operation_finished(self, success: bool, message: str) -> None:
        """Handle operation completion. Connect this to worker's finished signal."""
        self.start_btn.setEnabled(self._database is not None)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText(message)
        self.operation_finished.emit(success, message)

    @Slot(str)
    def _on_operation_error(self, error_msg: str) -> None:
        """Handle operation error. Connect this to worker's error signal."""
        self.start_btn.setEnabled(self._database is not None)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText(f"Error: {error_msg}")
        self.operation_finished.emit(False, error_msg)

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()
