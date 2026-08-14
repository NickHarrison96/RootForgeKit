# =============================================================================
# NicksFix — iOS IPSW Restore & Firmware Flashing Modal (PyQt6)
# idevicerestore wrapper for flashing IPSW images to iOS devices
# =============================================================================

import sys
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QFileDialog, QPlainTextEdit, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from utils.resource_manager import safe_run_command


class IpswRestoreWorker(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, ipsw_path: str, erase: bool = False):
        super().__init__()
        self.ipsw_path = ipsw_path
        self.erase = erase

    def run(self):
        cmd = ["idevicerestore"]
        if self.erase:
            cmd.append("-e")  # Erase/Full restore
        cmd.append(self.ipsw_path)
        ok, out = safe_run_command(cmd, timeout=900)
        self.finished_signal.emit(ok, out)


class IpswRestoreDialog(QDialog):
    """
    iOS IPSW Restore & Firmware Flashing modal dialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚡ iOS IPSW Restore & Firmware Flashing")
        self.resize(780, 500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        lbl_title = QLabel("⚡ IPSW Firmware Restore Engine")
        lbl_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        lbl_desc = QLabel("Flash custom or official Apple IPSW firmware files using idevicerestore.")
        lbl_desc.setStyleSheet("color: #8b949e;")
        layout.addWidget(lbl_desc)

        # File selection row
        file_row = QHBoxLayout()
        self.ipsw_input = QLineEdit()
        self.ipsw_input.setPlaceholderText("Select .ipsw firmware file...")
        file_row.addWidget(self.ipsw_input, stretch=1)

        btn_browse = QPushButton("Browse IPSW...")
        btn_browse.clicked.connect(self._browse_ipsw)
        file_row.addWidget(btn_browse)
        layout.addLayout(file_row)

        # Options
        self.chk_erase = QCheckBox("Full Erase && Restore (Wipes user data for clean flash)")
        layout.addWidget(self.chk_erase)

        # Start button
        self.btn_flash = QPushButton("🚀 Start IPSW Restore")
        self.btn_flash.clicked.connect(self._start_flash)
        layout.addWidget(self.btn_flash)

        # Log box
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QFont("Consolas", 9))
        self.log_console.setStyleSheet("background-color: #0d1117; color: #7ee787; border: 1px solid #30363d; border-radius: 6px;")
        layout.addWidget(self.log_console, stretch=1)

        # Close
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _browse_ipsw(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select IPSW Firmware File", "", "IPSW Files (*.ipsw);;All Files (*)")
        if filename:
            self.ipsw_input.setText(filename)

    def _start_flash(self):
        ipsw_path = self.ipsw_input.text().strip()
        if not ipsw_path or not os.path.isfile(ipsw_path):
            QMessageBox.warning(self, "Missing File", "Select a valid .ipsw firmware file.")
            return

        reply = QMessageBox.warning(
            self, "⚠️ Confirm Firmware Restore",
            f"Are you sure you want to flash IPSW:\n{ipsw_path}\n\nThis will reboot the device into restore mode.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log_console.appendPlainText(f"[*] Starting IPSW restore process for {ipsw_path}...")
        self.btn_flash.setEnabled(False)

        self._worker = IpswRestoreWorker(ipsw_path, self.chk_erase.isChecked())
        self._worker.finished_signal.connect(self._on_flash_finished)
        self._worker.start()

    def _on_flash_finished(self, ok: bool, output: str):
        self.btn_flash.setEnabled(True)
        if ok:
            self.log_console.appendPlainText(f"[+] Flash Success:\n{output}\n")
            QMessageBox.information(self, "Success", "IPSW Restore finished successfully!")
        else:
            self.log_console.appendPlainText(f"[-] Flash Failed:\n{output}\n")
            QMessageBox.critical(self, "Restore Error", f"IPSW Restore failed:\n{output}")
