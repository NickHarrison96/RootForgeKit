# =============================================================================
# RootForgeKit — Hardware Health & Telemetry Inspector Tab
# Async hardware telemetry querying, disk partition health breakdown,
# battery metrics, and SMART status monitoring console.
# =============================================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QTextEdit, QGroupBox, QSplitter
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from utils.hardware_inspector import (
    get_battery_telemetry,
    get_disk_health_metrics,
    query_smart_data_windows
)


class HardwareHealthWorker(QThread):
    """Asynchronously query battery, disk partitions, and SMART status."""
    data_ready = Signal(dict)

    def run(self):
        battery = get_battery_telemetry()
        disks = get_disk_health_metrics()
        smart = query_smart_data_windows()

        self.data_ready.emit({
            "battery": battery,
            "disks": disks,
            "smart": smart
        })


class HardwareHealthTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.refresh_telemetry()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Header Bar ──────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        
        t = QLabel("🩺 Hardware Health & Disk Inspector")
        t.setObjectName("TabSectionTitle")
        t.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        
        sub = QLabel("Monitor system battery metrics, partition storage distribution, and SMART drive health.")
        sub.setObjectName("TabSubtitle")
        
        title_col.addWidget(t)
        title_col.addWidget(sub)
        header_row.addLayout(title_col, stretch=1)

        self.btn_refresh = QPushButton("🔄 Refresh Telemetry")
        self.btn_refresh.setObjectName("MobileQuickBtn")
        self.btn_refresh.setMinimumHeight(30)
        self.btn_refresh.clicked.connect(self.refresh_telemetry)
        header_row.addWidget(self.btn_refresh)

        layout.addLayout(header_row)

        # ── Battery Status Card ─────────────────────────────────────────────
        self.battery_card = QFrame()
        self.battery_card.setObjectName("SpecCard")
        batt_layout = QHBoxLayout(self.battery_card)
        batt_layout.setContentsMargins(16, 12, 16, 12)

        self.lbl_battery_icon = QLabel("🔋")
        self.lbl_battery_icon.setFont(QFont("Segoe UI Emoji", 24))
        batt_layout.addWidget(self.lbl_battery_icon)

        batt_info_col = QVBoxLayout()
        self.lbl_battery_title = QLabel("System Battery Status: Querying...")
        self.lbl_battery_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        
        self.lbl_battery_details = QLabel("Plugged In: -- | Remaining: --")
        self.lbl_battery_details.setStyleSheet("color: #8b949e;")
        batt_info_col.addWidget(self.lbl_battery_title)
        batt_info_col.addWidget(self.lbl_battery_details)
        batt_layout.addLayout(batt_info_col, stretch=1)

        self.battery_bar = QProgressBar()
        self.battery_bar.setValue(0)
        self.battery_bar.setFixedWidth(180)
        self.battery_bar.setFixedHeight(22)
        batt_layout.addWidget(self.battery_bar)

        layout.addWidget(self.battery_card)

        # ── Splitter: Top = Partition Table, Bottom = SMART Console ────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)

        # ── Disk Partition Breakdown Table ──────────────────────────────────
        table_group = QGroupBox("💾 Disk Partitions & Storage Distribution")
        tg_layout = QVBoxLayout(table_group)

        self.disk_table = QTableWidget()
        self.disk_table.setColumnCount(6)
        self.disk_table.setHorizontalHeaderLabels([
            "Device", "Mount", "File System", "Total (GB)", "Free (GB)", "Usage (%)"
        ])
        self.disk_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.disk_table.setStyleSheet(
            "QTableWidget { background-color: #161b22; color: #e6edf3; border: 1px solid #30363d; gridline-color: #30363d; }"
            "QHeaderView::section { background-color: #1c2333; color: #00e5ff; font-weight: bold; padding: 6px; border: 1px solid #30363d; }"
        )
        tg_layout.addWidget(self.disk_table)
        splitter.addWidget(table_group)

        # ── SMART Health Terminal Console ────────────────────────────────────
        smart_group = QGroupBox("🛡️ Storage SMART Operational Status (PowerShell)")
        sg_layout = QVBoxLayout(smart_group)

        self.smart_console = QTextEdit()
        self.smart_console.setReadOnly(True)
        self.smart_console.setStyleSheet(
            "font-family: monospace; background-color: #0a0e14; color: #00e676; "
            "border: 1px solid #30363d; padding: 10px; border-radius: 6px;"
        )
        sg_layout.addWidget(self.smart_console)
        splitter.addWidget(smart_group)

        splitter.setSizes([260, 220])
        layout.addWidget(splitter, stretch=1)

    def refresh_telemetry(self):
        self.btn_refresh.setEnabled(False)
        self.lbl_battery_title.setText("System Battery Status: Querying telemetry...")
        
        self.worker = HardwareHealthWorker()
        self.worker.data_ready.connect(self._on_telemetry_ready)
        self.worker.start()

    def _on_telemetry_ready(self, data: dict):
        self.btn_refresh.setEnabled(True)

        # 1. Update Battery Status Card
        batt = data.get("battery", {})
        if batt.get("available"):
            pct = int(batt.get("percent", 0))
            self.battery_bar.setValue(pct)
            plugged_icon = "⚡ AC Power" if batt.get("plugged") else "🔋 Battery Power"
            self.lbl_battery_title.setText(f"Battery: {pct}% ({batt.get('status')})")
            self.lbl_battery_details.setText(f"Power Source: {plugged_icon} | {batt.get('time_left')}")
        else:
            self.battery_bar.setValue(100)
            self.lbl_battery_title.setText(f"Battery Status: {batt.get('status')}")
            self.lbl_battery_details.setText(f"Power Source: {batt.get('time_left')}")

        # 2. Update Partition Table
        disks = data.get("disks", [])
        self.disk_table.setRowCount(len(disks))
        for row, disk in enumerate(disks):
            self.disk_table.setItem(row, 0, QTableWidgetItem(disk.get("device")))
            self.disk_table.setItem(row, 1, QTableWidgetItem(disk.get("mountpoint")))
            self.disk_table.setItem(row, 2, QTableWidgetItem(disk.get("fstype")))
            self.disk_table.setItem(row, 3, QTableWidgetItem(str(disk.get("total_gb"))))
            self.disk_table.setItem(row, 4, QTableWidgetItem(str(disk.get("free_gb"))))

            pct_item = QTableWidgetItem(f"{disk.get('percent')}%")
            if disk.get('percent') > 85:
                pct_item.setForeground(Qt.GlobalColor.red)
            self.disk_table.setItem(row, 5, pct_item)

        # 3. Update SMART Console Output
        smart_data = data.get("smart", [])
        self.smart_console.clear()
        self.smart_console.append("=== STORAGE DRIVE SMART HEALTH SUMMARY ===")
        for d in smart_data:
            dev_id = d.get("device_id", "?")
            model = d.get("model", "Unknown")
            media = d.get("media_type", "N/A")
            health = d.get("health", "Unknown")
            status = d.get("status", "Unknown")
            size = d.get("size_gb", 0)

            health_icon = "✅" if health.lower() in ("healthy", "ok") else "⚠️"
            self.smart_console.append(
                f"{health_icon} Drive [{dev_id}] {model} ({media}, {size} GB)\n"
                f"   Health Status: {health} | Operational Status: {status}\n"
                f"   ------------------------------------------------------------"
            )
