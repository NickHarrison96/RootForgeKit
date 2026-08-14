# =============================================================================
# NicksFix — Mobile Interactive Modals & Step-by-Step Guides
# =============================================================================

import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QLabel, QFileDialog, QTabWidget,
    QTextBrowser, QFrame, QMessageBox, QPlainTextEdit
)
from PyQt6.QtCore import Qt, QProcess
from PyQt6.QtGui import QFont, QTextCursor

from utils.resource_manager import safe_run_command


class AdbFileExplorerDialog(QDialog):
    """
    Interactive ADB Remote File Explorer dialog supporting folder navigation,
    file downloading (Pull) and file uploading (Push).
    """

    def __init__(self, device_id: str = "", parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self.current_path = "/sdcard"
        self.setWindowTitle(f"ADB File Explorer {f'[{device_id}]' if device_id else ''}")
        self.resize(750, 520)
        self._init_ui()
        self._load_directory(self.current_path)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ── Navigation bar ──────────────────────────────────────────────────
        nav_layout = QHBoxLayout()
        btn_up = QPushButton("⬆ Up")
        btn_up.setObjectName("MobileQuickBtn")
        btn_up.clicked.connect(self._navigate_up)
        nav_layout.addWidget(btn_up)

        self.path_input = QLineEdit(self.current_path)
        self.path_input.returnPressed.connect(self._on_go_clicked)
        nav_layout.addWidget(self.path_input, stretch=1)

        btn_go = QPushButton("Go")
        btn_go.setObjectName("MobileQuickBtn")
        btn_go.clicked.connect(self._on_go_clicked)
        nav_layout.addWidget(btn_go)

        btn_refresh = QPushButton("🔄")
        btn_refresh.setToolTip("Refresh current directory")
        btn_refresh.clicked.connect(lambda: self._load_directory(self.current_path))
        nav_layout.addWidget(btn_refresh)

        layout.addLayout(nav_layout)

        # ── File List View ──────────────────────────────────────────────────
        self.file_list = QListWidget()
        self.file_list.setFont(QFont("Consolas", 10))
        self.file_list.setStyleSheet(
            "background-color: #161b22; color: #e6edf3; border: 1px solid #30363d; "
            "border-radius: 6px; padding: 6px;"
        )
        self.file_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.file_list, stretch=1)

        # ── Status and Action Toolbar ────────────────────────────────────────
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #8b949e;")
        bottom_layout.addWidget(self.status_label, stretch=1)

        btn_pull = QPushButton("📥 Pull File")
        btn_pull.setToolTip("Download selected file to PC")
        btn_pull.clicked.connect(self._pull_file)
        bottom_layout.addWidget(btn_pull)

        btn_push = QPushButton("📤 Push File")
        btn_push.setToolTip("Upload file from PC to current directory")
        btn_push.clicked.connect(self._push_file)
        bottom_layout.addWidget(btn_push)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

    def _adb_cmd(self, args: list[str], timeout: int = 10) -> tuple[bool, str]:
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)
        return safe_run_command(cmd, timeout=timeout)

    def _load_directory(self, path: str):
        self.status_label.setText(f"Loading {path}...")
        self.file_list.clear()

        # Sanitize path
        path = path.strip() or "/"
        ok, out = self._adb_cmd(["shell", "ls", "-la", path], timeout=8)
        if not ok:
            self.status_label.setText(f"Failed to list directory: {out}")
            return

        self.current_path = path
        self.path_input.setText(path)

        lines = out.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("total "):
                continue

            # Check if directory or file
            is_dir = line_str.startswith("d") or line_str.startswith("l")
            parts = line_str.split()
            if len(parts) >= 8:
                filename = " ".join(parts[7:])
            else:
                filename = line_str

            if filename in (".", ".."):
                continue

            display_icon = "📁 " if is_dir else "📄 "
            item = QListWidgetItem(f"{display_icon}{filename}")
            item.setData(Qt.ItemDataRole.UserRole, (filename, is_dir))
            self.file_list.addItem(item)

        self.status_label.setText(f"Loaded {self.file_list.count()} item(s)")

    def _navigate_up(self):
        if self.current_path == "/" or not self.current_path:
            return
        parent_dir = os.path.dirname(self.current_path.rstrip("/"))
        self._load_directory(parent_dir or "/")

    def _on_go_clicked(self):
        target = self.path_input.text().strip()
        self._load_directory(target)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        filename, is_dir = item.data(Qt.ItemDataRole.UserRole)
        if is_dir:
            # Handle symlinks if formatted like 'foo -> bar'
            clean_name = filename.split(" -> ")[0]
            new_path = (self.current_path.rstrip("/") + "/" + clean_name).replace("//", "/")
            self._load_directory(new_path)
        else:
            self._pull_file()

    def _pull_file(self):
        item = self.file_list.currentItem()
        if not item:
            QMessageBox.information(self, "Select File", "Please select a file to pull.")
            return

        filename, is_dir = item.data(Qt.ItemDataRole.UserRole)
        if is_dir:
            QMessageBox.warning(self, "Directory Selected", "Folder download is not supported. Select a file.")
            return

        clean_name = filename.split(" -> ")[0]
        remote_file_path = (self.current_path.rstrip("/") + "/" + clean_name).replace("//", "/")

        save_path, _ = QFileDialog.getSaveFileName(self, "Save Pulled File", clean_name)
        if not save_path:
            return

        self.status_label.setText(f"Pulling {clean_name}...")
        ok, out = self._adb_cmd(["pull", remote_file_path, save_path], timeout=30)
        if ok:
            self.status_label.setText(f"Successfully pulled to {save_path}")
            QMessageBox.information(self, "Success", f"File pulled successfully!\nSaved to: {save_path}")
        else:
            self.status_label.setText("Pull failed")
            QMessageBox.critical(self, "Error", f"Failed to pull file:\n{out}")

    def _push_file(self):
        local_path, _ = QFileDialog.getOpenFileName(self, "Select File to Push to Device")
        if not local_path:
            return

        filename = os.path.basename(local_path)
        remote_target = (self.current_path.rstrip("/") + "/" + filename).replace("//", "/")

        self.status_label.setText(f"Pushing {filename}...")
        ok, out = self._adb_cmd(["push", local_path, remote_target], timeout=30)
        if ok:
            self.status_label.setText(f"Successfully pushed {filename}")
            QMessageBox.information(self, "Success", f"File pushed successfully to {remote_target}")
            self._load_directory(self.current_path)
        else:
            self.status_label.setText("Push failed")
            QMessageBox.critical(self, "Error", f"Failed to push file:\n{out}")


class IosModeGuideDialog(QDialog):
    """
    Step-by-step interactive visual guide for putting iOS devices into DFU Mode or Recovery Mode.
    """

    def __init__(self, mode: str = "recovery", parent=None):
        super().__init__(parent)
        self.mode = mode.lower()
        self.setWindowTitle("iOS Device Hardware Guide")
        self.resize(700, 500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget()

        # ── Recovery Mode Guide Tab ─────────────────────────────────────────
        recovery_browser = QTextBrowser()
        recovery_browser.setOpenExternalLinks(True)
        recovery_browser.setHtml(self._get_recovery_html())
        self.tabs.addTab(recovery_browser, "🔑 Recovery Mode Guide")

        # ── DFU Mode Guide Tab ───────────────────────────────────────────────
        dfu_browser = QTextBrowser()
        dfu_browser.setOpenExternalLinks(True)
        dfu_browser.setHtml(self._get_dfu_html())
        self.tabs.addTab(dfu_browser, "🔓 DFU Mode Guide")

        if self.mode == "dfu":
            self.tabs.setCurrentIndex(1)
        else:
            self.tabs.setCurrentIndex(0)

        layout.addWidget(self.tabs, stretch=1)

        btn_close = QPushButton("Close Guide")
        btn_close.setObjectName("MobileQuickBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _get_recovery_html(self) -> str:
        return """
        <style>
            body { font-family: 'Segoe UI', sans-serif; color: #e6edf3; background-color: #0d1117; line-height: 1.5; padding: 10px; }
            h2 { color: #00e5ff; border-bottom: 1px solid #30363d; padding-bottom: 6px; }
            h3 { color: #536dfe; margin-top: 14px; }
            ol { padding-left: 20px; }
            li { margin-bottom: 8px; }
            .badge { background-color: #1c2333; color: #00e676; padding: 3px 8px; border-radius: 4px; font-weight: bold; }
            .note { background-color: #161b22; border-left: 4px solid #ffc107; padding: 10px; margin-top: 12px; }
        </style>
        <h2>How to Enter Recovery Mode</h2>
        <p>Recovery mode allows you to restore or update your iPhone using usbmuxd or iTunes/Finder.</p>
        
        <h3>iPhone 8, iPhone SE (2nd/3rd gen), iPhone X and Newer:</h3>
        <ol>
            <li>Connect your iPhone to your computer using a USB cable.</li>
            <li>Press and quickly release the <b>Volume Up</b> button.</li>
            <li>Press and quickly release the <b>Volume Down</b> button.</li>
            <li>Press and hold the <b>Side (Power) button</b> until you see the recovery mode screen (cable pointing to computer icon).</li>
        </ol>

        <h3>iPhone 7 and iPhone 7 Plus:</h3>
        <ol>
            <li>Press and hold both the <b>Volume Down</b> button and the <b>Side (Power) button</b> simultaneously.</li>
            <li>Keep holding them until the recovery mode screen appears.</li>
        </ol>

        <h3>iPhone 6s and Earlier, iPad with Home Button:</h3>
        <ol>
            <li>Press and hold both the <b>Home button</b> and the <b>Top/Side button</b> simultaneously.</li>
            <li>Keep holding them until you see the recovery mode screen.</li>
        </ol>

        <div class="note">
            <b>Note:</b> Once in Recovery mode, NicksFix and lockdown services will detect the device in recovery state.
        </div>
        """

    def _get_dfu_html(self) -> str:
        return """
        <style>
            body { font-family: 'Segoe UI', sans-serif; color: #e6edf3; background-color: #0d1117; line-height: 1.5; padding: 10px; }
            h2 { color: #00e5ff; border-bottom: 1px solid #30363d; padding-bottom: 6px; }
            h3 { color: #536dfe; margin-top: 14px; }
            ol { padding-left: 20px; }
            li { margin-bottom: 8px; }
            .warn { background-color: #161b22; border-left: 4px solid #ff5252; padding: 10px; margin-top: 12px; }
        </style>
        <h2>How to Enter DFU (Device Firmware Upgrade) Mode</h2>
        <p>DFU mode is a deep state where the device screen stays completely <b>BLACK</b>, allowing low-level firmware flashing.</p>

        <h3>iPhone 8, iPhone X, and Newer (Face ID / No Home Button):</h3>
        <ol>
            <li>Connect the iPhone to your PC via USB.</li>
            <li>Quickly press <b>Volume Up</b>, then quickly press <b>Volume Down</b>.</li>
            <li>Press and hold the <b>Side button</b> for 10 seconds (until screen turns black).</li>
            <li>While continuing to hold the Side button, press and hold the <b>Volume Down</b> button for 5 seconds.</li>
            <li>Release the <b>Side button</b> but continue holding <b>Volume Down</b> for another 10 seconds.</li>
            <li>If the screen remains black, the iPhone is successfully in DFU mode!</li>
        </ol>

        <div class="warn">
            <b>DFU Indicator:</b> If the Apple logo or Recovery icon appears on screen, timing was missed. Restart process.
        </div>
        """


class LiveStreamConsoleDialog(QDialog):
    """
    Live streaming console modal dialog for continuous logs like 'adb logcat' or 'syslog live'.
    Includes real-time line filtering, pause/resume, clearing, and exporting logs.
    """

    def __init__(self, title: str, cmd: list[str], parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.is_paused = False
        self.all_logs = []
        self.setWindowTitle(title)
        self.resize(850, 550)
        self._init_ui()
        self._start_process()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header bar with search & controls
        top_bar = QHBoxLayout()

        lbl_filter = QLabel("🔍 Filter:")
        lbl_filter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        top_bar.addWidget(lbl_filter)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter logs by text / tag...")
        self.filter_input.textChanged.connect(self._apply_filter)
        top_bar.addWidget(self.filter_input, stretch=1)

        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.setToolTip("Pause log streaming update")
        self.btn_pause.clicked.connect(self._toggle_pause)
        top_bar.addWidget(self.btn_pause)

        self.btn_clear = QPushButton("🗑 Clear")
        self.btn_clear.clicked.connect(self._clear_logs)
        top_bar.addWidget(self.btn_clear)

        self.btn_export = QPushButton("💾 Export")
        self.btn_export.clicked.connect(self._export_logs)
        top_bar.addWidget(self.btn_export)

        layout.addLayout(top_bar)

        # Console text edit
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 9))
        self.console.setMaximumBlockCount(8000)
        self.console.setStyleSheet(
            "background-color: #0d1117; color: #7ee787; border: 1px solid #30363d; "
            "border-radius: 6px; padding: 8px;"
        )
        layout.addWidget(self.console, stretch=1)

        # Bottom status layout
        bottom_bar = QHBoxLayout()
        self.status_label = QLabel("Stream initializing...")
        self.status_label.setStyleSheet("color: #8b949e;")
        bottom_bar.addWidget(self.status_label, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

    def _start_process(self):
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_ready_read)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

        executable = self.cmd[0]
        args = self.cmd[1:] if len(self.cmd) > 1 else []
        self.process.start(executable, args)
        self.status_label.setText(f"Streaming: {' '.join(self.cmd)}")

    def _on_ready_read(self):
        if not hasattr(self, "process") or self.process is None:
            return
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        lines = data.splitlines()
        for line in lines:
            self.all_logs.append(line)
            if not self.is_paused:
                filter_text = self.filter_input.text().strip().lower()
                if not filter_text or filter_text in line.lower():
                    self.console.appendPlainText(line)
        self.status_label.setText(f"Streaming live... ({len(self.all_logs)} lines total)")

    def _toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.setText("▶ Resume")
            self.status_label.setText("Streaming paused")
        else:
            self.btn_pause.setText("⏸ Pause")
            self._apply_filter()

    def _apply_filter(self):
        filter_text = self.filter_input.text().strip().lower()
        self.console.clear()
        matching = [l for l in self.all_logs if not filter_text or filter_text in l.lower()]
        self.console.appendPlainText("\n".join(matching[-3000:]))

    def _clear_logs(self):
        self.all_logs.clear()
        self.console.clear()
        self.status_label.setText("Logs cleared")

    def _export_logs(self):
        if not self.all_logs:
            QMessageBox.information(self, "Export Logs", "No logs available to export.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Log Output", "stream_log.txt", "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write("\n".join(self.all_logs))
                QMessageBox.information(self, "Success", f"Logs exported to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export log: {e}")

    def _on_finished(self, exit_code, exit_status):
        self.status_label.setText(f"Stream ended with code {exit_code}")

    def _on_error(self, error):
        self.status_label.setText(f"Process error: {error}")

    def closeEvent(self, event):
        if hasattr(self, "process") and self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        super().closeEvent(event)

