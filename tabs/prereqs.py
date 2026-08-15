# =============================================================================
# NicksFix — Unified Prerequisites & Driver Setup Tab
#
# Layout:
#   Scrollable page of CollapsibleSection accordions:
#     ▶ Windows 10/11 System Components
#     ▶ iOS Drivers & Tools
#     ▶ Android Drivers & Tools
#     ▶ [Future sections...]
#
# Each section auto-checks on first expand and shows install actions.
# =============================================================================

import os
import sys
import platform
import shutil
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal, pyqtSlot as Slot
from PyQt6.QtGui import QFont

from components.terminal_widget import TerminalConsoleWidget
from utils.command_builder import CommandBuilder, requires_admin
from tabs.base_driver_tab import CollapsibleSection
from components.requirement_item import RequirementItemWidget
from utils.resource_manager import safe_run_command


# =============================================================================
# Prerequisite definitions
# =============================================================================

SYSTEM_PREREQS = {
    "Windows": [
        ("wsl2",          "WSL2",                 "Windows Subsystem for Linux 2 — run Linux environments natively."),
        ("vcredist",      "VC++ Redistributable",  "Visual C++ 2015-2022 runtime — required by many applications."),
        ("dotnet",        ".NET Runtime",           ".NET 8 Desktop Runtime — needed for modern .NET applications."),
        ("directx",       "DirectX",               "DirectX End-User Runtime — required for gaming and multimedia."),
        ("msys2",         "MSYS2",                 "Unix-like shell, GCC toolchain, and pacman package manager for Windows."),
        ("zadig",         "Zadig",                 "Binds WinUSB, libusb-win32, or libusbK to a USB device — WinUSB ships "
                                                     "built into Windows; Zadig is how you attach it to a specific device "
                                                     "(e.g. DFU/bootloader-mode flashing)."),
        ("libusbk",       "libusbK",               "USB driver framework used by libusb-based flashing/diagnostic tools — "
                                                     "the driver package Zadig can bind to a device."),
        ("system_update", "System Updates",         "Update all installed packages via winget."),
    ],
    "Darwin": [
        ("dotnet",        ".NET SDK",              ".NET SDK via Homebrew — for .NET development and apps."),
        ("system_update", "Brew Updates",           "Update and upgrade all Homebrew packages."),
    ],
    "Linux": [
        ("dotnet",        ".NET Runtime",           ".NET 8 Runtime via apt — for .NET applications."),
        ("system_update", "System Updates",         "Update and upgrade all system packages."),
    ],
}

# iOS requirement definitions (platform → {key: (label, checker)})
IOS_REQUIREMENTS = {
    "windows": {
        "apple_service":  ("Apple Mobile Device Service", None),
        "pymobiledevice3": ("pymobiledevice3 Library",    None),
    },
    "darwin": {
        "usbmuxd":        ("usbmuxd Daemon (Native)",     None),
        "pymobiledevice3": ("pymobiledevice3 Library",    None),
    },
    "linux": {
        "usbmuxd":        ("usbmuxd Service",             None),
        "pymobiledevice3": ("pymobiledevice3 Library",    None),
    },
}

# Android requirement definitions
ANDROID_REQUIREMENTS = {
    "windows": {
        "adb":      ("Android Debug Bridge (adb.exe)",    None),
        "fastboot": ("Fastboot Tool (fastboot.exe)",      None),
    },
    "darwin": {
        "adb":      ("Android Debug Bridge (adb)",        None),
        "fastboot": ("Fastboot Tool",                     None),
    },
    "linux": {
        "adb":      ("Android Debug Bridge (adb)",        None),
        "fastboot": ("Fastboot Tool",                     None),
    },
}


# =============================================================================
# Requirement checker workers (inline, lightweight)
# =============================================================================

class ReqCheckWorker(QThread):
    item_result = Signal(str, bool, str)   # key, ok, message
    finished    = Signal(dict)             # key → bool

    def __init__(self, checks: dict):
        super().__init__()
        self.checks = checks  # {key: (label, callable)}

    def run(self):
        results = {}
        for key, (label, fn) in self.checks.items():
            try:
                ok, msg = fn() if fn else (False, "No checker")
                results[key] = ok
                self.item_result.emit(key, ok, msg)
            except Exception as e:
                results[key] = False
                self.item_result.emit(key, False, str(e))
        self.finished.emit(results)


# =============================================================================
# Driver Section Widget (iOS / Android accordion body)
# =============================================================================

class DriverSection(QWidget):
    """
    Embeds RequirementItemWidgets for iOS or Android inside a CollapsibleSection.
    Includes auto-check and install prompt logic.
    """
    def __init__(self, label: str, req_map: dict, installer_fn, log_fn, parent=None):
        super().__init__(parent)
        self._label      = label
        self._req_map    = req_map      # {key: (display_name, check_fn)}
        self._installer  = installer_fn
        self._log        = log_fn
        self._req_widgets = {}
        self._checked    = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # Requirement items
        for key, (name, _) in req_map.items():
            item = RequirementItemWidget(key, name)
            item.verify_requested.connect(self._single_check)
            self._req_widgets[key] = item
            outer.addWidget(item)

        # Install prompt (hidden until needed)
        self._prompt = QFrame()
        self._prompt.setFrameShape(QFrame.Shape.StyledPanel)
        pl = QHBoxLayout(self._prompt)
        pl.addWidget(QLabel("⚠️  Missing dependencies detected. Attempt auto-install?"), stretch=1)
        btn_yes = QPushButton("Yes (Y)")
        btn_no  = QPushButton("No (N)")
        btn_yes.clicked.connect(self._do_install)
        btn_no.clicked.connect(self._prompt.hide)
        pl.addWidget(btn_yes)
        pl.addWidget(btn_no)
        self._prompt.hide()
        outer.addWidget(self._prompt)

    def auto_check(self):
        if self._checked:
            return
        self._checked = True
        self._run_checks()

    def _run_checks(self):
        checks = {k: (name, fn) for k, (name, fn) in self._req_map.items()}
        self._worker = ReqCheckWorker(checks)
        self._worker.item_result.connect(self._on_item_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    @Slot(str, bool, str)
    def _on_item_result(self, key, ok, msg):
        if key in self._req_widgets:
            self._req_widgets[key].set_status(ok)

    @Slot(dict)
    def _on_finished(self, results):
        missing = sum(1 for ok in results.values() if not ok)
        if missing:
            self._prompt.show()
        else:
            self._prompt.hide()

    def _single_check(self, key: str):
        if key not in self._req_map:
            return
        checks = {key: self._req_map[key]}
        self._worker = ReqCheckWorker(checks)
        self._worker.item_result.connect(self._on_item_result)
        self._worker.finished.connect(lambda _: None)
        self._worker.start()

    def _do_install(self):
        self._prompt.hide()
        if self._installer:
            self._installer(self._log)


# =============================================================================
# Unified Prerequisites Tab
# =============================================================================

class PrereqsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cmd_builder  = CommandBuilder()
        self._card_widgets = {}
        self._driver_sections = {}
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        # ── Title ───────────────────────────────────────────────────────────
        title = QLabel("⚙️  Prerequisites & Driver Setup")
        title.setObjectName("TabSectionTitle")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        root.addWidget(title)
        root.addSpacing(4)

        subtitle = QLabel(
            "Manage system components, mobile drivers, and tool dependencies. "
            "Sections auto-check when opened."
        )
        subtitle.setObjectName("TabSubtitle")
        subtitle.setWordWrap(True)
        root.addSpacing(4)
        root.addWidget(subtitle)
        root.addSpacing(12)

        # ── Splitter: top = scrollable accordions, bottom = terminal ────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self._accordion_layout = QVBoxLayout(container)
        self._accordion_layout.setContentsMargins(0, 0, 8, 0)
        self._accordion_layout.setSpacing(8)

        # ── Section 1: Windows / macOS / Linux System Components ────────────
        os_name = platform.system()
        os_label_map = {"Windows": "Windows 10/11", "Darwin": "macOS", "Linux": "Linux"}
        os_display = os_label_map.get(os_name, os_name)

        self._win_section = CollapsibleSection(
            f"🪟  {os_display} System Components", expanded=False
        )
        self._win_section._header.clicked.connect(
            lambda: self._on_system_section_opened()
        )
        self._build_system_cards(self._win_section.content_layout(), os_name)
        self._accordion_layout.addWidget(self._win_section)

        # ── Section 2: iOS Drivers ───────────────────────────────────────────
        ios_sec = CollapsibleSection("📱  iOS Drivers & Tools", expanded=False)
        ios_req = self._build_ios_reqs()
        ios_body = DriverSection(
            "iOS", ios_req,
            installer_fn=self._ios_installer,
            log_fn=self._log
        )
        ios_sec.content_layout().addWidget(ios_body)
        # Auto-check when expanded
        ios_sec._header.clicked.connect(
            lambda: ios_body.auto_check() if ios_sec._expanded else None
        )
        self._driver_sections["ios"] = ios_body
        self._accordion_layout.addWidget(ios_sec)

        # ── Section 3: Android Drivers ───────────────────────────────────────
        and_sec = CollapsibleSection("🤖  Android Drivers & Tools", expanded=False)
        and_req = self._build_android_reqs()
        and_body = DriverSection(
            "Android", and_req,
            installer_fn=self._android_installer,
            log_fn=self._log
        )
        and_sec.content_layout().addWidget(and_body)
        and_sec._header.clicked.connect(
            lambda: and_body.auto_check() if and_sec._expanded else None
        )
        self._driver_sections["android"] = and_body
        self._accordion_layout.addWidget(and_sec)

        # ── Future sections placeholder ──────────────────────────────────────
        future_sec = CollapsibleSection("🔮  More Tools (Coming Soon)", expanded=False)
        future_body = QLabel("  Additional driver categories will appear here in future updates.")
        future_body.setObjectName("TabSubtitle")
        future_body.setContentsMargins(8, 8, 8, 8)
        future_sec.content_layout().addWidget(future_body)
        self._accordion_layout.addWidget(future_sec)

        self._accordion_layout.addStretch()
        scroll.setWidget(container)
        splitter.addWidget(scroll)

        # ── Terminal console ─────────────────────────────────────────────────
        term_frame = QFrame()
        tl = QVBoxLayout(term_frame)
        tl.setContentsMargins(0, 8, 0, 0)
        lbl = QLabel("📟  Installation Console")
        lbl.setObjectName("TerminalSectionLabel")
        lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        tl.addWidget(lbl)
        self.terminal = TerminalConsoleWidget()
        self.terminal.command_finished.connect(self._on_command_finished)
        tl.addWidget(self.terminal)
        splitter.addWidget(term_frame)

        splitter.setSizes([420, 260])
        root.addWidget(splitter, stretch=1)

    # ── System cards (Windows/macOS/Linux) ──────────────────────────────────

    def _build_system_cards(self, layout: QVBoxLayout, os_name: str):
        prereqs = SYSTEM_PREREQS.get(os_name, SYSTEM_PREREQS["Linux"])
        for cmd_key, name, description in prereqs:
            card = self._create_prereq_card(cmd_key, name, description)
            layout.addWidget(card)

    def _on_system_section_opened(self):
        pass  # Could add auto-check logic here in future

    def _create_prereq_card(self, cmd_key: str, name: str, description: str) -> QFrame:
        card = QFrame()
        card.setObjectName("PrereqCard")
        cl = QHBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(16)

        status = QLabel("⏳")
        status.setObjectName("PrereqStatus")
        status.setFont(QFont("Segoe UI Emoji", 18))
        status.setFixedWidth(36)
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(status)

        info = QVBoxLayout()
        info.setSpacing(4)
        n = QLabel(name)
        n.setObjectName("PrereqName")
        n.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        d = QLabel(description)
        d.setObjectName("PrereqDesc")
        d.setWordWrap(True)
        info.addWidget(n)
        info.addWidget(d)
        cl.addLayout(info, stretch=1)

        btn = QPushButton("▶  Install")
        btn.setObjectName("PrereqInstallBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumWidth(110)
        btn.setMinimumHeight(28)
        btn.clicked.connect(lambda checked, k=cmd_key: self._run_install(k))
        cl.addWidget(btn)

        self._card_widgets[cmd_key] = (status, btn)
        return card

    def _run_install(self, cmd_key: str):
        try:
            command, description, risk_level = self.cmd_builder.get(cmd_key)
        except KeyError:
            return
        if cmd_key in self._card_widgets:
            s, b = self._card_widgets[cmd_key]
            s.setText("🔄")
            b.setEnabled(False)
            b.setText("Installing...")
        started = self.terminal.execute_command(
            command=command, description=description,
            risk_level=risk_level, command_key=cmd_key,
            requires_admin=requires_admin(cmd_key),
        )
        # If the command never started (declined, needs elevation, or the
        # terminal was busy) the finished-signal will never fire, so undo the
        # "Installing..." state here or the card spins forever.
        if not started and cmd_key in self._card_widgets:
            s, b = self._card_widgets[cmd_key]
            s.setText("⏳")
            b.setEnabled(True)
            b.setText("▶  Install")

    def _on_command_finished(self, exit_code: int, command_key: str):
        if command_key in self._card_widgets:
            s, b = self._card_widgets[command_key]
            if exit_code == 0:
                s.setText("✅"); b.setText("✓ Done"); b.setEnabled(False)
            else:
                s.setText("❌"); b.setText("▶  Retry"); b.setEnabled(True)

    # ── iOS requirement builders ─────────────────────────────────────────────

    def _build_ios_reqs(self) -> dict:
        host = platform.system().lower()
        reqs = {}

        def check_apple_svc():
            ok, out = safe_run_command(["sc", "query", "Apple Mobile Device Service"], timeout=5)
            running = ok and "RUNNING" in out
            return running, "Service running" if running else "Service missing or stopped"

        def check_pymobile():
            try:
                import pymobiledevice3
                return True, "Module available"
            except ImportError:
                return False, "Not installed"

        def check_usbmuxd():
            found = shutil.which("usbmuxd") is not None
            return found, "Found in PATH" if found else "Not found"

        if host == "windows":
            reqs["apple_service"]  = ("Apple Mobile Device Service", check_apple_svc)
            reqs["pymobiledevice3"] = ("pymobiledevice3 Library",    check_pymobile)
        elif host == "darwin":
            reqs["usbmuxd"]        = ("usbmuxd Daemon (Native)",     check_usbmuxd)
            reqs["pymobiledevice3"] = ("pymobiledevice3 Library",    check_pymobile)
        else:
            reqs["usbmuxd"]        = ("usbmuxd Service",             check_usbmuxd)
            reqs["pymobiledevice3"] = ("pymobiledevice3 Library",    check_pymobile)
        return reqs

    def _ios_installer(self, log):
        log("[*] Installing pymobiledevice3 via pip...")
        ok, out = safe_run_command([sys.executable, "-m", "pip", "install", "pymobiledevice3"], timeout=60)
        log("[+] Done!" if ok else f"[-] Failed: {out}")

    # ── Android requirement builders ─────────────────────────────────────────

    def _build_android_reqs(self) -> dict:
        host = platform.system().lower()
        local_pt = os.path.abspath(os.path.join("bin", "platform-tools"))

        def check_adb():
            p = shutil.which("adb")
            if not p:
                c = os.path.join(local_pt, "adb.exe" if os.name == "nt" else "adb")
                if os.path.isfile(c):
                    p = c
            return (bool(p), f"Found at {p}" if p else "Not found in PATH or local bin/")

        def check_fastboot():
            p = shutil.which("fastboot")
            if not p:
                c = os.path.join(local_pt, "fastboot.exe" if os.name == "nt" else "fastboot")
                if os.path.isfile(c):
                    p = c
            return (bool(p), f"Found at {p}" if p else "Not found")

        adb_label = "Android Debug Bridge (adb.exe)" if host == "windows" else "Android Debug Bridge (adb)"
        fb_label  = "Fastboot Tool (fastboot.exe)"   if host == "windows" else "Fastboot Tool"
        return {
            "adb":      (adb_label, check_adb),
            "fastboot": (fb_label,  check_fastboot),
        }

    def _android_installer(self, log):
        import urllib.request, zipfile
        host = platform.system().lower()
        urls = {
            "darwin":  "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
            "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
            "linux":   "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
        }
        url = urls.get(host)
        if not url:
            log("[-] Unsupported OS for automated SDK download.")
            return
        bin_dir  = os.path.abspath("bin")
        os.makedirs(bin_dir, exist_ok=True)
        zip_path = os.path.join(bin_dir, "platform-tools.zip")
        try:
            log("[*] Downloading SDK Platform Tools from Google...")
            urllib.request.urlretrieve(url, zip_path)
            log("[*] Killing adb to release locks...")
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], capture_output=True)
            else:
                subprocess.run(["killall", "adb"], capture_output=True)
            log("[*] Extracting...")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(bin_dir)
            os.remove(zip_path)
            pt = os.path.join(bin_dir, "platform-tools")
            os.environ["PATH"] = pt + os.pathsep + os.environ["PATH"]
            log(f"[+] ADB/Fastboot ready at {pt}")
        except Exception as e:
            log(f"[!] Android setup failed: {e}")

    # ── Shared log helper ────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.terminal.console.appendPlainText(msg)
