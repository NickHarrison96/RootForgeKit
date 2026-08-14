# =============================================================================
# NicksFix — iOS Forensic Backup & Restore Wizard Modal (PyQt6)
#
# Acquisition modes (ported from the iForensics toolkit):
#   Logical       mobilebackup2 iTunes-style backup
#   Logical+      Logical + media + crash reports + app inventory → .tar
#   PRFS          Partially Restored File System (collection without backup)
#   FFS           Full File System — needs SSH to a jailbroken device
# =============================================================================

import sys
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLineEdit,
    QLabel, QFileDialog, QTabWidget, QMessageBox, QWidget, QFrame,
    QCheckBox, QProgressBar, QRadioButton, QButtonGroup, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from components.progress_panel import OperationProgressPanel
from utils.process_runner import StreamingProcessRunner
from utils.ios_core.backup_engine import AcquisitionWorker, ACQUISITION_MODES


class BackupRestoreDialog(QDialog):
    """
    iOS Forensic Backup & Restore modal dialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("💾 iOS Forensic Backup & Restore Wizard")
        self.resize(780, 560)
        self.runner = StreamingProcessRunner(self)
        self.runner.finished.connect(self._on_operation_finished)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 10))

        # ── Tab 1: Create Backup ────────────────────────────────────────────
        backup_tab = QWidget()
        b_layout = QVBoxLayout(backup_tab)
        b_layout.setContentsMargins(14, 14, 14, 14)
        b_layout.setSpacing(12)

        lbl_b = QLabel("📥 Create Forensic Device Backup")
        lbl_b.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        b_layout.addWidget(lbl_b)

        lbl_b_desc = QLabel("Perform a full iTunes-compatible backup of the connected iOS device.")
        lbl_b_desc.setStyleSheet("color: #8b949e;")
        b_layout.addWidget(lbl_b_desc)

        dir_row = QHBoxLayout()
        self.backup_path_input = QLineEdit(os.path.abspath("backups"))
        dir_row.addWidget(self.backup_path_input, stretch=1)
        btn_browse_b = QPushButton("Browse...")
        btn_browse_b.clicked.connect(self._browse_backup_dir)
        dir_row.addWidget(btn_browse_b)
        b_layout.addLayout(dir_row)

        # ---- Acquisition mode ----
        mode_group = QGroupBox("Acquisition Mode")
        mode_grid = QGridLayout(mode_group)
        mode_grid.setContentsMargins(8, 4, 8, 8)
        mode_grid.setSpacing(4)

        self.mode_group = QButtonGroup(self)
        self.mode_buttons: dict[str, QRadioButton] = {}
        for row, (key, meta) in enumerate(ACQUISITION_MODES.items()):
            radio = QRadioButton(meta["label"])
            radio.setToolTip(meta["detail"])
            radio.setFixedWidth(96)
            self.mode_group.addButton(radio)
            self.mode_buttons[key] = radio
            radio.toggled.connect(self._on_mode_changed)

            summary = QLabel(meta["summary"])
            summary.setStyleSheet("color: #8b949e;")
            summary.setWordWrap(True)

            mode_grid.addWidget(radio, row, 0)
            mode_grid.addWidget(summary, row, 1)
        mode_grid.setColumnStretch(1, 1)
        b_layout.addWidget(mode_group)

        # ---- Components (Logical+ / PRFS only) ----
        self.components_group = QGroupBox("Include")
        comp_row = QHBoxLayout(self.components_group)
        comp_row.setContentsMargins(8, 4, 8, 8)
        comp_row.setSpacing(10)

        self.chk_media = QCheckBox("Camera media")
        self.chk_crash = QCheckBox("Crash reports")
        self.chk_apps = QCheckBox("App inventory")
        self.chk_keep = QCheckBox("Keep staging folder")
        self.chk_media.setChecked(True)
        self.chk_crash.setChecked(True)
        self.chk_apps.setChecked(True)
        self.chk_keep.setToolTip("Keep the uncompressed staging folder next to the .tar archive.")
        for chk in (self.chk_media, self.chk_crash, self.chk_apps, self.chk_keep):
            comp_row.addWidget(chk)
        comp_row.addStretch()
        b_layout.addWidget(self.components_group)

        self.btn_start_backup = QPushButton("🚀 Start Acquisition")
        self.btn_start_backup.clicked.connect(self._start_backup)
        b_layout.addWidget(self.btn_start_backup)

        self.b_status = QLabel("Ready to create backup.")
        self.b_status.setStyleSheet("color: #8b949e;")
        self.b_status.setWordWrap(True)
        b_layout.addWidget(self.b_status)
        b_layout.addStretch()

        # Set the default only now — toggling fires _on_mode_changed, which
        # needs components_group to already exist.
        self.mode_buttons["logical"].setChecked(True)
        self._on_mode_changed()

        self.tabs.addTab(backup_tab, "📥 Create Backup")

        # ── Tab 2: Restore Backup ───────────────────────────────────────────
        restore_tab = QWidget()
        r_layout = QVBoxLayout(restore_tab)
        r_layout.setContentsMargins(14, 14, 14, 14)
        r_layout.setSpacing(12)

        lbl_r = QLabel("📤 Restore Device Backup")
        lbl_r.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        r_layout.addWidget(lbl_r)

        lbl_r_desc = QLabel("Restore an existing backup to the connected iOS device.")
        lbl_r_desc.setStyleSheet("color: #8b949e;")
        r_layout.addWidget(lbl_r_desc)

        r_dir_row = QHBoxLayout()
        self.restore_path_input = QLineEdit()
        self.restore_path_input.setPlaceholderText("Select backup folder to restore...")
        r_dir_row.addWidget(self.restore_path_input, stretch=1)
        btn_browse_r = QPushButton("Browse...")
        btn_browse_r.clicked.connect(self._browse_restore_dir)
        r_dir_row.addWidget(btn_browse_r)
        r_layout.addLayout(r_dir_row)

        self.btn_start_restore = QPushButton("⚡ Start Backup Restore")
        self.btn_start_restore.clicked.connect(self._start_restore)
        r_layout.addWidget(self.btn_start_restore)

        self.r_status = QLabel("Select backup folder to restore.")
        self.r_status.setStyleSheet("color: #8b949e;")
        r_layout.addWidget(self.r_status)
        r_layout.addStretch()

        self.tabs.addTab(restore_tab, "📤 Restore Backup")

        layout.addWidget(self.tabs, stretch=1)

        # Shared progress panel — hidden until an operation starts
        self.progress = OperationProgressPanel()
        self.progress.bind(self.runner)
        layout.addWidget(self.progress)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _browse_backup_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Backup Target Folder", self.backup_path_input.text())
        if d:
            self.backup_path_input.setText(d)

    def _browse_restore_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Backup Folder to Restore", os.path.abspath("backups"))
        if d:
            self.restore_path_input.setText(d)

    def _selected_mode(self) -> str:
        for key, radio in self.mode_buttons.items():
            if radio.isChecked():
                return key
        return "logical"

    def _on_mode_changed(self):
        """Component checkboxes only apply to the collection modes."""
        mode = self._selected_mode()
        self.components_group.setEnabled(mode in ("logical_plus", "prfs"))

    def _busy(self) -> bool:
        if self.runner.is_running():
            return True
        worker = getattr(self, "_acq_worker", None)
        return bool(worker and worker.isRunning())

    def _start_backup(self):
        if self._busy():
            QMessageBox.information(self, "Busy", "An operation is already running.")
            return

        target_dir = self.backup_path_input.text().strip()
        if not target_dir:
            QMessageBox.warning(self, "Missing Directory", "Select a valid target backup directory.")
            return

        os.makedirs(target_dir, exist_ok=True)
        mode = self._selected_mode()
        meta = ACQUISITION_MODES[mode]

        if mode == "ffs":
            QMessageBox.information(
                self, "FFS Unavailable",
                "Full File System acquisition requires SSH access to a "
                "jailbroken device, which this build does not configure.\n\n"
                "Use Logical+ or PRFS instead.",
            )
            return

        self.b_status.setText(f"{meta['label']} running — do not disconnect the device.")
        self._set_controls_enabled(False)
        self.progress.begin(f"📥  {meta['label']} acquisition")

        if mode == "logical":
            # Single streamed command; no timeout — a full backup can run for an hour.
            self.runner.start(["-m", "pymobiledevice3", "backup2", "backup",
                               "--full", target_dir])
            return

        # Multi-step collection modes run through the acquisition engine.
        options = {
            "incl_media": self.chk_media.isChecked(),
            "incl_crash": self.chk_crash.isChecked(),
            "incl_apps": self.chk_apps.isChecked(),
            "keep_intermediate": self.chk_keep.isChecked(),
        }
        self._acq_worker = AcquisitionWorker(mode, target_dir, options, parent=self)
        self.progress.bind(self._acq_worker)
        self._acq_worker.finished.connect(self._on_operation_finished)
        self._acq_worker.start()

    def _start_restore(self):
        if self._busy():
            QMessageBox.information(self, "Busy", "An operation is already running.")
            return

        restore_dir = self.restore_path_input.text().strip()
        if not restore_dir or not os.path.isdir(restore_dir):
            QMessageBox.warning(self, "Invalid Directory", "Select a valid existing backup folder.")
            return

        confirm = QMessageBox.warning(
            self, "Confirm Restore",
            "Restoring overwrites data on the connected device.\n\n"
            f"Restore from:\n{restore_dir}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.r_status.setText("Restore running — do not disconnect the device.")
        self._set_controls_enabled(False)
        self.progress.begin("📤  Restoring device backup")
        self.runner.start(["-m", "pymobiledevice3", "backup2", "restore", restore_dir])

    def _set_controls_enabled(self, enabled: bool):
        self.btn_start_backup.setEnabled(enabled)
        self.btn_start_restore.setEnabled(enabled)

    def _on_operation_finished(self, ok: bool, message: str):
        self._set_controls_enabled(True)
        status = message if ok else f"Failed — {message}"
        self.b_status.setText(status)
        self.r_status.setText(status)
