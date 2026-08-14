# =============================================================================
# NicksFix — Overview Dashboard Tab
# 3uTools-inspired split view:
#   Left Panel:  Neofetch-style OS badge (ASCII logo, hostname, kernel, uptime)
#   Right Panel: Hardware spec cards (CPU, GPU, RAM, Disk, Network, BIOS)
# =============================================================================

import platform

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QGridLayout, QProgressBar, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from utils.sys_info import SystemInfoWorker
from utils.system_info import get_system_summary


from utils.os_logo import (
    detect_os_key, render_logo, LOGO_ACCENTS, DISPLAY_NAMES,
)

# Rows rendered beside the logo: (caption, sys_info key)
INFO_ROWS = [
    ("OS",      "OS"),
    ("Kernel",  "Kernel"),
    ("Uptime",  "Uptime"),
    ("Shell",   "Shell"),
    ("Python",  "Python"),
    ("CPU",     "CPU"),
    ("Memory",  "Memory"),
]


class OverviewTab(QWidget):
    """
    Split dashboard view showing system identity and hardware metrics.
    Auto-refreshes via background SystemInfoWorker.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info_data = {}
        self._setup_ui()
        self._start_polling()

    def _setup_ui(self):
        """Build the split-pane overview layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # ---- Left Panel: OS Identity Badge ----
        self.left_panel = QFrame()
        self.left_panel.setObjectName("OverviewLeftPanel")
        self.left_panel.setFixedWidth(520)
        self.left_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(20, 24, 20, 24)
        left_layout.setSpacing(8)

        # ---- Logo + identity header ----
        self.os_key = detect_os_key()
        accent = LOGO_ACCENTS.get(self.os_key, "#00e5ff")

        header = QHBoxLayout()
        header.setSpacing(16)
        header.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("OsLogo")
        self.logo_label.setFixedSize(132, 132)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = render_logo(self.os_key, size=132)
        if pixmap:
            self.logo_label.setPixmap(pixmap)
        else:
            # No asset on disk — degrade to a text badge rather than a blank box.
            self.logo_label.setText(DISPLAY_NAMES.get(self.os_key, "?"))
            self.logo_label.setStyleSheet(f"color: {accent}; font-size: 15px; font-weight: 700;")
        header.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignTop)

        identity = QVBoxLayout()
        identity.setSpacing(2)
        identity.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.host_label = QLabel("…")
        self.host_label.setObjectName("OverviewHost")
        self.host_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.host_label.setStyleSheet(f"color: {accent};")
        identity.addWidget(self.host_label)

        self.platform_label = QLabel(DISPLAY_NAMES.get(self.os_key, ""))
        self.platform_label.setObjectName("OverviewPlatform")
        self.platform_label.setFont(QFont("Segoe UI", 10))
        self.platform_label.setStyleSheet("color: #8b949e;")
        identity.addWidget(self.platform_label)

        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet("background-color: #30363d;")
        identity.addSpacing(6)
        identity.addWidget(rule)
        identity.addSpacing(6)

        # Key/value grid — no padding math, so nothing can drift out of column.
        self.info_values: dict[str, QLabel] = {}
        info_grid = QGridLayout()
        info_grid.setContentsMargins(0, 0, 0, 0)
        info_grid.setHorizontalSpacing(10)
        info_grid.setVerticalSpacing(3)

        for row, (caption, key) in enumerate(INFO_ROWS):
            key_label = QLabel(caption)
            key_label.setObjectName("InfoKey")
            key_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            key_label.setStyleSheet(f"color: {accent};")
            key_label.setFixedWidth(58)

            value_label = QLabel("…")
            value_label.setObjectName("InfoValue")
            value_label.setFont(QFont("Segoe UI", 9))
            value_label.setWordWrap(True)
            value_label.setStyleSheet("color: #c9d1d9;")

            info_grid.addWidget(key_label, row, 0, Qt.AlignmentFlag.AlignTop)
            info_grid.addWidget(value_label, row, 1)
            self.info_values[key] = value_label

        info_grid.setColumnStretch(1, 1)
        identity.addLayout(info_grid)
        identity.addStretch()

        header.addLayout(identity, stretch=1)
        left_layout.addLayout(header)
        left_layout.addStretch()
        main_layout.addWidget(self.left_panel)

        # ---- Right Panel: Hardware Spec Cards (Scrollable) ----
        scroll = QScrollArea()
        scroll.setObjectName("OverviewScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        right_container = QWidget()
        self.right_layout = QVBoxLayout(right_container)
        self.right_layout.setContentsMargins(0, 0, 8, 0)
        self.right_layout.setSpacing(12)

        # Placeholder cards — will be populated on first data arrival
        self.cpu_card = self._create_spec_card("🔲  CPU", "Scanning...")
        self.right_layout.addWidget(self.cpu_card)

        self.gpu_card = self._create_spec_card("🎮  GPU", "Scanning...")
        self.right_layout.addWidget(self.gpu_card)

        self.ram_card = self._create_ram_card()
        self.right_layout.addWidget(self.ram_card)

        self.disk_card = self._create_spec_card("💾  Storage", "Scanning...")
        self.right_layout.addWidget(self.disk_card)

        self.network_card = self._create_spec_card("🌐  Network", "Scanning...")
        self.right_layout.addWidget(self.network_card)

        self.mobo_card = self._create_spec_card("🖥️  Motherboard / BIOS", "Scanning...")
        self.right_layout.addWidget(self.mobo_card)

        self.right_layout.addStretch()
        scroll.setWidget(right_container)
        main_layout.addWidget(scroll, stretch=1)

    # -------------------------------------------------------------------------
    # Data Polling
    # -------------------------------------------------------------------------

    def _start_polling(self):
        """Start background worker and set up auto-refresh every 10 seconds."""
        self._worker = SystemInfoWorker()
        self._worker.info_ready.connect(self._update_display)
        self._worker.start()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(10_000)  # 10-second refresh cycle

    def _refresh(self):
        """Re-launch the worker for fresh data."""
        if not self._worker.isRunning():
            self._worker = SystemInfoWorker()
            self._worker.info_ready.connect(self._update_display)
            self._worker.start()

    # -------------------------------------------------------------------------
    # Display Update
    # -------------------------------------------------------------------------

    def _update_display(self, data: dict):
        """Receive telemetry dict and update all UI elements."""
        self._info_data = data

        # ---- Left panel: OS badge ----
        summary = get_system_summary()
        self.host_label.setText(summary.get("user_host", "unknown"))
        for key, label in self.info_values.items():
            label.setText(str(summary.get(key, "—")))

        # ---- Right panel: Hardware cards ----
        # CPU
        cpu = data.get("cpu", {})
        cpu_text = (
            f"<b>{cpu.get('name', 'N/A')}</b><br>"
            f"Cores: {cpu.get('physical_cores', '?')} physical / {cpu.get('logical_cores', '?')} logical<br>"
            f"Frequency: {cpu.get('current_freq_mhz', 0)} MHz (max {cpu.get('max_freq_mhz', 0)} MHz)<br>"
            f"Usage: <span style='color:#00e5ff;'>{cpu.get('usage_percent', 0)}%</span>"
        )
        self._update_card_content(self.cpu_card, cpu_text)

        # GPU
        gpus = data.get("gpu", [])
        gpu_lines = []
        for i, gpu in enumerate(gpus):
            gpu_lines.append(
                f"<b>{gpu.get('name', 'N/A')}</b><br>"
                f"VRAM: {gpu.get('vram_total_mb', 'N/A')} MB "
                f"(Used: {gpu.get('vram_used_mb', 'N/A')} MB)<br>"
                f"Temp: {gpu.get('temp_c', 'N/A')}°C"
            )
        self._update_card_content(self.gpu_card, "<br><br>".join(gpu_lines) if gpu_lines else "No GPU detected")

        # RAM
        ram = data.get("ram", {})
        self.ram_value_label.setText(
            f"{ram.get('used_gb', 0)} GB / {ram.get('total_gb', 0)} GB  "
            f"({ram.get('percent', 0)}%)"
        )
        self.ram_bar.setValue(int(ram.get("percent", 0)))

        # Disk
        disks = data.get("disks", [])
        disk_lines = []
        for d in disks:
            disk_lines.append(
                f"<b>{d.get('device', 'N/A')}</b> → {d.get('mountpoint', '')}<br>"
                f"Type: {d.get('fstype', 'N/A')} | "
                f"Used: {d.get('used_gb', 0)}/{d.get('total_gb', 0)} GB "
                f"({d.get('percent', 0)}%)"
            )
        self._update_card_content(self.disk_card, "<br><br>".join(disk_lines) if disk_lines else "No disks found")

        # Network
        nets = data.get("network", [])
        net_lines = []
        for n in nets:
            status = "🟢 UP" if n.get("is_up") else "🔴 DOWN"
            ipv4 = n.get("ipv4", "—")
            if ipv4 and ipv4 != "—":
                net_lines.append(
                    f"<b>{n.get('name', 'N/A')}</b> {status}<br>"
                    f"IPv4: {ipv4} | MAC: {n.get('mac', 'N/A')} | Speed: {n.get('speed_mbps', 0)} Mbps"
                )
        self._update_card_content(self.network_card, "<br><br>".join(net_lines) if net_lines else "No active interfaces")

        # Motherboard / BIOS
        mobo = data.get("motherboard", {})
        mobo_text = (
            f"<b>{mobo.get('manufacturer', 'N/A')} — {mobo.get('product', 'N/A')}</b><br>"
            f"BIOS: {mobo.get('bios_vendor', 'N/A')} v{mobo.get('bios_version', 'N/A')}"
        )
        self._update_card_content(self.mobo_card, mobo_text)

    # -------------------------------------------------------------------------
    # UI Factory Helpers
    # -------------------------------------------------------------------------

    def _create_info_row(self, layout: QVBoxLayout, label_text: str, default: str) -> QLabel:
        """Create a key:value row in the left panel."""
        row = QHBoxLayout()
        row.setSpacing(8)

        key_label = QLabel(f"{label_text}:")
        key_label.setObjectName("InfoKey")
        key_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        key_label.setFixedWidth(70)
        row.addWidget(key_label)

        value_label = QLabel(default)
        value_label.setObjectName("InfoValue")
        value_label.setFont(QFont("Consolas", 10))
        value_label.setWordWrap(True)
        row.addWidget(value_label, stretch=1)

        layout.addLayout(row)
        return value_label

    def _create_spec_card(self, title: str, content: str) -> QFrame:
        """Create a hardware spec card with title and HTML content area."""
        card = QFrame()
        card.setObjectName("SpecCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("SpecCardTitle")
        title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        card_layout.addWidget(title_label)

        content_label = QLabel(content)
        content_label.setObjectName("SpecCardContent")
        content_label.setFont(QFont("Segoe UI", 10))
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.RichText)
        card_layout.addWidget(content_label)

        return card

    def _create_ram_card(self) -> QFrame:
        """Create the RAM card with a progress bar."""
        card = QFrame()
        card.setObjectName("SpecCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)

        title_label = QLabel("🧠  RAM")
        title_label.setObjectName("SpecCardTitle")
        title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        card_layout.addWidget(title_label)

        self.ram_value_label = QLabel("Scanning...")
        self.ram_value_label.setObjectName("SpecCardContent")
        self.ram_value_label.setFont(QFont("Segoe UI", 10))
        card_layout.addWidget(self.ram_value_label)

        self.ram_bar = QProgressBar()
        self.ram_bar.setObjectName("RamBar")
        self.ram_bar.setMinimum(0)
        self.ram_bar.setMaximum(100)
        self.ram_bar.setValue(0)
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setFixedHeight(12)
        card_layout.addWidget(self.ram_bar)

        return card

    @staticmethod
    def _update_card_content(card: QFrame, html_content: str):
        """Update the content label inside a spec card."""
        layout = card.layout()
        if layout and layout.count() >= 2:
            content_widget = layout.itemAt(1).widget()
            if isinstance(content_widget, QLabel):
                content_widget.setText(html_content)
