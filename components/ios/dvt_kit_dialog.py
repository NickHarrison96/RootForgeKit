# =============================================================================
# NicksFix — iOS DVT Kit & Instruments Modal (PyQt6)
# Processes, Live Screenshot, GPS Location Simulation, Power Assertions, System Monitor
# =============================================================================

import os
import subprocess
import sys
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QWidget, QFrame, QComboBox, QDoubleSpinBox,
    QPlainTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

from utils.ios_core.tunnel_manager import run_developer_command, get_tunnel_manager


# Quick-pick coordinates for the location simulator: (label, lat, lon)
LOCATION_PRESETS = [
    ("San Francisco", 37.774929, -122.419416),
    ("New York",      40.712776,  -74.005974),
    ("London",        51.507351,   -0.127758),
    ("Tokyo",         35.689487,  139.691711),
]


class DvtProcessWorker(QThread):
    procs_loaded = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def run(self):
        ok, out = run_developer_command(["developer", "dvt", "proclist"], timeout=20)

        if not ok:
            self.error_signal.emit(f"Failed to fetch processes:\n{out}")
            return

        try:
            data = json.loads(out)
            procs = []
            if isinstance(data, list):
                for item in data:
                    procs.append({
                        "pid": item.get("pid", 0),
                        "name": item.get("name", "Unknown"),
                        "realName": item.get("realAppName", ""),
                        "isApp": "Yes" if item.get("isApplication") else "No",
                        "startDate": item.get("startDate", "")
                    })
            procs.sort(key=lambda x: x["pid"])
            self.procs_loaded.emit(procs)
        except Exception as e:
            self.error_signal.emit(f"Error parsing process list: {e}")


class DvtKitDialog(QDialog):
    """
    iOS DVT Kit Instruments modal dialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🛠️ iOS DVT Kit & Developer Instruments")
        self.resize(920, 620)
        self._power_proc: subprocess.Popen | None = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 10))

        # ── Tab 1: Running Processes ────────────────────────────────────────
        proc_tab = QWidget()
        proc_layout = QVBoxLayout(proc_tab)
        proc_layout.setContentsMargins(10, 10, 10, 10)
        proc_layout.setSpacing(8)

        proc_top = QHBoxLayout()
        self.proc_status = QLabel("Query running processes on device (Requires DDI).")
        self.proc_status.setStyleSheet("color: #8b949e;")
        proc_top.addWidget(self.proc_status, stretch=1)

        btn_fetch_procs = QPushButton("🔄 Refresh Processes")
        btn_fetch_procs.clicked.connect(self._fetch_processes)
        proc_top.addWidget(btn_fetch_procs)
        proc_layout.addLayout(proc_top)

        self.proc_table = QTableWidget(0, 5)
        self.proc_table.setHorizontalHeaderLabels(["PID", "Process Name", "App Display Name", "Is App", "Start Date"])
        self.proc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.proc_table.setStyleSheet("background-color: #161b22; color: #e6edf3; gridline-color: #30363d;")
        proc_layout.addWidget(self.proc_table, stretch=1)

        self.tabs.addTab(proc_tab, "⚡ Processes")

        # ── Tab 2: Live Screenshot ──────────────────────────────────────────
        shot_tab = QWidget()
        shot_layout = QVBoxLayout(shot_tab)
        shot_layout.setContentsMargins(10, 10, 10, 10)
        shot_layout.setSpacing(8)

        shot_top = QHBoxLayout()
        btn_take_shot = QPushButton("📸 Take Screenshot")
        btn_take_shot.clicked.connect(self._take_screenshot)
        shot_top.addWidget(btn_take_shot)

        btn_save_shot = QPushButton("💾 Save Screenshot")
        btn_save_shot.clicked.connect(self._save_screenshot)
        shot_top.addWidget(btn_save_shot)

        self.shot_status = QLabel("Click 'Take Screenshot' to capture screen.")
        self.shot_status.setStyleSheet("color: #8b949e;")
        shot_top.addWidget(self.shot_status, stretch=1)
        shot_layout.addLayout(shot_top)

        self.shot_label = QLabel()
        self.shot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shot_label.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px;")
        shot_layout.addWidget(self.shot_label, stretch=1)

        self.tabs.addTab(shot_tab, "📸 Screenshot")

        # ── Tab 3: Location Simulator ───────────────────────────────────────
        loc_tab = QWidget()
        loc_layout = QVBoxLayout(loc_tab)
        loc_layout.setContentsMargins(14, 14, 14, 14)
        loc_layout.setSpacing(12)

        lbl_loc = QLabel("🌐 GPS Location Simulation")
        lbl_loc.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        loc_layout.addWidget(lbl_loc)

        lbl_loc_desc = QLabel("Set mock GPS coordinates on the iOS device (Requires DDI).")
        lbl_loc_desc.setStyleSheet("color: #8b949e;")
        loc_layout.addWidget(lbl_loc_desc)

        coord_frame = QFrame()
        coord_layout = QHBoxLayout(coord_frame)

        coord_layout.addWidget(QLabel("Latitude:"))
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-90.0, 90.0)
        self.lat_spin.setDecimals(6)
        self.lat_spin.setValue(37.774929)  # San Francisco default
        coord_layout.addWidget(self.lat_spin)

        coord_layout.addWidget(QLabel("Longitude:"))
        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(-180.0, 180.0)
        self.lon_spin.setDecimals(6)
        self.lon_spin.setValue(-122.419416)
        coord_layout.addWidget(self.lon_spin)

        loc_layout.addWidget(coord_frame)

        # ---- Presets ----
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        lbl_presets = QLabel("Presets:")
        lbl_presets.setStyleSheet("color: #8b949e;")
        preset_row.addWidget(lbl_presets)
        for name, lat, lon in LOCATION_PRESETS:
            btn = QPushButton(name)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"{lat}, {lon}")
            btn.clicked.connect(
                lambda _c, la=lat, lo=lon: self._apply_preset(la, lo)
            )
            preset_row.addWidget(btn)
        preset_row.addStretch()
        loc_layout.addLayout(preset_row)

        btn_loc_row = QHBoxLayout()
        btn_set_loc = QPushButton("🎯 Set Location")
        btn_set_loc.clicked.connect(self._set_location)
        btn_loc_row.addWidget(btn_set_loc)

        btn_clear_loc = QPushButton("❌ Clear Simulation")
        btn_clear_loc.clicked.connect(self._clear_location)
        btn_loc_row.addWidget(btn_clear_loc)

        loc_layout.addLayout(btn_loc_row)

        self.loc_status = QLabel("Enter coordinates or pick a preset.")
        self.loc_status.setStyleSheet("color: #8b949e;")
        self.loc_status.setWordWrap(True)
        loc_layout.addWidget(self.loc_status)
        loc_layout.addStretch()

        self.tabs.addTab(loc_tab, "📍 Location Simulator")

        # ── Tab 4: Power Assertions ─────────────────────────────────────────
        power_tab = QWidget()
        power_layout = QVBoxLayout(power_tab)
        power_layout.setContentsMargins(14, 14, 14, 14)
        power_layout.setSpacing(12)

        lbl_power = QLabel("🔋 Power Assertion Control")
        lbl_power.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        power_layout.addWidget(lbl_power)

        lbl_power_desc = QLabel(
            "Checks in as the device owner via developer arbitration, marking it "
            "'in-use'. The assertion holds while the check-in process runs, which "
            "keeps the device awake for long operations."
        )
        lbl_power_desc.setStyleSheet("color: #8b949e;")
        lbl_power_desc.setWordWrap(True)
        power_layout.addWidget(lbl_power_desc)

        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("Owner name:"))
        self.power_hostname = QLineEdit("NicksFix")
        self.power_hostname.setToolTip("Identifier reported to the device as the current owner.")
        host_row.addWidget(self.power_hostname, stretch=1)
        power_layout.addLayout(host_row)

        btn_power_row = QHBoxLayout()
        self.btn_power_start = QPushButton("⚡ Hold Assertion (Check-In)")
        self.btn_power_start.clicked.connect(self._start_power_assertion)
        btn_power_row.addWidget(self.btn_power_start)

        self.btn_power_stop = QPushButton("⏹ Release (Check-Out)")
        self.btn_power_stop.clicked.connect(self._stop_power_assertion)
        self.btn_power_stop.setEnabled(False)
        btn_power_row.addWidget(self.btn_power_stop)
        power_layout.addLayout(btn_power_row)

        self.power_status = QLabel("No assertion held.")
        self.power_status.setStyleSheet("color: #8b949e;")
        self.power_status.setWordWrap(True)
        power_layout.addWidget(self.power_status)
        power_layout.addStretch()

        self.tabs.addTab(power_tab, "⚡ Power Assertion")

        # ── Tab 6: System Monitor ───────────────────────────────────────────
        self.tabs.addTab(self._build_sysmon_tab(), "📈 System Monitor")

        # ── Tab 5: App Remote Launcher ──────────────────────────────────────
        launch_tab = QWidget()
        launch_layout = QVBoxLayout(launch_tab)
        launch_layout.setContentsMargins(14, 14, 14, 14)
        launch_layout.setSpacing(12)

        lbl_launch = QLabel("🚀 App Remote Launcher")
        lbl_launch.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        launch_layout.addWidget(lbl_launch)

        self.input_bundle = QLineEdit()
        self.input_bundle.setPlaceholderText("Enter App Bundle Identifier (e.g. com.apple.mobilesafari)")
        launch_layout.addWidget(self.input_bundle)

        btn_launch = QPushButton("▶ Launch Application")
        btn_launch.clicked.connect(self._launch_app)
        launch_layout.addWidget(btn_launch)

        btn_kill = QPushButton("⛔ Kill Application")
        btn_kill.clicked.connect(self._kill_app)
        launch_layout.addWidget(btn_kill)
        launch_layout.addStretch()

        self.tabs.addTab(launch_tab, "🚀 App Launcher")

        layout.addWidget(self.tabs, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _fetch_processes(self):
        self.proc_status.setText("Fetching process list...")
        self.proc_table.setRowCount(0)

        self._worker = DvtProcessWorker()
        self._worker.procs_loaded.connect(self._on_procs_loaded)
        self._worker.error_signal.connect(self._on_procs_error)
        self._worker.start()

    def _on_procs_loaded(self, procs):
        self.proc_table.setRowCount(len(procs))
        for row, p in enumerate(procs):
            self.proc_table.setItem(row, 0, QTableWidgetItem(str(p["pid"])))
            self.proc_table.setItem(row, 1, QTableWidgetItem(str(p["name"])))
            self.proc_table.setItem(row, 2, QTableWidgetItem(str(p["realName"])))
            self.proc_table.setItem(row, 3, QTableWidgetItem(str(p["isApp"])))
            self.proc_table.setItem(row, 4, QTableWidgetItem(str(p["startDate"])))
        self.proc_status.setText(f"Loaded {len(procs)} running process(es)")

    def _on_procs_error(self, err_msg):
        self.proc_status.setText("Failed loading processes")
        QMessageBox.warning(self, "Process Query Error", err_msg)

    def _take_screenshot(self):
        self.shot_status.setText("Capturing screenshot...")
        temp_shot = "temp_shot.png"
        ok, out = run_developer_command(["developer", "dvt", "screenshot", temp_shot], timeout=25)
        if ok and os.path.exists(temp_shot):
            pixmap = QPixmap(temp_shot)
            scaled = pixmap.scaled(400, 700, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.shot_label.setPixmap(scaled)
            self.shot_status.setText("Screenshot captured!")
        else:
            self.shot_status.setText("Screenshot capture failed")
            QMessageBox.warning(self, "Screenshot Error", f"Failed capturing screenshot (requires DDI):\n{out}")

    def _save_screenshot(self):
        if not self.shot_label.pixmap():
            QMessageBox.information(self, "No Image", "Take a screenshot first.")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "screenshot.png", "PNG Images (*.png)")
        if save_path:
            self.shot_label.pixmap().save(save_path)
            QMessageBox.information(self, "Saved", f"Screenshot saved to:\n{save_path}")

    def _apply_preset(self, lat: float, lon: float):
        """Load preset coordinates into the spin boxes (does not apply them)."""
        self.lat_spin.setValue(lat)
        self.lon_spin.setValue(lon)
        self.loc_status.setText(
            f"Preset loaded: {lat}, {lon} — press 'Set Location' to apply."
        )
        self.loc_status.setStyleSheet("color: #8b949e;")

    def _set_location(self):
        lat = self.lat_spin.value()
        lon = self.lon_spin.value()
        self.loc_status.setText("Applying location…")
        ok, out = run_developer_command(
            ["developer", "dvt", "simulate-location", "set", "--", str(lat), str(lon)],
            timeout=20,
        )
        if ok:
            self.loc_status.setText(f"Location simulated: {lat}, {lon}")
            self.loc_status.setStyleSheet("color: #00e676;")
        else:
            self.loc_status.setText("Failed to set location.")
            self.loc_status.setStyleSheet("color: #ff5252;")
            QMessageBox.warning(self, "Location Simulation Error",
                                f"Failed setting mock location:\n{out}")

    def _clear_location(self):
        ok, out = run_developer_command(
            ["developer", "dvt", "simulate-location", "clear"], timeout=20
        )
        if ok:
            self.loc_status.setText("Mock location cleared — device reports real GPS.")
            self.loc_status.setStyleSheet("color: #8b949e;")
        else:
            self.loc_status.setText("Failed to clear location.")
            self.loc_status.setStyleSheet("color: #ff5252;")
            QMessageBox.warning(self, "Error", f"Failed clearing mock location:\n{out}")

    # -------------------------------------------------------------------------
    # System Monitor
    # -------------------------------------------------------------------------

    def _build_sysmon_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel("📈 System Monitor")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(lbl)

        desc = QLabel("Snapshot of device-wide system statistics via DVT sysmon.")
        desc.setStyleSheet("color: #8b949e;")
        layout.addWidget(desc)

        row = QHBoxLayout()
        btn_sys = QPushButton("🔄 Refresh System Stats")
        btn_sys.clicked.connect(self._fetch_sysmon)
        row.addWidget(btn_sys)
        self.sysmon_status = QLabel("Not sampled yet.")
        self.sysmon_status.setStyleSheet("color: #8b949e;")
        row.addWidget(self.sysmon_status, stretch=1)
        layout.addLayout(row)

        self.sysmon_view = QPlainTextEdit()
        self.sysmon_view.setReadOnly(True)
        self.sysmon_view.setFont(QFont("Consolas", 9))
        self.sysmon_view.setPlaceholderText("System statistics appear here…")
        self.sysmon_view.setStyleSheet(
            "background-color: #0d1117; color: #7ee787; "
            "border: 1px solid #30363d; border-radius: 6px;"
        )
        layout.addWidget(self.sysmon_view, stretch=1)
        return page

    def _fetch_sysmon(self):
        self.sysmon_status.setText("Sampling…")
        ok, out = run_developer_command(["developer", "dvt", "sysmon", "system"], timeout=40)
        if not ok:
            self.sysmon_status.setText("Failed")
            self.sysmon_view.setPlainText(out)
            return
        try:
            data = json.loads(out)
            lines = [f"{k:<28}: {v}" for k, v in sorted(data.items())]
            self.sysmon_view.setPlainText("\n".join(lines))
            self.sysmon_status.setText(f"{len(data)} metric(s)")
        except Exception:
            self.sysmon_view.setPlainText(out)
            self.sysmon_status.setText("Sampled")

    # -------------------------------------------------------------------------
    # Power assertion (developer arbitration check-in)
    # -------------------------------------------------------------------------

    def _start_power_assertion(self):
        if self._power_proc and self._power_proc.poll() is None:
            QMessageBox.information(self, "Already Held",
                                    "An assertion is already being held.")
            return

        hostname = self.power_hostname.text().strip() or "NicksFix"
        tm = get_tunnel_manager()
        if not tm.is_running():
            QMessageBox.warning(self, "Tunnel Required",
                                "Power assertion is a developer service and needs "
                                "an active RSD tunnel.")
            return

        # check-in holds the assertion only while the process runs, so it is
        # spawned detached rather than run to completion.
        cmd = [sys.executable, "-m", "pymobiledevice3",
               "developer", "arbitration", "check-in", hostname, "--force"]
        env = {**os.environ, **tm.tunnel_env(), "PYTHONUNBUFFERED": "1"}
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

        try:
            self._power_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, env=env, creationflags=creationflags,
            )
        except Exception as e:
            QMessageBox.warning(self, "Power Assertion Failed", str(e))
            return

        # A failure to check in surfaces almost immediately.
        try:
            self._power_proc.wait(timeout=2.5)
            err = (self._power_proc.stderr.read() if self._power_proc.stderr else "").strip()
            self._power_proc = None
            self.power_status.setText("Check-in failed.")
            self.power_status.setStyleSheet("color: #ff5252;")
            QMessageBox.warning(self, "Power Assertion Failed",
                                err or "Arbitration check-in exited immediately.")
            return
        except subprocess.TimeoutExpired:
            pass    # still running — the assertion is held

        self.power_status.setText(f"Assertion held as '{hostname}' — device marked in-use.")
        self.power_status.setStyleSheet("color: #00e676;")
        self.btn_power_start.setEnabled(False)
        self.btn_power_stop.setEnabled(True)

    def _stop_power_assertion(self):
        if self._power_proc and self._power_proc.poll() is None:
            try:
                self._power_proc.terminate()
                self._power_proc.wait(timeout=5)
            except Exception:
                try:
                    self._power_proc.kill()
                except Exception:
                    pass
        self._power_proc = None

        # Release ownership so other tools can use the device.
        run_developer_command(["developer", "arbitration", "check-out"], timeout=20)

        self.power_status.setText("Assertion released.")
        self.power_status.setStyleSheet("color: #8b949e;")
        self.btn_power_start.setEnabled(True)
        self.btn_power_stop.setEnabled(False)

    def closeEvent(self, event):
        """Never leave the device marked in-use after the dialog closes."""
        if self._power_proc and self._power_proc.poll() is None:
            self._stop_power_assertion()
        super().closeEvent(event)

    def _launch_app(self):
        bundle_id = self.input_bundle.text().strip()
        if not bundle_id:
            QMessageBox.warning(self, "Missing Bundle ID", "Enter a valid application bundle identifier.")
            return
        ok, out = run_developer_command(["developer", "dvt", "launch", bundle_id], timeout=20)
        if ok:
            QMessageBox.information(self, "Success", f"Launched application: {bundle_id}")
        else:
            QMessageBox.warning(self, "Launch Error", f"Failed to launch application:\n{out}")

    def _kill_app(self):
        bundle_id = self.input_bundle.text().strip()
        if not bundle_id:
            QMessageBox.warning(self, "Missing Bundle ID", "Enter a valid application bundle identifier.")
            return
        ok, out = run_developer_command(["developer", "dvt", "kill", bundle_id], timeout=20)
        if ok:
            QMessageBox.information(self, "Success", f"Killed application: {bundle_id}")
        else:
            QMessageBox.warning(self, "Kill Error", f"Failed to kill application:\n{out}")
