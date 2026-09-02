# =============================================================================
# RootForgeKit — Technician Tools Tab
# Advanced system utilities. OS selector (Windows / macOS / Linux) reveals
# that platform's tool set.
# =============================================================================

import webbrowser

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QGridLayout, QScrollArea, QSplitter,
    QStackedWidget, QButtonGroup,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from components.terminal_widget import TerminalConsoleWidget
from utils.command_builder import CommandBuilder, requires_admin
from utils.batch_installer import BatchInstallWorker
from utils.os_logo import get_host_profile
from utils.hardware_vendor import detect_cpu_vendor, detect_gpu_vendor

# No winget package exists for the actual AMD/NVIDIA driver (verified via
# `winget search` — only third-party utilities like TinyNvidiaUpdateChecker
# turn up, not the OEM installer). Intel does publish a real one-click
# auto-detect tool, so only that path installs directly; AMD/NVIDIA route to
# the vendor's own official driver page instead of faking an install.
INTEL_DRIVER_ASSISTANT_CMD = (
    "winget install --id Intel.IntelDriverAndSupportAssistant -e "
    "--accept-package-agreements --accept-source-agreements"
)
AMD_DRIVER_URL = "https://www.amd.com/en/support"
NVIDIA_DRIVER_URL = "https://www.nvidia.com/Download/index.aspx"


# ---- Tool definitions: (command_key, icon, name, description) ----
TECH_TOOLS = [
    ("disk_health",          "💽", "Disk Health Check",     "Query SMART status and health of all connected drives."),
    ("network_diag",         "🌐", "Network Diagnostics",   "Display full network configuration and listening ports."),
    ("flush_dns",            "🔄", "Flush DNS Cache",       "Clear the DNS resolver cache to fix name resolution issues."),
    ("sfc_scan",             "🛡️", "System File Checker",   "Scan and repair protected system files (elevated)."),
    ("process_list",         "📊", "Process Monitor",       "List running processes sorted by CPU usage."),
    ("gpu_info",             "🎮", "GPU Details",           "Query detailed GPU adapter information."),
    ("temp_clean",           "🧹", "Temp File Cleaner",     "Remove temporary files to reclaim disk space."),
    ("system_update",        "⬆️", "System Update",         "Upgrade all installed packages."),
    ("dotnet",               "🧩", ".NET Runtime",          "Install the .NET 8 runtime."),
    ("activate_enterprise",  "🔑", "Activate Enterprise",   "Uninstall key, install Enterprise GVLK, set KMS server (kms8.msguides.com), and activate."),
    ("activate_pro",         "🔑", "Activate Windows Pro",  "Uninstall key, install Pro GVLK, set KMS server (kms8.msguides.com), and activate."),
    ("dism_server_standard", "💻", "DISM Server Standard",  "Set Windows Edition to ServerStandard via DISM with specified product key."),
]

# ---- OS selector: (platform_key, icon, label) ----
OS_TARGETS = [
    ("Windows", "🪟", "Windows"),
    ("Darwin",  "🍎", "macOS"),
    ("Linux",   "🐧", "Linux"),
]

TOOL_GRID_COLUMNS = 4
TOOL_BTN_W = 210
TOOL_BTN_H = 28


class TechToolsTab(QWidget):
    """Technician-level system utilities: OS selector drives a stacked tool area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.host = get_host_profile()
        self.host_os = self.host.family
        self.cmd_builder = CommandBuilder()
        self._builders: dict[str, CommandBuilder] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Build the technician tools layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(0)

        # Title
        title = QLabel("🔧  Technician Tools")
        title.setObjectName("TabSectionTitle")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        main_layout.addWidget(title)

        subtitle = QLabel("Advanced system diagnostics and repair utilities.")
        subtitle.setObjectName("TabSubtitle")
        subtitle.setFont(QFont("Segoe UI", 9))
        main_layout.addWidget(subtitle)
        main_layout.addSpacing(10)

        # ---- OS selector + Tool Grid + Terminal ----
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)

        top_pane = QWidget()
        top_layout = QVBoxLayout(top_pane)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)
        top_layout.addLayout(self._build_os_selector())

        # Secondary area — one page of tools per OS
        self.os_pages = QStackedWidget()
        for os_key, _, _ in OS_TARGETS:
            self.os_pages.addWidget(self._build_os_page(os_key))
        top_layout.addWidget(self.os_pages, stretch=1)
        splitter.addWidget(top_pane)

        # Terminal console
        terminal_frame = QFrame()
        terminal_frame.setObjectName("TechTerminalFrame")
        terminal_layout = QVBoxLayout(terminal_frame)
        terminal_layout.setContentsMargins(0, 6, 0, 0)
        terminal_layout.setSpacing(4)

        terminal_label = QLabel("📟  Diagnostic Console")
        terminal_label.setObjectName("TerminalSectionLabel")
        terminal_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        terminal_layout.addWidget(terminal_label)

        self.terminal = TerminalConsoleWidget()
        terminal_layout.addWidget(self.terminal)

        splitter.addWidget(terminal_frame)
        splitter.setSizes([340, 280])
        main_layout.addWidget(splitter, stretch=1)

        # Default to the host platform
        self._select_os(self.host_os if any(k == self.host_os for k, _, _ in OS_TARGETS) else "Windows")

    def _build_os_selector(self) -> QHBoxLayout:
        """Build the Windows / macOS / Linux selector row."""
        row = QHBoxLayout()
        row.setSpacing(6)

        self.os_group = QButtonGroup(self)
        self.os_group.setExclusive(True)
        self.os_buttons: dict[str, QPushButton] = {}

        for os_key, icon, label in OS_TARGETS:
            btn = QPushButton(f"{icon}  {label}")
            btn.setObjectName("OsSelectBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if os_key == self.host_os:
                btn.setToolTip(f"{label} — this machine")
            else:
                btn.setToolTip(f"{label} — commands shown for reference; run on a {label} host")
            btn.clicked.connect(lambda _checked, k=os_key: self._select_os(k))
            self.os_group.addButton(btn)
            self.os_buttons[os_key] = btn
            row.addWidget(btn)

        row.addStretch()
        return row

    def _build_os_page(self, os_key: str) -> QWidget:
        """Build the secondary tool area for one platform."""
        builder = CommandBuilder(os_type=os_key)
        self._builders[os_key] = builder

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(6)

        os_label = dict((k, l) for k, _, l in OS_TARGETS)[os_key]
        if not builder.list_keys():
            notice = QLabel(
                f"🚧  {os_label} support isn't built yet — Windows is the only verified "
                f"baseline for now."
            )
            notice.setObjectName("OsMismatchNotice")
            notice.setWordWrap(True)
            page_layout.addWidget(notice)
        elif os_key != self.host_os:
            notice = QLabel(
                f"⚠️  Viewing {os_label} commands on a {self.host_os} host — these will "
                f"not run correctly here."
            )
            notice.setObjectName("OsMismatchNotice")
            notice.setWordWrap(True)
            page_layout.addWidget(notice)

        scroll = QScrollArea()
        scroll.setObjectName("TechScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 6, 0)
        grid_layout.setSpacing(6)

        idx = 0
        for cmd_key, icon, name, desc in TECH_TOOLS:
            if cmd_key not in builder.list_keys():
                continue
            _, builder_desc, risk = builder.get(cmd_key)
            btn = self._create_tool_button(os_key, cmd_key, icon, name, builder_desc or desc, risk)
            grid_layout.addWidget(btn, idx // TOOL_GRID_COLUMNS, idx % TOOL_GRID_COLUMNS,
                                  Qt.AlignmentFlag.AlignLeft)
            idx += 1

        # Batch profile entry (host-only — installer targets the running machine)
        if os_key == self.host_os:
            self._tech_batch_btn = self._create_raw_tool_button(
                "🛠️", "Install Tech Utilities Profile",
                "Batch silent install of 7-Zip, Notepad++, Wireshark, VS Code, Git, Python 3.12.",
                self._run_tech_batch_profile,
            )
            grid_layout.addWidget(self._tech_batch_btn, idx // TOOL_GRID_COLUMNS, idx % TOOL_GRID_COLUMNS,
                                  Qt.AlignmentFlag.AlignLeft)
            idx += 1

        # CPU chipset / GPU driver buttons (Windows-only, host-only — vendor
        # detection reads this machine's actual hardware)
        if os_key == self.host_os and os_key == "Windows":
            cpu_vendor = detect_cpu_vendor()
            cpu_btn = self._create_raw_tool_button(
                "🧠", f"Install Chipset Drivers ({cpu_vendor})",
                self._driver_button_tooltip("CPU", cpu_vendor),
                self._run_cpu_driver_install,
            )
            grid_layout.addWidget(cpu_btn, idx // TOOL_GRID_COLUMNS, idx % TOOL_GRID_COLUMNS,
                                  Qt.AlignmentFlag.AlignLeft)
            idx += 1

            gpu_vendor = detect_gpu_vendor()
            gpu_btn = self._create_raw_tool_button(
                "🖥️", f"Install GPU Drivers ({gpu_vendor})",
                self._driver_button_tooltip("GPU", gpu_vendor),
                self._run_gpu_driver_install,
            )
            grid_layout.addWidget(gpu_btn, idx // TOOL_GRID_COLUMNS, idx % TOOL_GRID_COLUMNS,
                                  Qt.AlignmentFlag.AlignLeft)
            idx += 1

        # Trailing spacer column absorbs the slack so buttons stay left-packed
        grid_layout.setColumnStretch(TOOL_GRID_COLUMNS, 1)
        grid_layout.setRowStretch(grid_layout.rowCount(), 1)

        scroll.setWidget(grid_container)
        page_layout.addWidget(scroll, stretch=1)
        return page

    def _select_os(self, os_key: str):
        """Switch the secondary area to the chosen platform."""
        index = next((i for i, (k, _, _) in enumerate(OS_TARGETS) if k == os_key), 0)
        self.os_pages.setCurrentIndex(index)
        btn = self.os_buttons.get(os_key)
        if btn:
            btn.setChecked(True)

    def _create_tool_button(self, os_key: str, cmd_key: str, icon: str,
                            name: str, desc: str, risk: str) -> QPushButton:
        """Create a compact tool button wired to the command registry."""
        risk_marks = {"low": "", "medium": " ·", "high": " !"}
        btn = QPushButton(f"{icon}  {name}{risk_marks.get(risk, '')}")
        btn.setObjectName("ToolItemBtn")
        btn.setProperty("risk", risk)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(TOOL_BTN_W, TOOL_BTN_H)
        btn.setToolTip(f"{desc}\n\nRisk: {risk.upper()}")
        btn.clicked.connect(lambda _checked, k=cmd_key, o=os_key: self._execute_tool(k, o))
        return btn

    def _create_raw_tool_button(self, icon: str, name: str, desc: str, slot) -> QPushButton:
        """Create a compact tool button wired to an arbitrary callable."""
        btn = QPushButton(f"{icon}  {name}")
        btn.setObjectName("ToolItemBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(TOOL_BTN_W, TOOL_BTN_H)
        btn.setToolTip(desc)
        btn.clicked.connect(slot)
        return btn

    def _execute_tool(self, cmd_key: str, os_key: str):
        """Look up and execute a tool command via the terminal."""
        builder = self._builders.get(os_key, self.cmd_builder)
        try:
            command, description, risk_level = builder.get(cmd_key)
        except KeyError:
            return

        if not self.host.supports(os_key):
            self.terminal.console.appendPlainText(
                f"[BLOCKED] {self.host.block_reason(os_key)}\n"
                f"          Command shown for reference: {command}\n"
            )
            return

        self.terminal.execute_command(
            command=command,
            description=description,
            risk_level=risk_level,
            command_key=cmd_key,
            requires_admin=requires_admin(cmd_key),
        )

    def _run_tech_batch_profile(self):
        """
        Run batch installation of the tech_utilities profile in the
        background — this used to call install_profile() directly on the UI
        thread, which froze the whole app for the entire multi-package run.
        """
        if getattr(self, "_batch_worker", None) is not None and self._batch_worker.isRunning():
            return
        self._tech_batch_btn.setEnabled(False)
        self._tech_batch_btn.setText("🛠️  Installing…")
        self._batch_worker = BatchInstallWorker("tech_utilities")
        self._batch_worker.log_line.connect(self.terminal.console.appendPlainText)
        self._batch_worker.finished_profile.connect(self._on_tech_batch_finished)
        self._batch_worker.start()

    def _on_tech_batch_finished(self, success: bool):
        self._tech_batch_btn.setEnabled(True)
        self._tech_batch_btn.setText("🛠️  Install Tech Utilities Profile")

    # -------------------------------------------------------------------------
    # CPU / GPU driver buttons
    # -------------------------------------------------------------------------

    @staticmethod
    def _driver_button_tooltip(kind: str, vendor: str) -> str:
        if vendor == "Intel":
            return f"Detected Intel {kind} — installs Intel's official Driver & Support Assistant (auto-detects and updates all Intel drivers)."
        if vendor in ("AMD", "NVIDIA"):
            return f"Detected {vendor} {kind} — opens {vendor}'s official driver page. No winget package exists for the real {vendor} driver, so this isn't a one-click install."
        return f"Could not detect {kind} vendor — opens Intel's driver assistant as a fallback; check manually if this isn't an Intel system."

    def _run_cpu_driver_install(self):
        vendor = detect_cpu_vendor()
        if vendor == "AMD":
            self.terminal.console.appendPlainText(
                f"[*] AMD chipset drivers have no winget package — opening {AMD_DRIVER_URL}"
            )
            webbrowser.open(AMD_DRIVER_URL)
        else:
            # Intel, or unknown (Intel's assistant is a safe default — it
            # simply won't find anything to do on non-Intel hardware).
            self.terminal.execute_command(
                command=INTEL_DRIVER_ASSISTANT_CMD,
                description="Install Intel Driver & Support Assistant (auto-detects chipset/GPU/WiFi drivers)",
                risk_level="medium",
                command_key="",
            )

    def _run_gpu_driver_install(self):
        vendor = detect_gpu_vendor()
        if vendor == "NVIDIA":
            self.terminal.console.appendPlainText(
                f"[*] No winget package for the real NVIDIA driver — opening {NVIDIA_DRIVER_URL}"
            )
            webbrowser.open(NVIDIA_DRIVER_URL)
        elif vendor == "AMD":
            self.terminal.console.appendPlainText(
                f"[*] AMD GPU drivers have no winget package — opening {AMD_DRIVER_URL}"
            )
            webbrowser.open(AMD_DRIVER_URL)
        else:
            # Intel integrated graphics, or unknown — Intel's assistant
            # covers Intel GPUs too.
            self.terminal.execute_command(
                command=INTEL_DRIVER_ASSISTANT_CMD,
                description="Install Intel Driver & Support Assistant (auto-detects chipset/GPU/WiFi drivers)",
                risk_level="medium",
                command_key="",
            )
