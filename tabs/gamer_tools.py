# =============================================================================
# RootForgeKit — Gamer Tools Tab
# Gaming-focused utilities. OS selector (Windows / macOS / Linux) reveals
# that platform's tool set.
# =============================================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QGridLayout, QScrollArea, QSplitter,
    QStackedWidget, QButtonGroup,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from components.terminal_widget import TerminalConsoleWidget
from utils.command_builder import CommandBuilder, ps_encoded_command, requires_admin
from utils.batch_installer import BatchInstallWorker
from utils.os_logo import get_host_profile


# ---- Gamer tool definitions: (command_key, icon, name, description) ----
GAMER_TOOLS = [
    ("gpu_info",     "🎮", "GPU Monitor",       "Check GPU adapter details, driver version, and VRAM status."),
    ("process_list", "⚡", "Process Priority",  "View CPU-heavy processes to identify performance bottlenecks."),
    ("temp_clean",   "🧹", "Temp File Cleaner", "Remove temporary files to free disk space and improve performance."),
    ("flush_dns",    "🌐", "DNS Reset",         "Flush DNS cache to resolve online gaming connectivity issues."),
    ("network_diag", "📶", "Network Check",     "Inspect network configuration and open connections for lag hunting."),
    ("disk_health",  "💽", "Drive Health",      "Check drive health — failing drives cause stutter and long load times."),
]

# Platform-specific bonus tools: (command, icon, name, description, risk)
# Darwin/Linux intentionally omitted — they previously held guessed commands
# that were never run or tested on either platform. PLATFORM_BONUS.get(os_key,
# []) already falls back to empty for any key not listed here, so leaving
# them out (rather than "Darwin": []) is the same effect with less noise.
# Build these out for real, one tool at a time, once there's a way to test
# them — Windows is the only verified baseline for now.
#
# All four Windows entries below were `powershell -Command "..."` originally,
# which silently didn't work: the whole command string gets wrapped again by
# cmd.exe /c "..." (see components/terminal_widget.py), and the nested double
# quotes around -Command's argument collided with cmd.exe's own quote
# handling for /c. Confirmed via a direct QProcess reproduction that every
# one of these returned exit code 0 while the "output" was just the literal
# command text echoed back — never actually executed. Rewrapped through
# ps_encoded_command() (base64 -EncodedCommand), which sidesteps the quoting
# collision entirely.
PLATFORM_BONUS = {
    "Windows": [
        (
            ps_encoded_command(
                "Get-Process | Sort-Object CPU -Descending | "
                "Select-Object -First 15 Name,CPU,WorkingSet"
            ),
            "🎯", "Top Processes (Detailed)",
            "Show top 15 CPU-consuming processes with memory usage.",
            "low",
        ),
        (
            ps_encoded_command("Get-NetAdapterAdvancedProperty | Format-Table -AutoSize"),
            "📡", "Network Adapter Tweaks",
            "View advanced network adapter properties for latency tuning.",
            "low",
        ),
        (
            ps_encoded_command(
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name,DriverVersion,DriverDate | Format-List"
            ),
            "🖥️", "GPU Driver Info",
            "Check GPU driver version and date — outdated drivers hurt game performance.",
            "low",
        ),
        (
            ps_encoded_command("powercfg /getactivescheme"),
            "🔋", "Active Power Plan",
            "Show the active power plan; High Performance is preferred for gaming.",
            "low",
        ),
    ],
}

# ---- OS selector: (platform_key, icon, label) ----
OS_TARGETS = [
    ("Windows", "🪟", "Windows"),
    ("Darwin",  "🍎", "macOS"),
    ("Linux",   "🐧", "Linux"),
]

TOOL_GRID_COLUMNS = 4
TOOL_BTN_W = 210
TOOL_BTN_H = 28


class GamerToolsTab(QWidget):
    """
    Gaming-focused utilities.
    Same architecture as TechToolsTab: OS selector drives a stacked tool area.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.host = get_host_profile()
        self.host_os = self.host.family
        self.cmd_builder = CommandBuilder()
        self._builders: dict[str, CommandBuilder] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Build the gamer tools layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(0)

        # Title
        title = QLabel("🎮  Gamer Utilities")
        title.setObjectName("TabSectionTitle")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        main_layout.addWidget(title)

        subtitle = QLabel("Performance tweaks, GPU monitoring, and gaming optimizations.")
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
        terminal_frame.setObjectName("GamerTerminalFrame")
        terminal_layout = QVBoxLayout(terminal_frame)
        terminal_layout.setContentsMargins(0, 6, 0, 0)
        terminal_layout.setSpacing(4)

        terminal_label = QLabel("📟  Gaming Console")
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
        if not builder.list_keys() and not PLATFORM_BONUS.get(os_key):
            notice = QLabel(
                f"🚧  {os_label} support isn't built yet — Windows is the only verified "
                f"baseline for now."
            )
            notice.setObjectName("OsMismatchNotice")
            notice.setWordWrap(True)
            page_layout.addWidget(notice)
        elif os_key != self.host_os:
            notice = QLabel(
                f"⚠️  Viewing {os_label} commands on a {self.host_os} host — "
                f"these will not run correctly here."
            )
            notice.setObjectName("OsMismatchNotice")
            notice.setWordWrap(True)
            page_layout.addWidget(notice)

        scroll = QScrollArea()
        scroll.setObjectName("GamerScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 6, 0)
        grid_layout.setSpacing(6)

        idx = 0
        # Standard tools from CommandBuilder
        for cmd_key, icon, name, desc in GAMER_TOOLS:
            if cmd_key not in builder.list_keys():
                continue
            _, builder_desc, risk = builder.get(cmd_key)
            btn = self._create_tool_button(os_key, cmd_key, icon, name, builder_desc or desc, risk)
            grid_layout.addWidget(btn, idx // TOOL_GRID_COLUMNS, idx % TOOL_GRID_COLUMNS,
                                  Qt.AlignmentFlag.AlignLeft)
            idx += 1

        # Platform-specific bonus tools (raw commands)
        for cmd, icon, name, desc, risk in PLATFORM_BONUS.get(os_key, []):
            btn = self._create_raw_tool_button(os_key, cmd, icon, name, desc, risk)
            grid_layout.addWidget(btn, idx // TOOL_GRID_COLUMNS, idx % TOOL_GRID_COLUMNS,
                                  Qt.AlignmentFlag.AlignLeft)
            idx += 1

        # Batch profile entry (host-only — installer targets the running machine)
        if os_key == self.host_os:
            self._gamer_batch_btn = self._create_action_button(
                "🚀", "Install Gamer Essentials Profile",
                "Batch silent install of Steam, Discord, DirectX, VC++ Runtimes, 7-Zip, MSI Afterburner.",
                self._run_gaming_batch_profile,
            )
            grid_layout.addWidget(self._gamer_batch_btn, idx // TOOL_GRID_COLUMNS, idx % TOOL_GRID_COLUMNS,
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

    # -------------------------------------------------------------------------
    # Button Factories
    # -------------------------------------------------------------------------

    def _style_tool_button(self, btn: QPushButton, tooltip: str, risk: str = "low"):
        """Apply the shared compact tool-button styling."""
        btn.setObjectName("ToolItemBtn")
        btn.setProperty("risk", risk)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(TOOL_BTN_W, TOOL_BTN_H)
        btn.setToolTip(tooltip)

    def _create_tool_button(self, os_key: str, cmd_key: str, icon: str,
                            name: str, desc: str, risk: str) -> QPushButton:
        """Create a compact tool button wired to the command registry."""
        risk_marks = {"low": "", "medium": " ·", "high": " !"}
        btn = QPushButton(f"{icon}  {name}{risk_marks.get(risk, '')}")
        self._style_tool_button(btn, f"{desc}\n\nRisk: {risk.upper()}", risk)
        btn.clicked.connect(lambda _checked, k=cmd_key, o=os_key: self._execute_from_builder(k, o))
        return btn

    def _create_raw_tool_button(self, os_key: str, command: str, icon: str,
                                name: str, desc: str, risk: str) -> QPushButton:
        """Create a compact tool button wired to a raw command string."""
        risk_marks = {"low": "", "medium": " ·", "high": " !"}
        btn = QPushButton(f"{icon}  {name}{risk_marks.get(risk, '')}")
        self._style_tool_button(btn, f"{desc}\n\nRisk: {risk.upper()}", risk)
        btn.clicked.connect(
            lambda _checked, c=command, d=desc, r=risk, o=os_key: self._execute_raw(c, d, r, o)
        )
        return btn

    def _create_action_button(self, icon: str, name: str, desc: str, slot) -> QPushButton:
        """Create a compact tool button wired to an arbitrary callable."""
        btn = QPushButton(f"{icon}  {name}")
        self._style_tool_button(btn, desc)
        btn.clicked.connect(slot)
        return btn

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------

    def _warn_wrong_host(self, description: str, command: str, os_key: str) -> bool:
        """Log a block message when a command targets a non-host OS. True if blocked."""
        if self.host.supports(os_key):
            return False
        self.terminal.console.appendPlainText(
            f"[BLOCKED] {self.host.block_reason(os_key)}\n"
            f"          Command shown for reference: {command}\n"
        )
        return True

    def _execute_from_builder(self, cmd_key: str, os_key: str):
        """Execute a command looked up from CommandBuilder."""
        builder = self._builders.get(os_key, self.cmd_builder)
        try:
            command, description, risk_level = builder.get(cmd_key)
        except KeyError:
            return
        if self._warn_wrong_host(description, command, os_key):
            return
        self.terminal.execute_command(
            command=command, description=description,
            risk_level=risk_level, command_key=cmd_key,
            requires_admin=requires_admin(cmd_key),
        )

    def _execute_raw(self, command: str, description: str, risk_level: str, os_key: str):
        """Execute a raw command string."""
        if self._warn_wrong_host(description, command, os_key):
            return
        self.terminal.execute_command(
            command=command, description=description,
            risk_level=risk_level, command_key="",
        )

    def _run_gaming_batch_profile(self):
        """
        Run batch installation of the gaming_essentials profile in the
        background — this used to call install_profile() directly on the UI
        thread, which froze the whole app for the entire multi-package run.
        """
        if getattr(self, "_batch_worker", None) is not None and self._batch_worker.isRunning():
            return
        self._gamer_batch_btn.setEnabled(False)
        self._gamer_batch_btn.setText("🚀  Installing…")
        self._batch_worker = BatchInstallWorker("gaming_essentials")
        self._batch_worker.log_line.connect(self.terminal.console.appendPlainText)
        self._batch_worker.finished_profile.connect(self._on_gaming_batch_finished)
        self._batch_worker.start()

    def _on_gaming_batch_finished(self, success: bool):
        self._gamer_batch_btn.setEnabled(True)
        self._gamer_batch_btn.setText("🚀  Install Gamer Essentials Profile")
