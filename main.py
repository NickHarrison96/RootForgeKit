# =============================================================================
# RootForgeKit — Main Application Entry Point
# Architecture:
#   QMainWindow
#     ├── QTabWidget (central widget)
#     │     └── Overview, Hardware Health, Tech, Gamer
#     └── PersistentStatusBar (always visible)
#
# HWID is queried in a background thread and pushed to the status bar.
# =============================================================================

import sys
import os
import threading

# =============================================================================
# Dependency preflight — MUST run before anything imports PySide6 or psutil.
#
# Without this, a machine that has never installed our dependencies dies with a
# bare "ModuleNotFoundError: No module named 'psutil'" pointing at an import
# line in utils/sys_info.py, which tells a first-time user nothing about what to
# do next. The testers receive this as a GitHub zip, so "just pip install it
# first" is exactly the step that gets skipped.
#
# Deliberately stdlib-only: find_spec() checks for a package without executing
# it, so this stays cheap and cannot itself fail on a missing dependency.
# =============================================================================

_REQUIRED_PACKAGES = (
    ("PySide6", "the GUI toolkit the whole app is built on"),
    ("psutil", "CPU, memory, disk and battery telemetry"),
)


def _preflight_dependencies() -> None:
    """Exit with an actionable message if a required package is absent."""
    from importlib.util import find_spec

    missing = []
    for module, why in _REQUIRED_PACKAGES:
        try:
            found = find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append((module, why))

    if not missing:
        return

    lines = [
        "",
        "=" * 68,
        "  RootForgeKit cannot start: dependencies are not installed.",
        "=" * 68,
        "",
    ]
    for module, why in missing:
        lines.append(f"  MISSING  {module}  ({why})")
    lines += [
        "",
        "  Run this from the folder containing main.py, then start the app again:",
        "",
        "      python -m pip install -r requirements.txt",
        "",
        "  On Windows, 'run.bat' does all of the above for you, including",
        "  creating an isolated virtual environment:",
        "",
        "      run.bat",
        "",
    ]
    if os.name == "nt":
        lines += [
            "  If pip is not recognised, Python was installed without pip being",
            "  on PATH. Re-run the Python installer, choose Modify, and tick",
            "  'pip' under Optional Features.",
            "",
        ]
    lines.append("=" * 68)
    lines.append("")

    # stderr, because stdout may be swallowed by a launcher that opens a
    # console for the process.
    sys.stderr.write("\n".join(lines))
    sys.stderr.flush()
    raise SystemExit(1)


_preflight_dependencies()

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
)
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont, QIcon

from components.status_bar import PersistentStatusBar
from tabs.overview import OverviewTab
from tabs.tech_tools import TechToolsTab
from tabs.gamer_tools import GamerToolsTab
from tabs.hardware.tab import HardwareHealthTab
from tabs.secret_sauce import SecretGatekeeper, SecretSauceTab
from utils.hwid import get_smbios_info, get_display_summary
from utils.paths import resource_path
from utils.resource_manager import configure_global_thread_pool, install_global_crash_handler

# How long a shutdown may take before the process is forced down. A clean exit
# takes a fraction of this; anything still running at the limit is wedged.
_EXIT_WATCHDOG_SECONDS = 3.0

APP_VERSION = "0.5"
APP_STAGE = "Pre-Alpha"
APP_AUTHOR = "KushNick420"

# Windows groups taskbar buttons by "Application User Model ID". A Python
# process inherits the interpreter's, so without setting this the taskbar shows
# the generic Python icon and groups RootForgeKit under Python -- even though
# the window icon itself is correct. Must be set BEFORE the first window is
# created. Harmless no-op off Windows.
APP_USER_MODEL_ID = "KushNick420.RootForgeKit"


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:
        # Cosmetic only -- a failure here must never stop the app starting.
        pass


def app_icon() -> QIcon:
    """
    The application icon, preferring the multi-resolution .ico.

    The .ico carries 16-256px variants so Windows picks a crisp one per
    context (taskbar, alt-tab, title bar) instead of downscaling a single
    large bitmap. Falls back to the PNG, then to an empty icon rather than
    raising -- a missing icon is a cosmetic problem, not a fatal one.
    """
    for name in ("app.ico", "app.png"):
        path = resource_path("resources", name)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


# =============================================================================
# Background HWID Worker — keeps UI responsive during SMBIOS queries
# =============================================================================

class HwidWorker(QThread):
    """Query SMBIOS data in background to avoid blocking the UI on startup."""
    hwid_ready = Signal(dict)

    def run(self):
        smbios = get_smbios_info()
        summary = get_display_summary(smbios)
        self.hwid_ready.emit(summary)


# =============================================================================
# Main Window
# =============================================================================

class RootForgeKitMainWindow(QMainWindow):
    """
    Main application window.

    Layout:
        - QTabWidget as central widget (all tool tabs, shown immediately)
        - PersistentStatusBar at bottom (always visible)
    """

    def __init__(self):
        super().__init__()

        # Configure worker thread pool limits based on host CPU topology
        self.allocated_cores = configure_global_thread_pool()

        self._setup_window()
        self._setup_status_bar()
        self._setup_tabs()
        self._start_hwid_query()

        # Intercept crashes globally and direct them to active tab console
        install_global_crash_handler(log_callback=self.route_crash_to_console)

    def closeEvent(self, event):
        """Shut background work down before the window goes away.

        Without this, closing the window left a process running with no window
        on it, and every relaunch added another one. The cause is worker threads
        that outlive the event loop: a QThread still blocked in a child process
        keeps the interpreter alive during teardown, so the process never exits.

        Each tab gets asked to stop and is given a moment to comply. That is
        best-effort by design — the watchdog in main() is what actually
        guarantees the process ends, because a thread wedged in a driver call
        cannot be asked politely.
        """
        hwid_worker = getattr(self, "_hwid_worker", None)
        if hwid_worker is not None and hwid_worker.isRunning():
            hwid_worker.wait(1000)

        tabs = self.centralWidget()
        if isinstance(tabs, QTabWidget):
            for index in range(tabs.count()):
                tab = tabs.widget(index)
                shutdown = getattr(tab, "shutdown", None)
                if callable(shutdown):
                    try:
                        shutdown()
                    except Exception:
                        # Never let a failing teardown keep the window open.
                        pass

        event.accept()

    def route_crash_to_console(self, crash_report: str):
        """Routes unhandled exceptions directly into the active tab console."""
        tabs = self.centralWidget()
        if isinstance(tabs, QTabWidget):
            active_tab = tabs.currentWidget()
            if hasattr(active_tab, "log_verbose"):
                active_tab.log_verbose(crash_report)
            elif hasattr(active_tab, "terminal"):
                active_tab.terminal.console.appendPlainText(crash_report)
            else:
                sys.stderr.write(crash_report)
        else:
            sys.stderr.write(crash_report)

    def _setup_window(self):
        """Configure main window properties."""
        self.setWindowTitle(
            f"RootForgeKit v{APP_VERSION} ({APP_STAGE}) — System Utility & Diagnostic Suite "
            f"(Workers: {self.allocated_cores} Cores)"
        )
        # Design base resolution is 1920x1080. Never open larger than the
        # screen actually is, and never set a minimum wider than the screen.
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        base_w = min(1920, geo.width()) if geo else 1920
        base_h = min(1080, geo.height()) if geo else 1080
        self.setMinimumSize(min(1440, base_w), min(810, base_h))
        self.resize(base_w, base_h)

        if geo:
            self.move(geo.x() + max(0, (geo.width() - base_w) // 2),
                      geo.y() + max(0, (geo.height() - base_h) // 2))

    def _setup_status_bar(self):
        """Attach the persistent status bar (visible on ALL pages)."""
        self.status_bar = PersistentStatusBar(self)
        self.setStatusBar(self.status_bar)

    def _setup_tabs(self):
        """Build the tab container and make it the central widget."""
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setObjectName("MainTabs")

        self.tabs.addTab(OverviewTab(),       "📊  Overview")
        self.tabs.addTab(HardwareHealthTab(), "🩺  Hardware Health")
        self.tabs.addTab(TechToolsTab(),      "🔧  Tech Tools")
        self.tabs.addTab(GamerToolsTab(),     "🎮  Gamer Tools")

        # Gated tab, added last so it sits at the far right of the tab bar —
        # the one nobody stumbles into by accident.
        secret_index = self.tabs.addTab(SecretSauceTab(), "🍔  SecretSauce")
        self.secret_gate = SecretGatekeeper(self.tabs, secret_index)

        self.setCentralWidget(self.tabs)

    def _start_hwid_query(self):
        """Launch SMBIOS query in background thread."""
        self._hwid_worker = HwidWorker()
        self._hwid_worker.hwid_ready.connect(self._on_hwid_ready)
        self._hwid_worker.start()

    # -------------------------------------------------------------------------
    # Signal Handlers
    # -------------------------------------------------------------------------

    def _on_hwid_ready(self, summary: dict):
        """Receive SMBIOS data and push to status bar."""
        self.status_bar.set_hwid_info(
            board_label=summary.get("board_label", "Unknown"),
            host_id_short=summary.get("host_id", "N/A"),
            host_id_full=summary.get("host_id_full", ""),
        )
        print(f"[HWID] Board: {summary.get('board_label')} | "
              f"Host ID: {summary.get('host_id')}")


# =============================================================================
# QSS Loader
# =============================================================================

def load_stylesheet(app: QApplication) -> None:
    """Load the QSS stylesheet from the shipped application files."""
    qss_path = resource_path("styles.qss")

    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
        print(f"[OK] Loaded stylesheet: {qss_path}")
    else:
        print(f"[WARNING] Stylesheet not found: {qss_path}")


# =============================================================================
# Entry Point
# =============================================================================

def main():
    # Before QApplication, so the taskbar button picks up our identity.
    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName("RootForgeKit")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_AUTHOR)
    app.setFont(QFont("Segoe UI", 10))

    # Set on the application so every window and dialog inherits it, rather
    # than having to icon each one individually.
    app.setWindowIcon(app_icon())

    load_stylesheet(app)

    window = RootForgeKitMainWindow()
    window.show()

    code = app.exec()

    # ---- Exit watchdog ----------------------------------------------------
    # By the time app.exec() returns the Qt event loop is already gone, so a
    # QTimer here would never fire. A plain daemon thread is the only thing
    # that still runs during interpreter teardown.
    #
    # It exists because a healthy teardown finishes in well under a second,
    # while a worker wedged in a child process or a driver call can block
    # teardown indefinitely. Rather than leave a windowless process behind --
    # which is what made the app "stay open" and stack up on every relaunch --
    # force the process down. os._exit() skips atexit hooks and buffered writes
    # on purpose: at this point the only thing left to lose is a teardown that
    # is not going to finish anyway.
    watchdog = threading.Timer(_EXIT_WATCHDOG_SECONDS, lambda: os._exit(code))
    watchdog.daemon = True
    watchdog.start()

    sys.exit(code)


if __name__ == "__main__":
    main()
