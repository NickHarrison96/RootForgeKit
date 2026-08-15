# =============================================================================
# RootForgeKit — iOS Crash Reports Explorer Modal (PySide6)
# AFC Crash Report service browser, stack trace viewer, and bulk download
# =============================================================================

import sys
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QFileDialog, QPlainTextEdit, QMessageBox,
    QSplitter, QWidget, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from utils.resource_manager import safe_run_command


class CrashLogsWorker(QThread):
    logs_loaded = Signal(list)
    error_signal = Signal(str)

    def run(self):
        ok, out = safe_run_command([sys.executable, "-m", "pymobiledevice3", "crash", "ls"], timeout=15)
        if not ok:
            ok, out = safe_run_command(["pymobiledevice3", "crash", "ls"], timeout=15)

        if not ok:
            self.error_signal.emit(f"Failed to query crash logs:\n{out}")
            return

        lines = [l.strip() for l in out.splitlines() if l.strip()]
        self.logs_loaded.emit(lines)


class CrashReportsDialog(QDialog):
    """
    iOS Crash Reports Explorer modal dialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🩺 iOS Crash Reports Explorer")
        self.resize(900, 580)
        self._init_ui()
        self._load_crash_logs()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        top_row = QHBoxLayout()
        lbl_title = QLabel("🩺 Crash Reports & Stack Traces")
        lbl_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        top_row.addWidget(lbl_title)

        self.status_label = QLabel("Loading crash reports...")
        self.status_label.setStyleSheet("color: #8b949e;")
        top_row.addWidget(self.status_label, stretch=1)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._load_crash_logs)
        top_row.addWidget(btn_refresh)
        layout.addLayout(top_row)

        # Main splitter (left: log list, right: log preview)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)

        # Left panel
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Consolas", 9))
        self.list_widget.setStyleSheet("background-color: #161b22; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px;")
        self.list_widget.itemClicked.connect(self._on_log_selected)
        left_layout.addWidget(self.list_widget)

        splitter.addWidget(left_widget)

        # Right panel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.text_preview = QPlainTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setFont(QFont("Consolas", 9))
        self.text_preview.setStyleSheet("background-color: #0d1117; color: #7ee787; border: 1px solid #30363d; border-radius: 6px;")
        right_layout.addWidget(self.text_preview)

        splitter.addWidget(right_widget)
        splitter.setSizes([320, 580])
        layout.addWidget(splitter, stretch=1)

        # Bottom actions
        bottom_row = QHBoxLayout()
        btn_export = QPushButton("💾 Export Selected Crash Log")
        btn_export.clicked.connect(self._export_selected_log)
        bottom_row.addWidget(btn_export)

        btn_export_all = QPushButton("📦 Bulk Download All Crash Logs")
        btn_export_all.clicked.connect(self._export_all_logs)
        bottom_row.addWidget(btn_export_all)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addLayout(bottom_row)

    def _load_crash_logs(self):
        self.status_label.setText("Querying crash reports via AFC...")
        self.list_widget.clear()
        self.text_preview.clear()

        self._worker = CrashLogsWorker()
        self._worker.logs_loaded.connect(self._on_logs_loaded)
        self._worker.error_signal.connect(self._on_logs_error)
        self._worker.start()

    def _on_logs_loaded(self, logs):
        for log in logs:
            self.list_widget.addItem(log)
        self.status_label.setText(f"Found {len(logs)} crash report(s)")

    def _on_logs_error(self, err_msg):
        self.status_label.setText("Failed loading crash reports")
        QMessageBox.warning(self, "Crash Logs Error", err_msg)

    def _on_log_selected(self, item: QListWidgetItem):
        log_name = item.text()
        self.status_label.setText(f"Reading {log_name}...")
        ok, out = safe_run_command([sys.executable, "-m", "pymobiledevice3", "crash", "show", log_name], timeout=15)
        if ok:
            self.text_preview.setPlainText(out)
            self.status_label.setText(f"Loaded {log_name}")
        else:
            self.text_preview.setPlainText(f"Failed to read crash log:\n{out}")

    def _export_selected_log(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "Select Log", "Select a crash log to export.")
            return

        log_name = item.text()
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Crash Log", log_name, "Text Files (*.ips *.crash *.txt);;All Files (*)")
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(self.text_preview.toPlainText())
            QMessageBox.information(self, "Success", f"Crash log saved to:\n{save_path}")

    def _export_all_logs(self):
        target_dir = QFileDialog.getExistingDirectory(self, "Select Bulk Crash Export Directory")
        if target_dir:
            self.status_label.setText("Downloading all crash reports...")
            ok, out = safe_run_command([sys.executable, "-m", "pymobiledevice3", "crash", "pull", target_dir], timeout=60)
            if ok:
                QMessageBox.information(self, "Success", f"All crash logs exported to:\n{target_dir}")
            else:
                QMessageBox.critical(self, "Export Error", f"Failed bulk downloading crash logs:\n{out}")
