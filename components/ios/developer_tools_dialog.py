# =============================================================================
# RootForgeKit — iOS Developer Tools & DDI Manager Modal (PySide6)
# AMFI Developer Mode, Developer Disk Image (DDI) Mounter,
# RemoteXPC / RSD tunnel control (iOS 17+).
#
# On iOS 17+ every developer service (DVT proclist, screenshot, location
# simulation, app launch) is only reachable through an RSD tunnel. This dialog
# is the single place to bring up all three preconditions:
#   1. Administrator privileges  (tunnel interface creation)
#   2. tunneld daemon running    (RSD transport)
#   3. Developer Mode + DDI      (device-side services)
# =============================================================================

import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QPlainTextEdit, QMessageBox, QWidget, QFrame, QGroupBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from components.progress_panel import OperationProgressPanel
from utils.process_runner import StreamingProcessRunner
from utils.resource_manager import safe_run_command
from utils.ios_core.tunnel_manager import (
    TunneldManager, get_tunnel_manager, is_admin, needs_tunnel,
    run_developer_command, TUNNELD_URL,
)


class DevToolsWorker(QThread):
    """Runs one setup action off the UI thread."""
    finished_signal = Signal(bool, str)

    def __init__(self, action: str):
        super().__init__()
        self.action = action

    def run(self):
        tm = get_tunnel_manager()

        if self.action == "start_tunnel":
            # Long-lived daemon — TunneldManager spawns it detached and polls
            # for readiness rather than blocking on process exit.
            ok, msg = tm.start()
            self.finished_signal.emit(ok, msg)
            return

        if self.action == "restart_tunnel":
            stopped, stop_msg = tm.stop()
            if not stopped and tm.is_running():
                # An elevated daemon we did not spawn cannot be signalled from here.
                self.finished_signal.emit(False, (
                    f"{stop_msg}\n\nThe running tunnel was started outside this app. "
                    "Close that elevated tunneld window (or end the python process "
                    "running 'remote tunneld'), then press Start Tunnel."
                ))
                return
            ok, msg = tm.start()
            self.finished_signal.emit(ok, msg)
            return

        if self.action == "stop_tunnel":
            ok, msg = tm.stop()
            self.finished_signal.emit(ok, msg)
            return

        if self.action == "enable_dev_mode":
            cmd = [sys.executable, "-m", "pymobiledevice3", "amfi", "enable-developer-mode"]
        else:
            self.finished_signal.emit(False, f"Unknown action: {self.action}")
            return

        ok, out = safe_run_command(cmd, timeout=120)
        self.finished_signal.emit(ok, out or "(no output)")


class StatusWorker(QThread):
    """Collects device/tunnel state without freezing the UI."""
    status_ready = Signal(dict)

    def run(self):
        tm = get_tunnel_manager()
        tunnel_up = tm.is_running()
        status = {
            "admin": is_admin(),
            "tunneld": tunnel_up,
            "ios_version": None,
            "dev_mode": None,
            "ddi": None,
            "dvt": None,
        }

        ok, out = safe_run_command(
            [sys.executable, "-m", "pymobiledevice3", "lockdown", "info"], timeout=15
        )
        if ok:
            import json
            try:
                info = json.loads(out)
                status["ios_version"] = info.get("ProductVersion")
            except Exception:
                pass

        ok, out = safe_run_command(
            [sys.executable, "-m", "pymobiledevice3", "amfi", "developer-mode-status"], timeout=15
        )
        if ok:
            status["dev_mode"] = "true" in out.strip().lower()

        # DDI mount state. On iOS 17+ the personalized image does not appear in
        # `mounter list` even when developer services are fully working, so this
        # is informational there — `dvt` below is the real capability signal.
        ok, out = safe_run_command(
            [sys.executable, "-m", "pymobiledevice3", "mounter", "list"], timeout=15,
            env=tm.tunnel_env() if tunnel_up else None,
        )
        if ok:
            stripped = out.strip()
            status["ddi"] = bool(stripped) and stripped not in ("[]", "{}")

        # Ground truth: can we actually reach a developer service right now?
        if tunnel_up:
            probe_ok, _ = run_developer_command(
                ["developer", "dvt", "proclist"], timeout=40
            )
            status["dvt"] = probe_ok

        self.status_ready.emit(status)


class DeveloperToolsDialog(QDialog):
    """iOS Developer Tools, DDI Mounter, and RSD tunnel control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🛡️ iOS Developer Setup, DDI & Tunnel")
        self.resize(860, 620)
        self._init_ui()
        self.refresh_status()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl_title = QLabel("🛡️  Developer Setup, DDI & RSD Tunnel")
        lbl_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "iOS 17+ routes all developer services through an RSD tunnel. "
            "'Developer services' below is the signal that matters — when it is "
            "green, DVT tools will work."
        )
        lbl_desc.setStyleSheet("color: #8b949e;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # ---- Status panel ----
        status_group = QGroupBox("Readiness")
        status_grid = QGridLayout(status_group)
        status_grid.setContentsMargins(10, 6, 10, 8)
        status_grid.setSpacing(6)

        self.status_labels: dict[str, QLabel] = {}
        rows = [
            ("device",   "Device"),
            ("admin",    "Administrator"),
            ("tunneld",  "RSD tunnel (tunneld)"),
            ("dev_mode", "Developer Mode"),
            ("ddi",      "Developer Disk Image"),
            ("dvt",      "Developer services"),
        ]
        for row, (key, label) in enumerate(rows):
            name = QLabel(label)
            name.setStyleSheet("color: #8b949e;")
            name.setFixedWidth(170)
            value = QLabel("Checking…")
            value.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            self.status_labels[key] = value
            status_grid.addWidget(name, row, 0)
            status_grid.addWidget(value, row, 1)
        status_grid.setColumnStretch(1, 1)
        layout.addWidget(status_group)

        # ---- Actions ----
        actions = QHBoxLayout()
        actions.setSpacing(6)

        self.btn_refresh = QPushButton("🔄  Refresh Status")
        self.btn_refresh.clicked.connect(self.refresh_status)
        actions.addWidget(self.btn_refresh)

        self.btn_tunnel = QPushButton("📡  Start Tunnel")
        self.btn_tunnel.setToolTip(
            "Starts the tunneld daemon. Requires Administrator — a UAC prompt will appear."
        )
        self.btn_tunnel.clicked.connect(self._on_tunnel_clicked)
        actions.addWidget(self.btn_tunnel)

        self.btn_amfi = QPushButton("⚡  Enable Developer Mode")
        self.btn_amfi.setToolTip(
            "Enables Developer Mode on the device (iOS 16+). The device may reboot "
            "and will ask you to confirm on-screen."
        )
        self.btn_amfi.clicked.connect(lambda: self._run_action("enable_dev_mode"))
        actions.addWidget(self.btn_amfi)

        self.btn_ddi = QPushButton("💽  Auto-Mount DDI")
        self.btn_ddi.setToolTip(
            "Downloads and mounts the matching Developer Disk Image.\n"
            "The download can take several minutes on first run."
        )
        self.btn_ddi.clicked.connect(self._mount_ddi)
        actions.addWidget(self.btn_ddi)

        actions.addStretch()
        layout.addLayout(actions)

        # Streaming progress for the DDI mount (downloads a large image, so it
        # must not run under a fixed timeout).
        self.runner = StreamingProcessRunner(self)
        self.progress = OperationProgressPanel()
        self.progress.bind(self.runner)
        self.runner.finished.connect(self._on_ddi_finished)
        layout.addWidget(self.progress)

        # ---- Log ----
        lbl_log = QLabel("Output Log:")
        lbl_log.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        layout.addWidget(lbl_log)

        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QFont("Consolas", 9))
        self.log_console.setMinimumHeight(60)
        self.log_console.setStyleSheet(
            "background-color: #0d1117; color: #7ee787; "
            "border: 1px solid #30363d; border-radius: 6px;"
        )
        layout.addWidget(self.log_console, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    def refresh_status(self):
        """Re-collect readiness state in the background."""
        for lbl in self.status_labels.values():
            lbl.setText("Checking…")
            lbl.setStyleSheet("color: #8b949e;")
        self.btn_refresh.setEnabled(False)

        self._status_worker = StatusWorker()
        self._status_worker.status_ready.connect(self._on_status_ready)
        self._status_worker.start()

    def _set_status(self, key: str, ok: bool | None, text: str):
        lbl = self.status_labels.get(key)
        if not lbl:
            return
        colors = {True: "#00e676", False: "#ff5252", None: "#8b949e"}
        lbl.setText(text)
        lbl.setStyleSheet(f"color: {colors.get(ok, '#8b949e')};")

    def _on_status_ready(self, status: dict):
        self.btn_refresh.setEnabled(True)

        # Elevation only matters for *starting* the tunnel; once it is up an
        # unelevated app talks to the local daemon just fine.
        if status["admin"]:
            self._set_status("admin", True, "Elevated")
        elif status["tunneld"]:
            self._set_status("admin", None, "Not elevated — not needed, tunnel already up")
        else:
            self._set_status("admin", False, "Not elevated — tunnel start will prompt for UAC")

        self._set_status("tunneld", status["tunneld"],
                         f"Running on {TUNNELD_URL}" if status["tunneld"]
                         else "Not running")
        self._tunnel_running = status["tunneld"]
        self.btn_tunnel.setText("📡  Restart Tunnel" if status["tunneld"] else "📡  Start Tunnel")

        version = status.get("ios_version")
        if version:
            required = needs_tunnel(version)
            self._set_status("device", True,
                             f"iOS {version} — {'tunnel required' if required else 'tunnel not required'}")
        else:
            self._set_status("device", False, "No device detected over USB")

        dev_mode = status.get("dev_mode")
        self._set_status("dev_mode", dev_mode,
                         {True: "Enabled", False: "Disabled", None: "Unknown"}[dev_mode]
                         if dev_mode in (True, False, None) else "Unknown")

        dvt = status.get("dvt")
        rsd_era = needs_tunnel(version) if version else False

        # On iOS 17+ a working tunnel serves developer services without the
        # image showing up in `mounter list` — don't flag that as a failure.
        ddi = status.get("ddi")
        if ddi:
            self._set_status("ddi", True, "Mounted")
        elif rsd_era and dvt:
            self._set_status("ddi", None, "Not listed — not required over RSD")
        elif ddi is False:
            self._set_status("ddi", False, "Not mounted")
        else:
            self._set_status("ddi", None, "Unknown")

        if dvt is None:
            self._set_status("dvt", None, "Not probed — tunnel is down")
        else:
            self._set_status("dvt", dvt,
                             "Reachable — DVT tools working" if dvt
                             else "Unreachable — DVT calls will fail")

        # Actionable summary, driven by real capability rather than inference
        blockers = []
        if not status["tunneld"]:
            blockers.append("start the RSD tunnel")
        if status.get("dev_mode") is False:
            blockers.append("enable Developer Mode")
        if dvt is False and not rsd_era and ddi is False:
            blockers.append("mount the DDI")

        if dvt:
            summary = "[+] Developer services are reachable — DVT tools are ready."
        elif blockers:
            summary = "[!] DVT tools are blocked. Remaining steps: " + ", ".join(blockers) + "."
        else:
            summary = ("[!] Developer services unreachable. Try remounting the DDI, "
                       "then restart the tunnel.")

        # Only log when the verdict changes — refreshes fire often and would
        # otherwise fill the console with identical lines.
        if summary != getattr(self, "_last_summary", None):
            self.log_console.appendPlainText(summary)
            self._last_summary = summary

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def _mount_ddi(self):
        """Mount the DDI with live progress and no timeout."""
        if self.runner.is_running():
            QMessageBox.information(self, "Busy", "An operation is already running.")
            return
        self.log_console.appendPlainText(
            "[*] Mounting Developer Disk Image (first run downloads the image)…"
        )
        self._set_actions_enabled(False)
        self.progress.begin("💽  Mounting Developer Disk Image")
        self.runner.start(["-m", "pymobiledevice3", "mounter", "auto-mount"])

    def _on_ddi_finished(self, ok: bool, message: str):
        self._set_actions_enabled(True)
        self.log_console.appendPlainText(f"{'[+]' if ok else '[-]'} {message}")
        self.refresh_status()

    def _on_tunnel_clicked(self):
        """Start, or genuinely restart when a tunnel is already up."""
        self._run_action("restart_tunnel" if getattr(self, "_tunnel_running", False)
                         else "start_tunnel")

    def _run_action(self, action: str):
        labels = {
            "start_tunnel": "Starting RSD tunnel (approve the elevation prompt)…",
            "restart_tunnel": "Restarting RSD tunnel…",
            "stop_tunnel": "Stopping RSD tunnel…",
            "enable_dev_mode": "Enabling Developer Mode (confirm on the device)…",
            "mount_ddi": "Mounting Developer Disk Image (may download first)…",
        }
        self.log_console.appendPlainText(f"[*] {labels.get(action, action)}")
        self._set_actions_enabled(False)

        self._worker = DevToolsWorker(action)
        self._worker.finished_signal.connect(self._on_action_finished)
        self._worker.start()

    def _set_actions_enabled(self, enabled: bool):
        for btn in (self.btn_tunnel, self.btn_amfi, self.btn_ddi, self.btn_refresh):
            btn.setEnabled(enabled)

    def _on_action_finished(self, ok: bool, output: str):
        self._set_actions_enabled(True)
        if ok:
            self.log_console.appendPlainText(f"[+] {output}\n")
        else:
            self.log_console.appendPlainText(f"[-] {output}\n")
            QMessageBox.warning(self, "Operation Failed", output)
        self.refresh_status()
