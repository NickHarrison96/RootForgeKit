# =============================================================================
# RootForgeKit — iOS Lockdown Control Panel (PySide6)
#
# Two tabs:
#   Control    — device power control, settings, vitals, feature toggles,
#                activation state (ported from the iForensics Lockdown view).
#   Inspector  — raw lockdown key/value domain browser.
#
# Power actions are confirmed before running; everything else is read-only or
# an explicit toggle.
# =============================================================================

import sys
import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLineEdit,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QComboBox, QWidget, QFrame, QGroupBox, QCheckBox, QTabWidget,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from utils.resource_manager import safe_run_command


# Power actions need an explicit confirmation before firing.
DESTRUCTIVE_ACTIONS = {
    "restart":  ("Restart Device",  "The device will reboot and disconnect."),
    "shutdown": ("Shutdown Device", "The device will power off and disconnect."),
    "sleep":    ("Sleep Device",    "The device display will sleep."),
}


class LockdownCommandWorker(QThread):
    """Runs one pymobiledevice3 command and reports its result."""
    done = Signal(str, bool, str)   # key, ok, output

    def __init__(self, key: str, args: list[str], timeout: int = 20):
        super().__init__()
        self.key = key
        self.args = args
        self.timeout = timeout

    def run(self):
        ok, out = safe_run_command(
            [sys.executable, "-m", "pymobiledevice3"] + self.args, timeout=self.timeout
        )
        self.done.emit(self.key, ok, (out or "").strip())


class LockdownValuesWorker(QThread):
    values_loaded = Signal(dict)
    error_signal = Signal(str)

    def __init__(self, domain: str = ""):
        super().__init__()
        self.domain = domain

    def run(self):
        # `lockdown info` has no --domain flag; domain queries go through
        # `lockdown get --domain <domain>`.
        if self.domain:
            cmd = [sys.executable, "-m", "pymobiledevice3",
                   "lockdown", "get", "--domain", self.domain]
        else:
            cmd = [sys.executable, "-m", "pymobiledevice3", "lockdown", "info"]
        ok, out = safe_run_command(cmd, timeout=20)
        if not ok:
            self.error_signal.emit(f"Failed querying lockdown domain info:\n{out}")
            return
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                self.values_loaded.emit(data)
            else:
                self.error_signal.emit("Invalid JSON response received.")
        except Exception as e:
            self.error_signal.emit(f"Failed parsing lockdown JSON: {e}")


class LockdownDialog(QDialog):
    """iOS Lockdown control panel and raw inspector."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔑 iOS Lockdown Control Panel")
        self.resize(900, 680)
        self._workers: dict[str, LockdownCommandWorker] = {}
        self._init_ui()
        self.refresh_device_info()
        self._load_lockdown_info()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_control_tab(), "🎛️  Control")
        self.tabs.addTab(self._build_inspector_tab(), "🔍  Inspector")
        layout.addWidget(self.tabs, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    # -------------------------------------------------------------------------
    # Control tab
    # -------------------------------------------------------------------------

    def _build_control_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        # ---- Device Control ----
        power_group = QGroupBox("Device Control")
        power_row = QHBoxLayout(power_group)
        power_row.setContentsMargins(8, 4, 8, 8)
        power_row.setSpacing(6)

        for action, (label, _) in DESTRUCTIVE_ACTIONS.items():
            btn = QPushButton(label)
            btn.setObjectName(f"Power{action.capitalize()}Btn")
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, a=action: self._power_action(a))
            power_row.addWidget(btn)
        power_row.addStretch()
        outer.addWidget(power_group)

        # ---- Settings + Vitals side by side ----
        mid = QHBoxLayout()
        mid.setSpacing(8)

        settings_group = QGroupBox("Device Settings")
        sg = QGridLayout(settings_group)
        sg.setContentsMargins(8, 4, 8, 8)
        sg.setSpacing(6)

        sg.addWidget(QLabel("Device Name:"), 0, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Device name…")
        sg.addWidget(self.name_input, 0, 1)

        btn_set_name = QPushButton("Set")
        btn_set_name.setFixedWidth(52)
        btn_set_name.clicked.connect(self._set_device_name)
        sg.addWidget(btn_set_name, 0, 2)

        self.lbl_date = QLabel("Unknown")
        self.lbl_language = QLabel("Unknown")
        self.lbl_locale = QLabel("Unknown")
        for row, (caption, widget) in enumerate(
            [("Date:", self.lbl_date), ("Language:", self.lbl_language),
             ("Locale:", self.lbl_locale)], start=1
        ):
            cap = QLabel(caption)
            cap.setStyleSheet("color: #8b949e;")
            widget.setStyleSheet("color: #c9d1d9;")
            sg.addWidget(cap, row, 0)
            sg.addWidget(widget, row, 1, 1, 2)

        btn_refresh_info = QPushButton("🔄  Refresh Info")
        btn_refresh_info.clicked.connect(self.refresh_device_info)
        sg.addWidget(btn_refresh_info, 4, 0, 1, 3)
        sg.setColumnStretch(1, 1)
        mid.addWidget(settings_group, stretch=3)

        vitals_group = QGroupBox("Device Vitals")
        vg = QVBoxLayout(vitals_group)
        vg.setContentsMargins(8, 4, 8, 8)
        vg.setSpacing(6)

        btn_battery = QPushButton("🔋  Get Battery Info")
        btn_battery.clicked.connect(self._get_battery)
        vg.addWidget(btn_battery)

        self.battery_view = QPlainTextEdit()
        self.battery_view.setReadOnly(True)
        self.battery_view.setFont(QFont("Consolas", 9))
        self.battery_view.setPlaceholderText("Click 'Get Battery Info' to view battery details…")
        self.battery_view.setMinimumHeight(90)
        self.battery_view.setStyleSheet(
            "background-color: #0d1117; color: #7ee787; "
            "border: 1px solid #30363d; border-radius: 6px;"
        )
        vg.addWidget(self.battery_view, stretch=1)
        mid.addWidget(vitals_group, stretch=2)

        outer.addLayout(mid)

        # ---- Feature toggles + activation ----
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        toggles_group = QGroupBox("Feature Toggles")
        tg = QGridLayout(toggles_group)
        tg.setContentsMargins(8, 4, 8, 8)
        tg.setSpacing(6)

        self.chk_assistive = QCheckBox("Assistive Touch")
        self.chk_assistive.setToolTip("On-screen accessibility button")
        self.chk_assistive.clicked.connect(
            lambda checked: self._set_toggle("assistive-touch", checked)
        )
        tg.addWidget(self.chk_assistive, 0, 0)

        self.chk_wifi = QCheckBox("WiFi Connections")
        self.chk_wifi.setToolTip(
            "Enables WiFi sync/debugging — does not disable the WiFi radio"
        )
        self.chk_wifi.clicked.connect(
            lambda checked: self._set_toggle("wifi-connections", checked)
        )
        tg.addWidget(self.chk_wifi, 1, 0)

        btn_read_states = QPushButton("Read States")
        btn_read_states.clicked.connect(self._read_toggle_states)
        tg.addWidget(btn_read_states, 2, 0)
        tg.setColumnStretch(1, 1)
        bottom.addWidget(toggles_group, stretch=1)

        activation_group = QGroupBox("Activation Status")
        ag = QVBoxLayout(activation_group)
        ag.setContentsMargins(8, 4, 8, 8)
        ag.setSpacing(6)

        btn_activation = QPushButton("Check Activation")
        btn_activation.clicked.connect(self._check_activation)
        ag.addWidget(btn_activation)

        self.lbl_activation = QLabel("Status: Not checked")
        self.lbl_activation.setStyleSheet("color: #8b949e;")
        ag.addWidget(self.lbl_activation)
        ag.addStretch()
        bottom.addWidget(activation_group, stretch=1)

        outer.addLayout(bottom)

        # ---- Operations log ----
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setPlaceholderText("Lockdown operations log…")
        self.log.setMinimumHeight(60)
        self.log.setMaximumBlockCount(1000)
        self.log.setStyleSheet(
            "background-color: #0a0e14; color: #7ee787; "
            "border: 1px solid #30363d; border-radius: 6px;"
        )
        outer.addWidget(self.log, stretch=1)

        return page

    # -------------------------------------------------------------------------
    # Inspector tab
    # -------------------------------------------------------------------------

    def _build_inspector_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        lbl_domain = QLabel("Domain:")
        lbl_domain.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        top_row.addWidget(lbl_domain)

        self.domain_combo = QComboBox()
        self.domain_combo.addItems([
            "Global (All Domains)",
            "com.apple.mobile.battery",
            "com.apple.disk_usage",
            "com.apple.international",
            "com.apple.mobile.data_sync",
            "com.apple.mobile.restriction",
            "com.apple.mobile.wireless_lockdown",
            "com.apple.fairplay",
        ])
        self.domain_combo.currentIndexChanged.connect(self._load_lockdown_info)
        top_row.addWidget(self.domain_combo, stretch=1)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._load_lockdown_info)
        top_row.addWidget(btn_refresh)
        layout.addLayout(top_row)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Lockdown Key", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(
            "background-color: #161b22; color: #e6edf3; gridline-color: #30363d;"
        )
        layout.addWidget(self.table, stretch=1)

        self.status_label = QLabel("Querying lockdown info…")
        self.status_label.setStyleSheet("color: #8b949e;")
        layout.addWidget(self.status_label)
        return page

    # -------------------------------------------------------------------------
    # Command plumbing
    # -------------------------------------------------------------------------

    def _log(self, text: str):
        self.log.appendPlainText(text)

    def _run(self, key: str, args: list[str], timeout: int = 20):
        """Fire a command; results arrive in _on_command_done."""
        worker = LockdownCommandWorker(key, args, timeout)
        worker.done.connect(self._on_command_done)
        self._workers[key] = worker            # keep a reference alive
        worker.start()

    def _on_command_done(self, key: str, ok: bool, out: str):
        handler = getattr(self, f"_handle_{key.replace('-', '_')}", None)
        if handler:
            handler(ok, out)
        else:
            self._log(f"{'[+]' if ok else '[-]'} {key}: {out or '(no output)'}")
        self._workers.pop(key, None)

    # -------------------------------------------------------------------------
    # Device control
    # -------------------------------------------------------------------------

    def _power_action(self, action: str):
        label, consequence = DESTRUCTIVE_ACTIONS[action]
        reply = QMessageBox.warning(
            self, f"Confirm {label}",
            f"<b>{label}</b><br><br>{consequence}<br><br>Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._log(f"[.] {label} cancelled.")
            return
        self._log(f"[*] Sending {action}…")
        self._run(f"power_{action}", ["diagnostics", action], timeout=25)

    def _handle_power_restart(self, ok, out): self._power_result("Restart", ok, out)
    def _handle_power_shutdown(self, ok, out): self._power_result("Shutdown", ok, out)
    def _handle_power_sleep(self, ok, out): self._power_result("Sleep", ok, out)

    def _power_result(self, label: str, ok: bool, out: str):
        if ok:
            self._log(f"[+] {label} command sent — the device will disconnect.")
        else:
            self._log(f"[-] {label} failed: {out}")

    # -------------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------------

    def refresh_device_info(self):
        self._log("[*] Reading device settings…")
        self._run("device_name", ["lockdown", "device-name"])
        self._run("date", ["lockdown", "date"])
        self._run("language", ["lockdown", "language"])
        self._run("locale", ["lockdown", "locale"])

    @staticmethod
    def _clean(value: str) -> str:
        return (value or "").strip().strip('"').strip()

    def _handle_device_name(self, ok: bool, out: str):
        if ok:
            name = self._clean(out)
            if not self.name_input.hasFocus():
                self.name_input.setText(name)
            self._log(f"[+] Device name: {name}")
        else:
            self._log(f"[-] Could not read device name: {out}")

    def _handle_date(self, ok: bool, out: str):
        self.lbl_date.setText(self._clean(out) if ok else "Unavailable")

    def _handle_language(self, ok: bool, out: str):
        self.lbl_language.setText(self._clean(out) if ok else "Unavailable")

    def _handle_locale(self, ok: bool, out: str):
        self.lbl_locale.setText(self._clean(out) if ok else "Unavailable")

    def _set_device_name(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Enter a device name first.")
            return
        self._log(f"[*] Setting device name to '{name}'…")
        self._run("set_name", ["lockdown", "device-name", name])

    def _handle_set_name(self, ok: bool, out: str):
        if ok:
            self._log("[+] Device name updated.")
            self._run("device_name", ["lockdown", "device-name"])
        else:
            self._log(f"[-] Failed to set device name: {out}")

    # -------------------------------------------------------------------------
    # Vitals
    # -------------------------------------------------------------------------

    def _get_battery(self):
        self.battery_view.setPlainText("Querying battery…")
        # The battery lockdown domain is far more readable than
        # `diagnostics battery single`, which returns raw IOKit blobs.
        self._run("battery", ["lockdown", "info", "--domain", "com.apple.mobile.battery"])

    def _handle_battery(self, ok: bool, out: str):
        if not ok:
            self.battery_view.setPlainText(f"Failed to read battery info:\n{out}")
            self._log("[-] Battery query failed.")
            return
        try:
            data = json.loads(out)
            lines = []
            level = data.get("BatteryCurrentCapacity")
            charging = data.get("BatteryIsCharging")
            if level is not None:
                lines.append(f"Charge level      : {level}%")
            if charging is not None:
                lines.append(f"Charging          : {'yes' if charging else 'no'}")
            for key, value in sorted(data.items()):
                if key in ("BatteryCurrentCapacity", "BatteryIsCharging"):
                    continue
                lines.append(f"{key:18}: {value}")
            self.battery_view.setPlainText("\n".join(lines))
            self._log(f"[+] Battery: {level}%"
                      f"{' (charging)' if charging else ''}")
        except Exception:
            self.battery_view.setPlainText(out)
            self._log("[+] Battery info retrieved.")

    # -------------------------------------------------------------------------
    # Feature toggles
    # -------------------------------------------------------------------------

    def _read_toggle_states(self):
        self._log("[*] Reading feature toggle states…")
        self._run("assistive_get", ["lockdown", "assistive-touch"])
        self._run("wifi_get", ["lockdown", "wifi-connections"])

    @staticmethod
    def _truthy(out: str) -> bool:
        lowered = (out or "").lower()
        if "true" in lowered:
            return True
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                return any(bool(v) for v in data.values())
            return bool(data)
        except Exception:
            return False

    def _handle_assistive_get(self, ok: bool, out: str):
        if ok:
            state = self._truthy(out)
            self.chk_assistive.setChecked(state)
            self._log(f"[+] Assistive Touch: {'on' if state else 'off'}")
        else:
            self._log(f"[-] Could not read Assistive Touch: {out}")

    def _handle_wifi_get(self, ok: bool, out: str):
        if ok:
            state = self._truthy(out)
            self.chk_wifi.setChecked(state)
            self._log(f"[+] WiFi Connections: {'on' if state else 'off'}")
        else:
            self._log(f"[-] Could not read WiFi Connections: {out}")

    def _set_toggle(self, feature: str, enabled: bool):
        state = "on" if enabled else "off"
        self._log(f"[*] Setting {feature} to {state}…")
        key = "assistive_set" if feature == "assistive-touch" else "wifi_set"
        self._run(key, ["lockdown", feature, state])

    def _handle_assistive_set(self, ok: bool, out: str):
        self._log(f"[+] Assistive Touch updated." if ok
                  else f"[-] Assistive Touch change failed: {out}")
        self._run("assistive_get", ["lockdown", "assistive-touch"])

    def _handle_wifi_set(self, ok: bool, out: str):
        self._log(f"[+] WiFi Connections updated." if ok
                  else f"[-] WiFi Connections change failed: {out}")
        self._run("wifi_get", ["lockdown", "wifi-connections"])

    # -------------------------------------------------------------------------
    # Activation
    # -------------------------------------------------------------------------

    def _check_activation(self):
        self.lbl_activation.setText("Status: Checking…")
        self._run("activation", ["lockdown", "info"])

    def _handle_activation(self, ok: bool, out: str):
        if not ok:
            self.lbl_activation.setText("Status: Unavailable")
            self.lbl_activation.setStyleSheet("color: #ff5252;")
            self._log(f"[-] Activation check failed: {out}")
            return
        try:
            data = json.loads(out)
            state = data.get("ActivationState", "Unknown")
        except Exception:
            state = "Unknown"

        activated = str(state).lower() in ("activated", "wildcardactivated")
        self.lbl_activation.setText(f"Status: {state}")
        self.lbl_activation.setStyleSheet(
            f"color: {'#00e676' if activated else '#f0a500'};"
        )
        self._log(f"[+] Activation state: {state}")

    # -------------------------------------------------------------------------
    # Inspector
    # -------------------------------------------------------------------------

    def _load_lockdown_info(self):
        text = self.domain_combo.currentText()
        domain = "" if text.startswith("Global") else text
        self.status_label.setText("Querying lockdown values…")
        self.table.setRowCount(0)

        self._values_worker = LockdownValuesWorker(domain)
        self._values_worker.values_loaded.connect(self._on_values_loaded)
        self._values_worker.error_signal.connect(self._on_values_error)
        self._values_worker.start()

    def _on_values_loaded(self, values: dict):
        self.table.setRowCount(len(values))
        for row, (k, v) in enumerate(sorted(values.items())):
            self.table.setItem(row, 0, QTableWidgetItem(str(k)))
            self.table.setItem(row, 1, QTableWidgetItem(str(v)))
        self.status_label.setText(f"Loaded {len(values)} key-value pair(s)")

    def _on_values_error(self, err_msg: str):
        self.status_label.setText("Failed loading lockdown info")
        self._log(f"[-] {err_msg}")
