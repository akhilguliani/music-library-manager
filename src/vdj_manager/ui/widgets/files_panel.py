"""File management panel with scan, import, remove, remap, and duplicates."""

from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vdj_manager.core.database import VDJDatabase
from vdj_manager.core.models import Song
from vdj_manager.files.path_remapper import PathRemapper
from vdj_manager.files.validator import FileValidator
from vdj_manager.ui.widgets.results_table import ConfigurableResultsTable
from vdj_manager.ui.workers.file_workers import (
    DuplicateWorker,
    ImportWorker,
    RemapWorker,
    RemoveWorker,
    ScanWorker,
)


class FilesPanel(QWidget):
    """Panel for file management operations.

    Sub-tabs:
    - Scan: Preview new files in a directory
    - Import: Add scanned files to database
    - Remove: Remove missing/invalid entries
    - Remap: Remap Windows paths to macOS
    - Duplicates: Find duplicate entries

    Signals:
        database_changed: Emitted when database is modified
    """

    database_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._database: VDJDatabase | None = None
        self._tracks: list[Song] = []
        self._scanned_files: list[dict] = []
        self._scan_worker: ScanWorker | None = None
        self._import_worker: ImportWorker | None = None
        self._remove_worker: RemoveWorker | None = None
        self._remap_worker: RemapWorker | None = None
        self._duplicate_worker: DuplicateWorker | None = None
        self._setup_ui()

    def set_database(self, database: VDJDatabase | None) -> None:
        self._database = database
        if database is not None:
            self._tracks = list(database.iter_songs())
        else:
            self._tracks = []
        self._update_button_states()

    def _update_button_states(self) -> None:
        has_db = self._database is not None
        self.scan_btn.setEnabled(True)  # Scan doesn't need db
        self.import_btn.setEnabled(has_db and len(self._scanned_files) > 0)
        self.remove_btn.setEnabled(has_db)
        self.remap_detect_btn.setEnabled(has_db)
        self.remap_apply_btn.setEnabled(has_db)
        self.dup_scan_btn.setEnabled(has_db)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.addTab(self._create_scan_tab(), "Scan")
        self.sub_tabs.addTab(self._create_import_tab(), "Import")
        self.sub_tabs.addTab(self._create_remove_tab(), "Remove")
        self.sub_tabs.addTab(self._create_remap_tab(), "Remap")
        self.sub_tabs.addTab(self._create_duplicates_tab(), "Duplicates")

        layout.addWidget(self.sub_tabs)

    # ---- Scan Tab ----
    def _create_scan_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Directory picker
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Directory:"))
        self.scan_dir_input = QLineEdit()
        self.scan_dir_input.setPlaceholderText("Select directory to scan...")
        dir_layout.addWidget(self.scan_dir_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_scan_browse)
        dir_layout.addWidget(browse_btn)
        layout.addLayout(dir_layout)

        # Options row
        opts_layout = QHBoxLayout()
        self.scan_recursive = QCheckBox("Recursive")
        self.scan_recursive.setChecked(True)
        opts_layout.addWidget(self.scan_recursive)

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        opts_layout.addWidget(self.scan_btn)

        self.scan_status = QLabel("")
        opts_layout.addWidget(self.scan_status)
        opts_layout.addStretch()
        layout.addLayout(opts_layout)

        # Results
        self.scan_results = ConfigurableResultsTable(
            [
                {"name": "File", "key": "name", "tooltip_key": "file_path"},
                {"name": "Size", "key": "size"},
                {"name": "Extension", "key": "extension"},
            ]
        )
        layout.addWidget(self.scan_results)

        return widget

    def _on_scan_browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if directory:
            self.scan_dir_input.setText(directory)

    def _on_scan_clicked(self) -> None:
        directory = self.scan_dir_input.text().strip()
        if not directory or not Path(directory).is_dir():
            QMessageBox.warning(self, "Invalid Directory", "Please select a valid directory.")
            return

        existing = set()
        if self._database is not None:
            existing = {s.file_path for s in self._database.iter_songs()}

        self.scan_btn.setEnabled(False)
        self.scan_status.setText("Scanning...")
        self.scan_results.clear()

        self._scan_worker = ScanWorker(Path(directory), existing, self.scan_recursive.isChecked())
        self._scan_worker.finished_work.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    @Slot(object)
    def _on_scan_finished(self, files: list[dict]) -> None:
        self.scan_btn.setEnabled(True)
        self._scanned_files = files
        self.scan_status.setText(f"Found {len(files)} new files")

        for f in files:
            size_kb = f.get("file_size", 0) / 1024
            self.scan_results.add_result(
                {
                    "name": f.get("name", ""),
                    "file_path": f.get("file_path", ""),
                    "size": f"{size_kb:.0f} KB",
                    "extension": f.get("extension", ""),
                }
            )

        self._update_button_states()

    @Slot(str)
    def _on_scan_error(self, error: str) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_status.setText(f"Error: {error}")

    # ---- Import Tab ----
    def _create_import_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel("Import scanned files into the database. Run Scan first.")
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("Import Scanned Files")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self._on_import_clicked)
        btn_layout.addWidget(self.import_btn)

        self.import_status = QLabel("")
        btn_layout.addWidget(self.import_status)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.import_results = ConfigurableResultsTable(
            [
                {"name": "File", "key": "file"},
                {
                    "name": "Status",
                    "key": "status",
                    "color_fn": lambda v: QColor("green") if v == "OK" else QColor("red"),
                },
            ]
        )
        layout.addWidget(self.import_results)

        return widget

    def _on_import_clicked(self) -> None:
        if self._database is None or not self._scanned_files:
            return

        paths = [f["file_path"] for f in self._scanned_files]

        self.import_btn.setEnabled(False)
        self.import_status.setText(f"Importing {len(paths)} files...")
        self.import_results.clear()

        self._import_worker = ImportWorker(paths)
        self._import_worker.finished_work.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    @Slot(object)
    def _on_import_finished(self, result: dict) -> None:
        # Apply mutations on main thread
        paths_to_add = result.get("paths_to_add", [])
        added = 0
        failed = 0
        for path in paths_to_add:
            try:
                self._database.add_song(path)
                added += 1
            except Exception:
                failed += 1

        if added > 0:
            self._database.save()

        self.import_status.setText(f"Imported {added} files ({failed} failed)")
        self.import_btn.setEnabled(False)  # Can't re-import

        for f in self._scanned_files:
            self.import_results.add_result(
                {
                    "file": f.get("name", ""),
                    "status": "OK",
                }
            )

        self._scanned_files = []
        self._tracks = list(self._database.iter_songs()) if self._database else []
        self.database_changed.emit()

    @Slot(str)
    def _on_import_error(self, error: str) -> None:
        self.import_btn.setEnabled(True)
        self.import_status.setText(f"Error: {error}")

    # ---- Remove Tab ----
    def _create_remove_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel("Remove entries from the database.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.remove_missing_only = QCheckBox("Missing files only")
        self.remove_missing_only.setChecked(True)
        layout.addWidget(self.remove_missing_only)

        btn_layout = QHBoxLayout()
        self.remove_btn = QPushButton("Find & Remove")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        btn_layout.addWidget(self.remove_btn)

        self.remove_status = QLabel("")
        btn_layout.addWidget(self.remove_status)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()
        return widget

    def _on_remove_clicked(self) -> None:
        if self._database is None:
            return

        validator = FileValidator()
        if self.remove_missing_only.isChecked():
            to_remove = validator.find_missing_files(iter(self._tracks))
        else:
            categories = validator.categorize_entries(iter(self._tracks))
            to_remove = categories.get("audio_missing", []) + categories.get("non_audio", [])

        if not to_remove:
            QMessageBox.information(self, "Nothing to Remove", "No entries to remove.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove {len(to_remove)} entries? A backup will be created first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from vdj_manager.core.backup import BackupManager

        try:
            BackupManager().create_backup(self._database.db_path, label="pre_remove")
        except Exception as e:
            QMessageBox.warning(self, "Backup Failed", str(e))
            return

        paths = [s.file_path for s in to_remove]
        self.remove_btn.setEnabled(False)
        self.remove_status.setText(f"Removing {len(paths)} entries...")

        self._remove_worker = RemoveWorker(paths)
        self._remove_worker.finished_work.connect(self._on_remove_finished)
        self._remove_worker.error.connect(self._on_remove_error)
        self._remove_worker.start()

    @Slot(object)
    def _on_remove_finished(self, result: dict) -> None:
        # Apply mutations on main thread
        paths_to_remove = result.get("paths_to_remove", [])
        removed = 0
        for path in paths_to_remove:
            if self._database.remove_song(path):
                removed += 1
        if removed > 0:
            self._database.save()

        self.remove_btn.setEnabled(True)
        self.remove_status.setText(f"Removed {removed} entries")
        self._tracks = list(self._database.iter_songs()) if self._database else []
        self.database_changed.emit()

    @Slot(str)
    def _on_remove_error(self, error: str) -> None:
        self.remove_btn.setEnabled(True)
        self.remove_status.setText(f"Error: {error}")

    # ---- Remap Tab ----
    def _create_remap_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()
        self.remap_win_input = QLineEdit()
        self.remap_win_input.setPlaceholderText("e.g., D:/Music/")
        form.addRow("Windows Prefix:", self.remap_win_input)

        self.remap_mac_input = QLineEdit()
        self.remap_mac_input.setPlaceholderText("e.g., /Volumes/MyNVMe/Music/")
        form.addRow("Mac Prefix:", self.remap_mac_input)
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self.remap_detect_btn = QPushButton("Detect")
        self.remap_detect_btn.setEnabled(False)
        self.remap_detect_btn.setToolTip("Auto-detect Windows prefixes from database")
        self.remap_detect_btn.clicked.connect(self._on_remap_detect)
        btn_layout.addWidget(self.remap_detect_btn)

        self.remap_apply_btn = QPushButton("Apply Remap")
        self.remap_apply_btn.setEnabled(False)
        self.remap_apply_btn.clicked.connect(self._on_remap_apply)
        btn_layout.addWidget(self.remap_apply_btn)

        self.remap_status = QLabel("")
        btn_layout.addWidget(self.remap_status)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.remap_results = ConfigurableResultsTable(
            [
                {"name": "Old Path", "key": "old_path"},
                {"name": "New Path", "key": "new_path"},
                {
                    "name": "Exists",
                    "key": "exists",
                    "color_fn": lambda v: QColor("green") if v == "Yes" else QColor("orange"),
                },
            ]
        )
        layout.addWidget(self.remap_results)

        return widget

    def _on_remap_detect(self) -> None:
        if not self._tracks:
            return
        remapper = PathRemapper()
        prefixes = remapper.detect_windows_prefixes(iter(self._tracks))

        if prefixes:
            first_prefix = list(prefixes.keys())[0]
            self.remap_win_input.setText(first_prefix)
            suggestion = remapper.suggest_mapping(first_prefix)
            self.remap_mac_input.setText(suggestion)
            self.remap_status.setText(f"Found {len(prefixes)} Windows prefix(es)")
        else:
            self.remap_status.setText("No Windows paths found")

    def _on_remap_apply(self) -> None:
        if self._database is None:
            return

        win_prefix = self.remap_win_input.text().strip()
        mac_prefix = self.remap_mac_input.text().strip()
        if not win_prefix or not mac_prefix:
            QMessageBox.warning(self, "Missing Prefixes", "Enter both Windows and Mac prefixes.")
            return

        remapper = PathRemapper({win_prefix: mac_prefix})

        # Preview
        self.remap_results.clear()
        mappable = [
            s for s in self._tracks if s.is_windows_path and remapper.can_remap(s.file_path)
        ]

        if not mappable:
            QMessageBox.information(self, "Nothing to Remap", "No paths match the given prefix.")
            return

        for s in mappable[:100]:  # Preview first 100
            new_path = remapper.remap_path(s.file_path)
            self.remap_results.add_result(
                {
                    "old_path": s.file_path,
                    "new_path": new_path or "-",
                    "exists": "Yes" if new_path and Path(new_path).exists() else "No",
                }
            )

        reply = QMessageBox.question(
            self,
            "Confirm Remap",
            f"Remap {len(mappable)} paths? A backup will be created first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from vdj_manager.core.backup import BackupManager

        try:
            BackupManager().create_backup(self._database.db_path, label="pre_remap")
        except Exception as e:
            QMessageBox.warning(self, "Backup Failed", str(e))
            return

        self.remap_apply_btn.setEnabled(False)
        self.remap_status.setText("Remapping...")

        self._remap_worker = RemapWorker(mappable, remapper)
        self._remap_worker.finished_work.connect(self._on_remap_finished)
        self._remap_worker.error.connect(self._on_remap_error)
        self._remap_worker.start()

    @Slot(object)
    def _on_remap_finished(self, result: dict) -> None:
        # Apply mutations on main thread
        remappings = result.get("remappings", [])
        remapped = 0
        failed = 0
        for old_path, new_path in remappings:
            try:
                if self._database.remap_path(old_path, new_path):
                    remapped += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        if remapped > 0:
            self._database.save()

        self.remap_apply_btn.setEnabled(True)
        self.remap_status.setText(
            f"Remapped {remapped}, skipped {result.get('skipped', 0)}, " f"failed {failed}"
        )
        self._tracks = list(self._database.iter_songs()) if self._database else []
        self.database_changed.emit()

    @Slot(str)
    def _on_remap_error(self, error: str) -> None:
        self.remap_apply_btn.setEnabled(True)
        self.remap_status.setText(f"Error: {error}")

    # ---- Duplicates Tab ----
    def _create_duplicates_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Options
        opts_layout = QHBoxLayout()
        self.dup_metadata = QCheckBox("By metadata")
        self.dup_metadata.setChecked(True)
        opts_layout.addWidget(self.dup_metadata)

        self.dup_filename = QCheckBox("By filename")
        self.dup_filename.setChecked(True)
        opts_layout.addWidget(self.dup_filename)

        self.dup_hash = QCheckBox("By hash (slow)")
        opts_layout.addWidget(self.dup_hash)

        self.dup_scan_btn = QPushButton("Find Duplicates")
        self.dup_scan_btn.setEnabled(False)
        self.dup_scan_btn.clicked.connect(self._on_dup_scan)
        opts_layout.addWidget(self.dup_scan_btn)

        self.dup_status = QLabel("")
        opts_layout.addWidget(self.dup_status)
        opts_layout.addStretch()
        layout.addLayout(opts_layout)

        # Results
        self.dup_results = ConfigurableResultsTable(
            [
                {"name": "File", "key": "file", "tooltip_key": "path"},
                {"name": "Match Type", "key": "match_type"},
                {"name": "Group", "key": "group"},
            ]
        )
        layout.addWidget(self.dup_results)

        return widget

    def _on_dup_scan(self) -> None:
        if not self._tracks:
            return

        self.dup_scan_btn.setEnabled(False)
        self.dup_status.setText("Scanning for duplicates...")
        self.dup_results.clear()

        self._duplicate_worker = DuplicateWorker(
            self._tracks,
            by_metadata=self.dup_metadata.isChecked(),
            by_filename=self.dup_filename.isChecked(),
            by_hash=self.dup_hash.isChecked(),
        )
        self._duplicate_worker.finished_work.connect(self._on_dup_finished)
        self._duplicate_worker.error.connect(self._on_dup_error)
        self._duplicate_worker.start()

    @Slot(object)
    def _on_dup_finished(self, result: dict) -> None:
        self.dup_scan_btn.setEnabled(True)

        summary = result.get("summary", {})
        meta_groups = summary.get("metadata_groups", 0)
        file_groups = summary.get("filename_groups", 0)
        exact = summary.get("exact_duplicates", 0)

        self.dup_status.setText(
            f"Metadata: {meta_groups} groups, Filename: {file_groups} groups, Exact: {exact}"
        )

        # Show metadata duplicates
        by_metadata = result.get("by_metadata", {})
        for group_idx, (key, songs) in enumerate(by_metadata.items()):
            for song in songs:
                self.dup_results.add_result(
                    {
                        "file": Path(song.file_path).name,
                        "path": song.file_path,
                        "match_type": "Metadata",
                        "group": str(group_idx + 1),
                    }
                )

        # Show filename duplicates
        by_filename = result.get("by_filename", {})
        for group_idx, (key, songs) in enumerate(by_filename.items()):
            for song in songs:
                self.dup_results.add_result(
                    {
                        "file": Path(song.file_path).name,
                        "path": song.file_path,
                        "match_type": "Filename",
                        "group": str(group_idx + 1),
                    }
                )

    @Slot(str)
    def _on_dup_error(self, error: str) -> None:
        self.dup_scan_btn.setEnabled(True)
        self.dup_status.setText(f"Error: {error}")
