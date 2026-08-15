# =============================================================================
# RootForgeKit — iOS Lockdown Control Panel (embeddable widget)
#
# Device power control, settings, vitals, feature toggles and activation state,
# all over lockdown services. Lives on the iOS Tools primary (iDevice) page so
# the common controls are one click away rather than behind a modal.
#
# The raw key/value domain browser stays in LockdownDialog (Inspector).
# =============================================================================

import sys
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLineEdit,
    QLabel, QMessageBox, QGroupBox, QCheckBox, QPlainTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from utils.resource_manager import safe_run_command


# Power actions require explicit confirmation before firing.
DESTRUCTIVE_ACTIONS = {
    "restart":  ("🔄  Restart",  "The device will reboot and disconnect."),
    "shutdown": ("⏻  Shutdown", "The device will power off and disconnect."),
    "sleep":    ("💤  Sleep",    "The device display will sleep."),
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


class LockdownControlPanel(QWidget):
    """Embeddable lockdown control surface."""

    # Mirrors log lines out to a host console (e.g. the tab's verbose output).
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers: dict[str, LockdownCommandWorker] = {}
        self._build_ui()

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # ---- Row 1: power control + activation ----
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        power_group = QGroupBox("Device Control")
        power_row = QHBoxLayout(power_group)
        power_row.setContentsMargins(8, 4, 8, 8)
        power_row.setSpacing(6)
        for action, (label, _) in DESTRUCTIVE_ACTIONS.items():
            btn = QPushButton(label)
            btn.setObjectName("LockdownPowerBtn")
            btn.setProperty("action", action)
            btn.setFixedSize(110, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, a=action: self._power_action(a))
            power_row.addWidget(btn)
        power_row.addStretch()
        row1.addWidget(power_group, stretch=3)

        activation_group = QGroupBox("Activation")
        ag = QHBoxLayout(activation_group)
        ag.setContentsMargins(8, 4, 8, 8)
        ag.setSpacing(6)
        btn_activation = QPushButton("Check")
        btn_activation.setFixedSize(80, 28)
        btn_activation.clicked.connect(self._check_activation)
        ag.addWidget(btn_activation)
        self.lbl_activation = QLabel("Not checked")
        self.lbl_activation.setStyleSheet("color: #8b949e;")
        ag.addWidget(self.lbl_activation, stretch=1)
        row1.addWidget(activation_group, stretch=2)

        outer.addLayout(row1)

        # ---- Row 2: settings + vitals + toggles ----
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        settings_group = QGroupBox("Device Settings")
        sg = QGridLayout(settings_group)
        sg.setContentsMargins(8, 4, 8, 8)
        sg.setSpacing(5)

        cap_name = QLabel("Name:")
        cap_name.setStyleSheet("color: #8b949e;")
        sg.addWidget(cap_name, 0, 0)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Device name…")
        self.name_input.setFixedHeight(24)
        sg.addWidget(self.name_input, 0, 1)

        btn_set_name = QPushButton("Set")
        btn_set_name.setFixedSize(46, 24)
        btn_set_name.clicked.connect(self._set_device_name)
        sg.addWidget(btn_set_name, 0, 2)

        self.lbl_date = QLabel("—")
        self.lbl_language = QLabel("—")
        self.lbl_locale = QLabel("—")
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
        btn_refresh_info.setFixedHeight(24)
        btn_refresh_info.clicked.connect(self.refresh_device_info)
        sg.addWidget(btn_refresh_info, 4, 0, 1, 3)
        sg.setColumnStretch(1, 1)
        row2.addWidget(settings_group, stretch=3)

        vitals_group = QGroupBox("Device Vitals")
        vg = QVBoxLayout(vitals_group)
        vg.setContentsMargins(8, 4, 8, 8)
        vg.setSpacing(5)
        btn_battery = QPushButton("🔋  Get Battery Info")
        btn_battery.setFixedHeight(24)
        btn_battery.clicked.connect(self._get_battery)
        vg.addWidget(btn_battery)

        self.battery_view = QPlainTextEdit()
        self.battery_view.setReadOnly(True)
        self.battery_view.setFont(QFont("Consolas", 8))
        self.battery_view.setPlaceholderText("Battery details appear here…")
        self.battery_view.setMinimumHeight(70)
        self.battery_view.setStyleSheet(
            "background-color: #0d1117; color: #7ee787; "
            "border: 1px solid #30363d; border-radius: 6px;"
        )
        vg.addWidget(self.battery_view, stretch=1)
        row2.addWidget(vitals_group, stretch=3)

        toggles_group = QGroupBox("Feature Toggles")
        tg = QVBoxLayout(toggles_group)
        tg.setContentsMargins(8, 4, 8, 8)
        tg.setSpacing(5)

        self.chk_assistive = QCheckBox("Assistive Touch")
        self.chk_assistive.setToolTip("On-screen accessibility button")
        self.chk_assistive.clicked.connect(
            lambda checked: self._set_toggle("assistive-touch", checked)
        )
        tg.addWidget(self.chk_assistive)

        self.chk_wifi = QCheckBox("WiFi Connections")
        self.chk_wifi.setToolTip(
            "Enables WiFi sync/debugging — does not disable the WiFi radio"
        )
        self.chk_wifi.clicked.connect(
            lambda checked: self._set_toggle("wifi-connections", checked)
        )
        tg.addWidget(self.chk_wifi)

        btn_read_states = QPushButton("Read States")
        btn_read_states.setFixedHeight(24)
        btn_read_states.clicked.connect(self.read_toggle_states)
        tg.addWidget(btn_read_states)
        tg.addStretch()
        row2.addWidget(toggles_group, stretch=2)

        outer.addLayout(row2)

    # -------------------------------------------------------------------------
    # Command plumbing
    # -------------------------------------------------------------------------

    def _log(self, text: str):
        self.log_message.emit(text)

    def _run(self, key: str, args: list[str], timeout: int = 20):
        worker = LockdownCommandWorker(key, args, timeout)
        worker.done.connect(self._on_command_done)
        self._workers[key] = worker            # keep a reference alive
        worker.start()

    def _on_command_done(self, key: str, ok: bool, out: str):
        handler = getattr(self, f"_handle_{key}", None)
        if handler:
            handler(ok, out)
        else:
            self._log(f"{'[+]' if ok else '[-]'} {key}: {out or '(no output)'}")
        self._workers.pop(key, None)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def refresh_device_info(self):
        """Re-read name/date/language/locale."""
        self._log("[lockdown] Reading device settings…")
        self._run("device_name", ["lockdown", "device-name"])
        self._run("date", ["lockdown", "date"])
        self._run("language", ["lockdown", "language"])
        self._run("locale", ["lockdown", "locale"])

    def read_toggle_states(self):
        self._log("[lockdown] Reading feature toggle states…")
        self._run("assistive_get", ["lockdown", "assistive-touch"])
        # `lockdown wifi-connections` prints nothing when reading. The keyed
        # query is the only readback, and it only exists once the value has
        # been set at least once ("No such value" otherwise).
        self._run("wifi_get",
                  ["lockdown", "get",
                   "--domain", "com.apple.mobile.wireless_lockdown",
                   "--key", "EnableWifiConnections"])

    # -------------------------------------------------------------------------
    # Device control
    # -------------------------------------------------------------------------

    def _power_action(self, action: str):
        label, consequence = DESTRUCTIVE_ACTIONS[action]
        clean_label = label.split("  ", 1)[-1]
        reply = QMessageBox.warning(
            self, f"Confirm {clean_label}",
            f"<b>{clean_label} device?</b><br><br>{consequence}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._log(f"[lockdown] {clean_label} cancelled.")
            return
        self._log(f"[lockdown] Sending {action}…")
        self._run(f"power_{action}", ["diagnostics", action], timeout=25)

    def _power_result(self, label: str, ok: bool, out: str):
        self._log(f"[+] {label} sent — the device will disconnect." if ok
                  else f"[-] {label} failed: {out}")

    def _handle_power_restart(self, ok, out):  self._power_result("Restart", ok, out)
    def _handle_power_shutdown(self, ok, out): self._power_result("Shutdown", ok, out)
    def _handle_power_sleep(self, ok, out):    self._power_result("Sleep", ok, out)

    # -------------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------------

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
        self._log(f"[lockdown] Setting device name to '{name}'…")
        # device-name takes --new-name, not a positional argument.
        self._run("set_name", ["lockdown", "device-name", "--new-name", name])

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
        # `lockdown get --domain` (not `info --domain`, which has no such flag).
        # Far more readable than `diagnostics battery single`, which returns
        # raw IOKit blobs.
        self._run("battery", ["lockdown", "get", "--domain", "com.apple.mobile.battery"])

    def _handle_battery(self, ok: bool, out: str):
        if not ok:
            self.battery_view.setPlainText(f"Failed to read battery info:\n{out}")
            self._log("[-] Battery query failed.")
            return
        try:
            data = json.loads(out)
            level = data.get("BatteryCurrentCapacity")
            charging = data.get("BatteryIsCharging")
            lines = []
            if level is not None:
                lines.append(f"{'Charge level':<22}: {level}%")
            if charging is not None:
                lines.append(f"{'Charging':<22}: {'yes' if charging else 'no'}")
            for key, value in sorted(data.items()):
                if key in ("BatteryCurrentCapacity", "BatteryIsCharging"):
                    continue
                lines.append(f"{key:<22}: {value}")
            self.battery_view.setPlainText("\n".join(lines))
            self._log(f"[+] Battery: {level}%{' (charging)' if charging else ''}")
        except Exception:
            self.battery_view.setPlainText(out)
            self._log("[+] Battery info retrieved.")

    # -------------------------------------------------------------------------
    # Feature toggles
    # -------------------------------------------------------------------------

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
        if not ok:
            # The device reports "No such value" until the key has been written
            # once — that is "not configured", not a read failure.
            if "no such value" in (out or "").lower():
                self.chk_wifi.setChecked(False)
                self.chk_wifi.setText("WiFi Connections (not set)")
                self._log("[.] WiFi Connections: not configured on this device "
                          "(no stored value to read back).")
            else:
                self._log(f"[-] Could not read WiFi Connections: {out}")
            return
        state = self._truthy(out)
        self.chk_wifi.setChecked(state)
        self.chk_wifi.setText("WiFi Connections")
        self._log(f"[+] WiFi Connections: {'on' if state else 'off'}")

    def _set_toggle(self, feature: str, enabled: bool):
        state = "on" if enabled else "off"
        self._log(f"[lockdown] Setting {feature} to {state}…")
        key = "assistive_set" if feature == "assistive-touch" else "wifi_set"
        # These toggles take --state on|off, not a positional argument.
        self._run(key, ["lockdown", feature, "--state", state])

    def _handle_assistive_set(self, ok: bool, out: str):
        self._log("[+] Assistive Touch updated." if ok
                  else f"[-] Assistive Touch change failed: {out}")
        self._run("assistive_get", ["lockdown", "assistive-touch"])

    def _handle_wifi_set(self, ok: bool, out: str):
        self._log("[+] WiFi Connections updated." if ok
                  else f"[-] WiFi Connections change failed: {out}")
        self._run("wifi_get", ["lockdown", "wifi-connections"])

    # -------------------------------------------------------------------------
    # Activation
    # -------------------------------------------------------------------------

    def _check_activation(self):
        self.lbl_activation.setText("Checking…")
        self._run("activation", ["lockdown", "info"])

    def _handle_activation(self, ok: bool, out: str):
        if not ok:
            self.lbl_activation.setText("Unavailable")
            self.lbl_activation.setStyleSheet("color: #ff5252;")
            self._log(f"[-] Activation check failed: {out}")
            return
        try:
            state = json.loads(out).get("ActivationState", "Unknown")
        except Exception:
            state = "Unknown"
        activated = str(state).lower() in ("activated", "wildcardactivated")
        self.lbl_activation.setText(str(state))
        self.lbl_activation.setStyleSheet(
            f"color: {'#00e676' if activated else '#f0a500'};"
        )
        self._log(f"[+] Activation state: {state}")
