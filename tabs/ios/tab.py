import os
import sys
import subprocess
import shutil
import asyncio
from PyQt6.QtWidgets import (
    QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QStackedWidget, QScrollArea, QFrame, QGridLayout, QGroupBox,
    QSizePolicy
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from tabs.base_driver_tab import BaseDriverTab
from utils.mobile_info import MOBILE_LOGOS, format_device_side_by_side
from components.mobile_dialogs import IosModeGuideDialog, LiveStreamConsoleDialog
from components.ios.file_manager_dialog import IosFileManagerDialog
from components.ios.dvt_kit_dialog import DvtKitDialog
from components.ios.backup_restore_dialog import BackupRestoreDialog
from components.ios.crash_reports_dialog import CrashReportsDialog
from components.ios.lockdown_dialog import LockdownDialog
from components.ios.developer_tools_dialog import DeveloperToolsDialog
from components.ios.ipsw_restore_dialog import IpswRestoreDialog
from components.ios.lockdown_panel import LockdownControlPanel


class IosDevicePoller(QThread):
    info_ready = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def run(self):
        """Run everything inside a single async context to avoid nested event loop conflicts."""
        try:
            result = asyncio.run(self._async_fetch())
            self.info_ready.emit(result)
        except Exception as e:
            self.error_signal.emit(f"[!] IosDevicePoller fatal error: {e}")
            self.info_ready.emit({})

    async def _async_fetch(self) -> dict:
        try:
            import pymobiledevice3
        except ImportError:
            self.error_signal.emit("[!] pymobiledevice3 not installed.")
            return {}

        # ── List devices ──────────────────────────────────────────────
        try:
            from pymobiledevice3.usbmux import list_devices
            raw = list_devices()
            import inspect
            devices = list(await raw if inspect.iscoroutine(raw) else raw)
        except Exception as e:
            self.error_signal.emit(f"[!] list_devices() error: {e}")
            return {}

        if not devices:
            return {}

        dev = devices[0]
        try:
            conn_type = "Wi-Fi" if dev.connection_type.lower() == "network" else "USB"
        except Exception:
            conn_type = "USB"

        # ── Open lockdown ─────────────────────────────────────────────
        lockdown = None
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            import inspect
            raw_ld = create_using_usbmux(serial=dev.serial)
            lockdown = await raw_ld if inspect.iscoroutine(raw_ld) else raw_ld
        except Exception as e:
            self.error_signal.emit(f"[!] Lockdown open failed: {e}")
            return {}

        # ── Read values ───────────────────────────────────────────────
        async def gv(domain=None, key=None):
            try:
                import inspect
                if domain:
                    raw = lockdown.get_value(domain=domain, key=key)
                else:
                    raw = lockdown.get_value(key=key)
                return await raw if inspect.iscoroutine(raw) else raw
            except Exception:
                return None

        product_type  = await gv(key="ProductType")   or "Unknown"
        product_name  = await gv(key="ProductName")   or product_type
        os_ver        = await gv(key="ProductVersion") or "Unknown"
        serial        = await gv(key="SerialNumber")   or dev.serial
        imei          = await gv(key="InternationalMobileEquipmentIdentity") or "N/A"
        activation    = await gv(key="ActivationState") or "Unknown"
        battery       = await gv(domain="com.apple.mobile.battery",
                                 key="BatteryCurrentCapacity")

        return {
            "Model":      product_name,
            "OS":         f"iOS {os_ver}",
            "Serial_UDID": serial,
            "IMEI":       imei,
            "Connection": conn_type,
            "Battery":    f"{battery}%" if battery is not None else "Unknown",
            "Activation": activation,
            "Status":     "Paired / Online"
        }


class IosDriverTab(BaseDriverTab):
    def __init__(self):
        super().__init__("iOS")
        self._build_stacked_ui()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_device_info)
        self.refresh_timer.start(6000)
        self._update_device_info()

    def _build_stacked_ui(self):
        """Build the 3uTools-style stacked view on top of the base layout."""
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self._build_device_info_page())   # page 0
        self.view_stack.addWidget(self._build_toolbox_page())        # page 1

        # Nav bar
        nav_layout = QHBoxLayout()
        self.btn_view_info = QPushButton("📱  iDevice")
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

        # Insert nav + stack above the tools_group (which we hide)
        self.tools_group.hide()
        idx = self.content_layout.indexOf(self.tools_group)
        self.content_layout.insertLayout(idx, nav_layout)
        self.content_layout.insertWidget(idx + 1, self.view_stack)

    def _build_device_info_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 6, 0, 0)
        outer.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(6)

        self.device_overview_label = QLabel()
        self.device_overview_label.setFont(QFont("Consolas", 10))
        self.device_overview_label.setTextFormat(Qt.TextFormat.RichText)
        self.device_overview_label.setObjectName("DeviceOverviewLabel")
        self.device_overview_label.setStyleSheet(
            "background-color: #161b22; padding: 14px 18px; border-radius: 8px; "
            "border: 1px solid #30363d; color: #c9d1d9;"
        )
        self._render_disconnected_state(platform="iOS")
        layout.addWidget(self.device_overview_label)

        # Quick action row
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        for label, slot in [("🔒  Pair", self._act_pair),
                            ("↺  Refresh", self._update_device_info)]:
            btn = QPushButton(label)
            btn.setObjectName("MobileQuickBtn")
            btn.setFixedHeight(26)
            btn.clicked.connect(slot)
            quick_row.addWidget(btn)
        quick_row.addStretch()
        layout.addLayout(quick_row)

        # Lockdown control surface — power, settings, vitals, toggles, activation
        self.lockdown_panel = LockdownControlPanel()
        self.lockdown_panel.log_message.connect(self.log_verbose)
        layout.addWidget(self.lockdown_panel)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)
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

        # (label, slot, tooltip) — "&&" renders as a literal "&" (Qt mnemonic escape)
        categories = {
            "Common Tools": [
                ("🔒  Pair Device",            self._act_pair,             "Trust and pair this computer with the connected device."),
                ("📋  Stream Syslog",          self._act_syslog,           "Live-stream the device system log with filtering."),
                ("📁  Files && Apps Manager",  self._act_file_manager,     "Browse the AFC file system, installed apps, and media."),
                ("ℹ️  Lockdown Info",          self._act_lockdown_dialog,  "View raw lockdown configuration key-value domains."),
            ],
            "Forensic && Analysis Tools": [
                ("💾  Backup && Restore",      self._act_backup_dialog,    "Create or restore a full mobilebackup2 device backup."),
                ("🩺  Crash Log Explorer",     self._act_crash_reports,    "Browse, preview, and export .ips / .crash reports."),
                ("🛠️  DVT Instruments Kit",    self._act_dvt_kit,          "Processes, screenshots, GPS simulation, app launcher (needs DDI)."),
                ("🛡️  Developer Setup && DDI", self._act_dev_tools,        "Mount the Developer Disk Image and manage developer mode."),
            ],
            "Advanced Hardware && Flashing": [
                ("⚡  IPSW Firmware Restore",  self._act_ipsw_restore,     "Restore device firmware from an IPSW file."),
                ("🔑  Recovery Mode Guide",    self._act_recovery,         "Step-by-step guide for entering Recovery Mode."),
                ("🔓  DFU Mode Guide",         self._act_dfu,              "Step-by-step guide for entering DFU Mode."),
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

    def _render_disconnected_state(self, platform="iOS"):
        specs = {"Model": "No Device", "OS": "-", "Serial_UDID": "-",
                 "Connection": "-", "Battery": "-", "Status": "Disconnected"}
        formatted = format_device_side_by_side(MOBILE_LOGOS[platform], specs)
        self.device_overview_label.setText(f"<pre>{formatted}</pre>")

    def _update_device_info(self):
        if hasattr(self, "_poller") and self._poller.isRunning():
            return
        self._poller = IosDevicePoller()
        self._poller.error_signal.connect(self.log_verbose)
        self._poller.info_ready.connect(self._on_device_info_ready)
        self._poller.start()

    def _on_device_info_ready(self, specs):
        if not specs:
            self._render_disconnected_state("iOS")
            return
        formatted = format_device_side_by_side(MOBILE_LOGOS["iOS"], specs)
        self.device_overview_label.setText(f"<pre>{formatted}</pre>")

    # ── Quick actions ─────────────────────────────────────────────────────────
    def _act_restart(self):
        self.log_verbose("[iOS] Sending restart command via lockdown...")

    def _act_shutdown(self):
        self.log_verbose("[iOS] Sending shutdown command via lockdown...")

    def _act_pair(self):
        self.log_verbose("[iOS] Sending pairing handshake...")

    def _act_syslog(self):
        self.log_verbose("[iOS] Opening Syslog live stream console...")
        cmd = [sys.executable, "-m", "pymobiledevice3", "syslog", "live"] if shutil.which("pymobiledevice3") or True else ["idevicesyslog"]
        dlg = LiveStreamConsoleDialog(title="iOS Syslog Live Stream", cmd=cmd, parent=self)
        dlg.exec()

    def _act_file_manager(self):
        self.log_verbose("[iOS] Opening Files & Apps Manager...")
        dlg = IosFileManagerDialog(parent=self)
        dlg.exec()

    def _act_lockdown_dialog(self):
        self.log_verbose("[iOS] Opening Lockdown Inspector...")
        dlg = LockdownDialog(parent=self)
        dlg.exec()

    def _act_backup_dialog(self):
        self.log_verbose("[iOS] Opening Forensic Backup & Restore Wizard...")
        dlg = BackupRestoreDialog(parent=self)
        dlg.exec()

    def _act_crash_reports(self):
        self.log_verbose("[iOS] Opening Crash Reports Explorer...")
        dlg = CrashReportsDialog(parent=self)
        dlg.exec()

    def _act_dvt_kit(self):
        self.log_verbose("[iOS] Opening DVT Kit & Instruments Modal...")
        dlg = DvtKitDialog(parent=self)
        dlg.exec()

    def _act_dev_tools(self):
        self.log_verbose("[iOS] Opening Developer Setup & DDI Mounter...")
        dlg = DeveloperToolsDialog(parent=self)
        dlg.exec()

    def _act_ipsw_restore(self):
        self.log_verbose("[iOS] Opening IPSW Restore Engine...")
        dlg = IpswRestoreDialog(parent=self)
        dlg.exec()

    def _act_get_info(self):
        self._update_device_info()
        self.log_verbose("[iOS] Refreshing lockdown device info...")

    def _act_recovery(self):
        self.open_recovery_guide()

    def open_recovery_guide(self):
        self.log_verbose("[iOS] Opening Recovery Mode hardware guide...")
        dlg = IosModeGuideDialog(mode="recovery", parent=self)
        dlg.exec()

    def _act_backup(self):
        self._act_backup_dialog()

    def _act_dfu(self):
        self.open_dfu_guide()

    def open_dfu_guide(self):
        self.log_verbose("[iOS] Opening DFU Mode hardware guide...")
        dlg = IosModeGuideDialog(mode="dfu", parent=self)
        dlg.exec()

