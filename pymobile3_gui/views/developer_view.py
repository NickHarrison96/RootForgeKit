"""
Pymobile3-GUI - Developer Tools & DVT Instruments Workspace
Unified developer workspace with progressive readiness flow (Dev Mode -> DDI -> RSD Tunnel)
and interactive DVT instruments (Process Manager, Live Screenshot, GPS Simulator).
"""

import sys
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QScrollArea, QMessageBox, QDoubleSpinBox, QComboBox,
    QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCursor, QPixmap
from pymobile3_gui.ui.theme import Colors
from pymobile3_gui.core.backend.tunnel_manager import (
    run_developer_command, get_tunnel_manager, is_admin
)
from pymobile3_gui.core.backend.resource_manager import safe_run_command


LOCATION_PRESETS = [
    ("San Francisco", 37.774929, -122.419416),
    ("New York",      40.712776,  -74.005974),
    ("London",        51.507351,   -0.127758),
    ("Tokyo",         35.689487,  139.691711),
    ("Paris",         48.856614,    2.352222),
]


class DvtProcessWorker(QThread):
    procs_loaded = Signal(list)
    error_signal = Signal(str)

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


class DeveloperView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc_worker = None

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 32)
        layout.setSpacing(22)

        # ── Header ───────────────────────────────────────────────────
        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(2)
        lbl_eyebrow = QLabel("DEVELOPER SERVICES & DVT INSTRUMENTATION", self)
        lbl_eyebrow.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {Colors.TEXT_MUTED}; letter-spacing: 1px;")
        header_vbox.addWidget(lbl_eyebrow)

        lbl_title = QLabel("Developer Tools", self)
        lbl_title.setStyleSheet("font-size: 24px; font-weight: 750; color: #ffffff; letter-spacing: -0.5px;")
        header_vbox.addWidget(lbl_title)
        layout.addLayout(header_vbox)

        # ── 1. Progressive Readiness Flow ─────────────────────────────
        lbl_flow = QLabel("DEVELOPER READINESS PIPELINE", self)
        lbl_flow.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {Colors.TEXT_MUTED}; letter-spacing: 1px;")
        layout.addWidget(lbl_flow)

        readiness_frame = QFrame(self)
        readiness_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 14px;
                padding: 16px;
            }}
        """)
        readiness_layout = QHBoxLayout(readiness_frame)
        readiness_layout.setContentsMargins(14, 12, 14, 12)
        readiness_layout.setSpacing(16)

        # Step 1: Dev Mode
        box_step1 = QVBoxLayout()
        lbl_s1_t = QLabel("1. Developer Mode", self)
        lbl_s1_t.setStyleSheet("font-size: 12px; font-weight: 700; color: #fff;")
        lbl_s1_d = QLabel("Enable AMFI developer mode on device", self)
        lbl_s1_d.setStyleSheet(f"font-size: 10px; color: {Colors.TEXT_MUTED};")
        btn_s1 = QPushButton("Enable Dev Mode", self)
        btn_s1.clicked.connect(self._enable_dev_mode)
        box_step1.addWidget(lbl_s1_t)
        box_step1.addWidget(lbl_s1_d)
        box_step1.addWidget(btn_s1)
        readiness_layout.addLayout(box_step1)

        # Step 2: DDI Mount
        box_step2 = QVBoxLayout()
        lbl_s2_t = QLabel("2. DDI Image", self)
        lbl_s2_t.setStyleSheet("font-size: 12px; font-weight: 700; color: #fff;")
        lbl_s2_d = QLabel("Mount Developer Disk Image", self)
        lbl_s2_d.setStyleSheet(f"font-size: 10px; color: {Colors.TEXT_MUTED};")
        btn_s2 = QPushButton("Auto-Mount DDI", self)
        btn_s2.clicked.connect(self._mount_ddi)
        box_step2.addWidget(lbl_s2_t)
        box_step2.addWidget(lbl_s2_d)
        box_step2.addWidget(btn_s2)
        readiness_layout.addLayout(box_step2)

        # Step 3: Tunneld (RSD)
        box_step3 = QVBoxLayout()
        lbl_s3_t = QLabel("3. RSD Tunnel", self)
        lbl_s3_t.setStyleSheet("font-size: 12px; font-weight: 700; color: #fff;")
        lbl_s3_d = QLabel("Start RemoteXPC tunnel (iOS 17+)", self)
        lbl_s3_d.setStyleSheet(f"font-size: 10px; color: {Colors.TEXT_MUTED};")
        self.btn_tunnel = QPushButton("Start Tunnel", self)
        self.btn_tunnel.clicked.connect(self._toggle_tunnel)
        box_step3.addWidget(lbl_s3_t)
        box_step3.addWidget(lbl_s3_d)
        box_step3.addWidget(self.btn_tunnel)
        readiness_layout.addLayout(box_step3)

        layout.addWidget(readiness_frame)

        # ── 2. Instruments Tabs ───────────────────────────────────────
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                background: {Colors.BG_SURFACE};
                border-radius: 12px;
                padding: 12px;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                padding: 8px 18px;
                font-weight: 600;
                font-size: 12px;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: #ffffff;
                border-bottom: 2px solid {Colors.ACCENT_PRIMARY};
            }}
        """)

        # ── Tab A: Process Monitor ───────────────────────────────────
        proc_widget = QWidget()
        proc_layout = QVBoxLayout(proc_widget)
        proc_layout.setContentsMargins(8, 8, 8, 8)
        proc_layout.setSpacing(10)

        proc_top = QHBoxLayout()
        self.lbl_proc_status = QLabel("Requires mounted DDI (and RSD tunnel on iOS 17+).", self)
        self.lbl_proc_status.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_MUTED};")
        proc_top.addWidget(self.lbl_proc_status, stretch=1)

        btn_refresh_procs = QPushButton("⟳ Query Processes", self)
        btn_refresh_procs.clicked.connect(self._fetch_processes)
        proc_top.addWidget(btn_refresh_procs)
        proc_layout.addLayout(proc_top)

        self.proc_table = QTableWidget(0, 4, self)
        self.proc_table.setHorizontalHeaderLabels(["PID", "Process Name", "Application Name", "App?"])
        self.proc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        proc_layout.addWidget(self.proc_table)
        self.tabs.addTab(proc_widget, "⚡ Process Monitor")

        # ── Tab B: Screenshot Capture ─────────────────────────────────
        shot_widget = QWidget()
        shot_layout = QVBoxLayout(shot_widget)
        shot_layout.setContentsMargins(14, 14, 14, 14)
        shot_layout.setSpacing(12)

        shot_top = QHBoxLayout()
        btn_take_shot = QPushButton("📸 Capture Screen", self)
        btn_take_shot.clicked.connect(self._take_screenshot)
        shot_top.addWidget(btn_take_shot)
        shot_top.addStretch()
        shot_layout.addLayout(shot_top)

        self.lbl_shot_preview = QLabel("No screenshot captured yet.", self)
        self.lbl_shot_preview.setAlignment(Qt.AlignCenter)
        self.lbl_shot_preview.setStyleSheet(f"""
            background-color: {Colors.BG_CARD};
            border: 1px dashed {Colors.BORDER_MUTED};
            border-radius: 10px;
            color: {Colors.TEXT_MUTED};
            min-height: 280px;
        """)
        shot_layout.addWidget(self.lbl_shot_preview)
        self.tabs.addTab(shot_widget, "📷 Screen Capture")

        # ── Tab C: GPS Simulator ──────────────────────────────────────
        gps_widget = QWidget()
        gps_layout = QVBoxLayout(gps_widget)
        gps_layout.setContentsMargins(14, 14, 14, 14)
        gps_layout.setSpacing(12)

        lbl_gps_d = QLabel("Override device location hardware readings with custom coordinates.", self)
        lbl_gps_d.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_MUTED};")
        gps_layout.addWidget(lbl_gps_d)

        form_box = QGridLayout()
        form_box.addWidget(QLabel("Preset:"), 0, 0)
        self.cmb_presets = QComboBox(self)
        for label, lat, lon in LOCATION_PRESETS:
            self.cmb_presets.addItem(label, (lat, lon))
        self.cmb_presets.currentIndexChanged.connect(self._on_preset_changed)
        form_box.addWidget(self.cmb_presets, 0, 1)

        form_box.addWidget(QLabel("Latitude:"), 1, 0)
        self.spin_lat = QDoubleSpinBox(self)
        self.spin_lat.setRange(-90.0, 90.0)
        self.spin_lat.setDecimals(6)
        self.spin_lat.setValue(37.774929)
        form_box.addWidget(self.spin_lat, 1, 1)

        form_box.addWidget(QLabel("Longitude:"), 2, 0)
        self.spin_lon = QDoubleSpinBox(self)
        self.spin_lon.setRange(-180.0, 180.0)
        self.spin_lon.setDecimals(6)
        self.spin_lon.setValue(-122.419416)
        form_box.addWidget(self.spin_lon, 2, 1)
        gps_layout.addLayout(form_box)

        gps_btns = QHBoxLayout()
        btn_apply_gps = QPushButton("📍 Set Simulated Location", self)
        btn_apply_gps.clicked.connect(self._set_location)
        btn_clear_gps = QPushButton("✕ Stop Simulation", self)
        btn_clear_gps.clicked.connect(self._clear_location)
        gps_btns.addWidget(btn_apply_gps)
        gps_btns.addWidget(btn_clear_gps)
        gps_btns.addStretch()
        gps_layout.addLayout(gps_btns)
        gps_layout.addStretch()

        self.tabs.addTab(gps_widget, "📍 GPS Location Simulation")
        layout.addWidget(self.tabs)

        layout.addStretch()
        scroll.setWidget(content)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _enable_dev_mode(self):
        ok, out = safe_run_command([sys.executable, "-m", "pymobiledevice3", "amfi", "enable-developer-mode"])
        if ok:
            QMessageBox.information(self, "Developer Mode", "Command sent. Device may prompt to reboot and confirm in Settings > Privacy & Security.")
        else:
            QMessageBox.critical(self, "Error", f"Failed: {out}")

    def _mount_ddi(self):
        ok, out = safe_run_command([sys.executable, "-m", "pymobiledevice3", "mounter", "auto-mount"])
        if ok:
            QMessageBox.information(self, "DDI Mounted", "Developer Disk Image mounted successfully.")
        else:
            QMessageBox.critical(self, "Mount Failed", f"Error mounting DDI: {out}")

    def _toggle_tunnel(self):
        tm = get_tunnel_manager()
        if tm.is_running():
            tm.stop()
            self.btn_tunnel.setText("Start Tunnel")
            QMessageBox.information(self, "Tunnel", "RSD Tunnel stopped.")
        else:
            ok, msg = tm.start()
            if ok:
                self.btn_tunnel.setText("Stop Tunnel")
                QMessageBox.information(self, "Tunnel", "RSD Tunnel active.")
            else:
                QMessageBox.critical(self, "Tunnel Error", msg)

    def _fetch_processes(self):
        self.lbl_proc_status.setText("Querying processes via DVT...")
        self.proc_table.setRowCount(0)
        self.proc_worker = DvtProcessWorker()
        self.proc_worker.procs_loaded.connect(self._on_procs_loaded)
        self.proc_worker.error_signal.connect(lambda e: self.lbl_proc_status.setText(f"Error: {e}"))
        self.proc_worker.start()

    def _on_procs_loaded(self, procs: list):
        self.proc_table.setRowCount(len(procs))
        for row, p in enumerate(procs):
            self.proc_table.setItem(row, 0, QTableWidgetItem(str(p.get("pid", ""))))
            self.proc_table.setItem(row, 1, QTableWidgetItem(str(p.get("name", ""))))
            self.proc_table.setItem(row, 2, QTableWidgetItem(str(p.get("realName", ""))))
            self.proc_table.setItem(row, 3, QTableWidgetItem(str(p.get("isApp", ""))))
        self.lbl_proc_status.setText(f"Loaded {len(procs)} active processes.")

    def _take_screenshot(self):
        shot_path = os.path.abspath("temp_shot.png")
        ok, out = run_developer_command(["developer", "dvt", "screenshot", shot_path])
        if ok and os.path.exists(shot_path):
            pix = QPixmap(shot_path)
            scaled = pix.scaledToHeight(380, Qt.SmoothTransformation)
            self.lbl_shot_preview.setPixmap(scaled)
        else:
            QMessageBox.critical(self, "Screenshot Failed", f"Could not capture screen:\n{out}")

    def _on_preset_changed(self, index: int):
        data = self.cmb_presets.currentData()
        if data:
            lat, lon = data
            self.spin_lat.setValue(lat)
            self.spin_lon.setValue(lon)

    def _set_location(self):
        lat = self.spin_lat.value()
        lon = self.spin_lon.value()
        ok, out = run_developer_command(["developer", "dvt", "simulate-location", "set", "--", str(lat), str(lon)])
        if ok:
            QMessageBox.information(self, "Location Set", f"Simulated GPS set to:\n{lat}, {lon}")
        else:
            QMessageBox.critical(self, "Simulation Error", out)

    def _clear_location(self):
        ok, out = run_developer_command(["developer", "dvt", "simulate-location", "clear"])
        if ok:
            QMessageBox.information(self, "Cleared", "Hardware location simulation stopped.")
        else:
            QMessageBox.critical(self, "Clear Error", out)
