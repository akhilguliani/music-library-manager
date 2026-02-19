"""Tests for OperationPanel base class and ProgressSimpleWorker."""

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from vdj_manager.ui.widgets.operation_panel import OperationPanel
from vdj_manager.ui.workers.base_worker import ProgressSimpleWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class ConcretePanel(OperationPanel):
    """Concrete subclass for testing."""

    def _operation_name(self) -> str:
        return "Test"

    def _create_config_widgets(self) -> QWidget | None:
        label = QLabel("Config goes here")
        return label

    def _start_operation(self) -> None:
        pass


class NullConfigPanel(OperationPanel):
    """Panel with no config widgets."""

    def _operation_name(self) -> str:
        return "NullTest"

    def _create_config_widgets(self) -> QWidget | None:
        return None

    def _start_operation(self) -> None:
        pass


class ConcreteProgressWorker(ProgressSimpleWorker):
    """Concrete subclass for testing."""

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self.items = items or []

    def do_work(self):
        results = []
        for i, item in enumerate(self.items):
            if self.is_cancelled:
                return results
            self.report_progress(i + 1, len(self.items), f"Processing {item}")
            results.append(item.upper())
        return results


class TestOperationPanel:
    """Tests for OperationPanel base class."""

    def test_creation(self, qapp):
        panel = ConcretePanel()
        assert panel.start_btn is not None
        assert panel.cancel_btn is not None
        assert panel.progress_widget is not None
        assert panel.status_label is not None

    def test_start_button_disabled_without_database(self, qapp):
        panel = ConcretePanel()
        assert not panel.start_btn.isEnabled()

    def test_start_button_enabled_with_database(self, qapp):
        panel = ConcretePanel()
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        panel.set_database(mock_db)
        assert panel.start_btn.isEnabled()

    def test_set_database_none_disables(self, qapp):
        panel = ConcretePanel()
        from unittest.mock import MagicMock

        panel.set_database(MagicMock())
        assert panel.start_btn.isEnabled()
        panel.set_database(None)
        assert not panel.start_btn.isEnabled()

    def test_null_config_panel(self, qapp):
        panel = NullConfigPanel()
        assert panel.start_btn is not None
        # Should not have a Configuration group box
        assert panel.start_btn.text() == "Start NullTest"

    def test_operation_name_in_button(self, qapp):
        panel = ConcretePanel()
        assert panel.start_btn.text() == "Start Test"

    def test_is_running_false_by_default(self, qapp):
        panel = ConcretePanel()
        assert not panel.is_running()

    def test_on_operation_finished(self, qapp):
        panel = ConcretePanel()
        from unittest.mock import MagicMock

        panel.set_database(MagicMock())

        panel._on_operation_finished(True, "Done!")
        assert panel.status_label.text() == "Done!"
        assert panel.start_btn.isEnabled()
        assert not panel.cancel_btn.isEnabled()

    def test_on_operation_error(self, qapp):
        panel = ConcretePanel()
        panel._on_operation_error("Something broke")
        assert "Something broke" in panel.status_label.text()


class TestProgressSimpleWorker:
    """Tests for ProgressSimpleWorker."""

    def test_worker_runs_and_finishes(self, qapp):
        worker = ConcreteProgressWorker(items=["a", "b", "c"])
        results = []
        worker.finished_work.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(results) == 1
        assert results[0] == ["A", "B", "C"]

    def test_worker_emits_progress(self, qapp):
        worker = ConcreteProgressWorker(items=["x", "y"])
        progress_updates = []
        worker.progress.connect(lambda c, t, m: progress_updates.append((c, t, m)))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(progress_updates) == 2
        assert progress_updates[0] == (1, 2, "Processing x")
        assert progress_updates[1] == (2, 2, "Processing y")

    def test_worker_cancel(self, qapp):
        worker = ConcreteProgressWorker(items=["a", "b", "c"])
        worker.cancel()
        assert worker.is_cancelled

    def test_worker_error_handling(self, qapp):
        class FailingWorker(ProgressSimpleWorker):
            def do_work(self):
                raise ValueError("test error")

        worker = FailingWorker()
        errors = []
        worker.error.connect(lambda e: errors.append(e))
        worker.start()
        worker.wait(5000)
        QCoreApplication.processEvents()

        assert len(errors) == 1
        assert "test error" in errors[0]
