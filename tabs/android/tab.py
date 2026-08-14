import os
import shutil
import re
from PyQt6.QtWidgets import (
    QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QStackedWidget, QScrollArea, QFrame, QGridLayout,
    QGroupBox, QLineEdit, QFileDialog, QSizePolicy
)
from components.mobile_dialogs import AdbFileExplorerDialog, LiveStreamConsoleDialog
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from tabs.base_driver_tab import BaseDriverTab
from utils.mobile_info import MOBILE_LOGOS, format_device_side_by_side
from utils.resource_manager import safe_run_command


class AndroidDevicePoller(QThread):
    info_ready = pyqtSignal(dict)

    def run(self):
        if not shutil.which("adb"):
            # Also check local bin/
            local = os.path.abspath(os.path.join("bin", "platform-tools"))
            adb_candidate = os.path.join(local, "adb.exe" if os.name == "nt" else "adb")
            if not os.path.isfile(adb_candidate):
                self.info_ready.emit({})
                return
        try:
            ok, dev_stdout = safe_run_command(["adb", "devices"], timeout=5)
            if not ok:
                self.info_ready.emit({})
                return

            devices = re.findall(r"^(\S+)\s+device$", dev_stdout, re.MULTILINE)
            if not devices:
                self.info_ready.emit({})
                return

            device_id = devices[0]
            conn_type = "Wi-Fi (Wireless)" if ":" in device_id else "USB"

            def get_prop(prop):
                ok_p, p_out = safe_run_command(["adb", "-s", device_id, "shell", "getprop", prop], timeout=5)
                return p_out if ok_p else "Unknown"

            model = get_prop("ro.product.model")
            brand = get_prop("ro.product.brand").capitalize()
            os_ver = get_prop("ro.build.version.release")
            android_ver = get_prop("ro.build.version.sdk")
            serial = get_prop("ro.serialno")

            ok_b, batt_out = safe_run_command(["adb", "-s", device_id, "shell", "dumpsys", "battery"], timeout=5)
            batt_match = re.search(r"level:\s+(\d+)", batt_out) if ok_b else None
            battery = f"{batt_match.group(1)}%" if batt_match else "Unknown"

            specs = {
                "Model": f"{brand} {model}",
                "OS": f"Android {os_ver} (API {android_ver})",
                "Serial_UDID": serial or device_id,
                "Connection": conn_type,
                "Battery": battery,
                "Status": "Authorized / Online"
            }
            self.info_ready.emit(specs)
        except Exception:
            self.info_ready.emit({})


class AndroidDriverTab(BaseDriverTab):
    def __init__(self):
        super().__init__("Android")
        self._patch_local_path()
        self._build_stacked_ui()
        self._update_device_info()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_device_info)
        self.refresh_timer.start(6000)

    @staticmethod
    def _local_platform_tools_path() -> str | None:
        candidate = os.path.abspath(os.path.join("bin", "platform-tools"))
        if os.path.isdir(candidate):
            return candidate
        return None

    def _patch_local_path(self):
        local = self._local_platform_tools_path()
        if local and local not in os.environ.get("PATH", ""):
            os.environ["PATH"] = local + os.pathsep + os.environ["PATH"]
            self.log_verbose(f"[+] Local Platform Tools found — added to PATH: {local}")

    def _build_stacked_ui(self):
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self._build_device_info_page())   # page 0
        self.view_stack.addWidget(self._build_toolbox_page())        # page 1

        nav_layout = QHBoxLayout()
        self.btn_view_info = QPushButton("🤖  iDevice")
        self.btn_view_info.setObjectName("MobileNavBtn")
        self.btn_view_info.setCheckable(True)
        self.btn_view_info.setChecked(True)
        self.btn_view_toolbox = QPushButton("🧰  Toolbox")
        self.btn_view_toolbox.setObjectName("MobileNavBtn")
        self.btn_view_toolbox.setCheckable(True)
        self.btn_view_info.clicked.connect(lambda: self._switch_view(0))
        self.btn_view_toolbox.clicked.connect(lambda: self._switch_view(1))
        nav_layout.addWidget(self.btn_view_info)
        nav_layout.addWidget(self.btn_view_toolbox)
        nav_layout.addStretch()

        self.tools_group.hide()
        idx = self.content_layout.indexOf(self.tools_group)
        self.content_layout.insertLayout(idx, nav_layout)
        self.content_layout.insertWidget(idx + 1, self.view_stack)

    def _build_device_info_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)

        self.device_overview_label = QLabel()
        self.device_overview_label.setFont(QFont("Consolas", 10))
        self.device_overview_label.setTextFormat(Qt.TextFormat.RichText)
        self.device_overview_label.setStyleSheet(
            "background-color: #161b22; padding: 14px 18px; border-radius: 8px; "
            "border: 1px solid #30363d; color: #c9d1d9;"
        )
        self._render_disconnected_state()
        layout.addWidget(self.device_overview_label)

        # Wireless ADB bar
        wifi_row = QHBoxLayout()
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Enter IP:Port for Wireless ADB  (e.g. 192.168.1.50:5555)")
        self.btn_wifi_connect = QPushButton("📡  Connect Wireless ADB")
        self.btn_wifi_connect.setObjectName("MobileQuickBtn")
        self.btn_wifi_connect.clicked.connect(self._connect_wireless_adb)
        wifi_row.addWidget(self.ip_input, stretch=1)
        wifi_row.addWidget(self.btn_wifi_connect)
        layout.addLayout(wifi_row)

        # Quick actions
        quick_row = QHBoxLayout()
        for label, slot in [("🔄 Reboot", self._act_reboot),
                             ("🔓 Bootloader", self._act_bootloader),
                             ("↺  Refresh", self._update_device_info)]:
            btn = QPushButton(label)
            btn.setObjectName("MobileQuickBtn")
            btn.clicked.connect(slot)
            quick_row.addWidget(btn)
        layout.addLayout(quick_row)
        return page

    def _build_toolbox_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 6, 0, 0)
        outer.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(6)

        # (label, slot, tooltip)
        categories = {
            "Common Tools": [
                ("📋  List Devices",      self._act_list_devices, "List all ADB-visible devices and their authorization state."),
                ("📸  Screenshot",        self._act_screenshot,   "Capture the device screen and pull it to this computer."),
                ("📦  Install APK",       self._act_install_apk,  "Select and sideload an APK onto the connected device."),
                ("📜  Stream Logcat",     self._act_logcat,       "Live-stream logcat output with filtering and export."),
            ],
            "Advanced Tools": [
                ("🔓  Reboot Bootloader", self._act_bootloader,   "Reboot the device into bootloader / fastboot mode."),
                ("🔧  Reboot Recovery",   self._act_recovery,     "Reboot the device into recovery mode."),
                ("🗂️  Pull File",         self._act_pull_file,    "Browse the device file system and pull files."),
                ("💾  Backup (adb)",      self._act_backup,       "Create an adb backup archive of the device."),
                ("🔑  Enable TCP/IP",     self._act_tcpip,        "Switch ADB to TCP/IP mode for wireless debugging."),
            ],
        }

        COLS = 4
        for cat_name, tools in categories.items():
            group = QGroupBox(cat_name)
            group.setObjectName("ToolboxGroup")
            grid = QGridLayout(group)
            grid.setContentsMargins(8, 4, 8, 8)
            grid.setSpacing(6)
            for i, (label, slot, tip) in enumerate(tools):
                btn = QPushButton(label)
                btn.setObjectName("ToolboxItemBtn")
                btn.setFixedSize(210, 28)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(tip)
                btn.clicked.connect(slot)
                grid.addWidget(btn, i // COLS, i % COLS,
                                Qt.AlignmentFlag.AlignLeft)
            # Trailing spacer column absorbs the slack so buttons stay left-packed
            grid.setColumnStretch(COLS, 1)
            v.addWidget(group)

        v.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)
        return page

    def _switch_view(self, idx: int):
        self.view_stack.setCurrentIndex(idx)
        self.btn_view_info.setChecked(idx == 0)
        self.btn_view_toolbox.setChecked(idx == 1)

    def _render_disconnected_state(self):
        specs = {"Model": "No Device", "OS": "-", "Serial_UDID": "-",
                 "Connection": "-", "Battery": "-", "Status": "Disconnected"}
        formatted = format_device_side_by_side(MOBILE_LOGOS["Android"], specs)
        self.device_overview_label.setText(f"<pre>{formatted}</pre>")

    def _update_device_info(self):
        if hasattr(self, "_poller") and self._poller.isRunning():
            return
        self._poller = AndroidDevicePoller()
        self._poller.info_ready.connect(self._on_device_info_ready)
        self._poller.start()

    def _on_device_info_ready(self, specs):
        if not specs:
            self._render_disconnected_state()
            return
        formatted = format_device_side_by_side(MOBILE_LOGOS["Android"], specs)
        self.device_overview_label.setText(f"<pre>{formatted}</pre>")

    def _connect_wireless_adb(self):
        ip_port = self.ip_input.text().strip()
        if not ip_port:
            self.log_verbose("[-] Please enter a valid IP:Port.")
            return
        self.log_verbose(f"[*] Attempting Wireless ADB connection to {ip_port}...")
        ok, out = safe_run_command(["adb", "connect", ip_port], timeout=8)
        self.log_verbose(f"[Android] {out}")
        if ok:
            self._update_device_info()

    # ── Quick actions ─────────────────────────────────────────────────────────
    def _act_reboot(self):
        self.log_verbose("[Android] Sending 'adb reboot'...")
        ok, out = safe_run_command(["adb", "reboot"], timeout=5)
        self.log_verbose(f"[Android] {out}")

    def _act_bootloader(self):
        self.log_verbose("[Android] Sending 'adb reboot bootloader'...")
        ok, out = safe_run_command(["adb", "reboot", "bootloader"], timeout=5)
        self.log_verbose(f"[Android] {out}")

    def _act_list_devices(self):
        ok, out = safe_run_command(["adb", "devices"], timeout=5)
        self.log_verbose(f"[Android] adb devices:\n{out}")

    def _act_screenshot(self):
        self.log_verbose("[Android] Capturing device screen via adb screencap...")
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "screenshot.png", "PNG Images (*.png)")
        if not save_path:
            return
        temp_remote = "/sdcard/screen_temp.png"
        ok1, out1 = safe_run_command(["adb", "shell", "screencap", "-p", temp_remote], timeout=10)
        if ok1:
            ok2, out2 = safe_run_command(["adb", "pull", temp_remote, save_path], timeout=15)
            safe_run_command(["adb", "shell", "rm", temp_remote], timeout=5)
            if ok2:
                self.log_verbose(f"[+] Screenshot saved successfully: {save_path}")
            else:
                self.log_verbose(f"[-] Failed to pull screenshot: {out2}")
        else:
            self.log_verbose(f"[-] Failed to capture screenshot: {out1}")

    def _act_install_apk(self):
        self.install_apk_dialog()

    def install_apk_dialog(self):
        apk_path, _ = QFileDialog.getOpenFileName(self, "Select APK File", "", "Android Package (*.apk)")
        if not apk_path:
            return
        self.log_verbose(f"[*] Installing APK: {apk_path}...")
        ok, out = safe_run_command(["adb", "install", "-r", apk_path], timeout=60)
        if ok:
            self.log_verbose(f"[+] APK Installation Success!\n{out}")
        else:
            self.log_verbose(f"[-] APK Installation Failed:\n{out}")

    def _act_recovery(self):
        self.log_verbose("[Android] Sending 'adb reboot recovery'...")
        ok, out = safe_run_command(["adb", "reboot", "recovery"], timeout=5)
        self.log_verbose(f"[Android] {out}")

    def _act_pull_file(self):
        self.open_file_explorer_modal()

    def open_file_explorer_modal(self):
        target_device = ""
        if hasattr(self, "_poller") and hasattr(self._poller, "info_ready"):
            # Check for device ID if available
            pass
        dlg = AdbFileExplorerDialog(device_id=target_device, parent=self)
        dlg.exec()

    def _act_backup(self):
        self.log_verbose("[Android] Starting full adb backup...")

    def _act_tcpip(self):
        self.log_verbose("[Android] Enabling TCP/IP mode on port 5555...")
        ok, out = safe_run_command(["adb", "tcpip", "5555"], timeout=5)
        self.log_verbose(f"[Android] {out}")

    def _act_logcat(self):
        self.log_verbose("[Android] Opening Logcat live stream console...")
        dlg = LiveStreamConsoleDialog(title="Android Logcat Live Stream", cmd=["adb", "logcat"], parent=self)
        dlg.exec()

