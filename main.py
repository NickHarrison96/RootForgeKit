# =============================================================================
# RootForgeKit — Main Application Entry Point
# Architecture:
#   QMainWindow
#     ├── QTabWidget (central widget)
#     │     └── Overview, Hardware Health, Prerequisites, Tech, Gamer,
#     │         iOS, Android
#     └── PersistentStatusBar (always visible)
#
# HWID is queried in a background thread and pushed to the status bar.
# =============================================================================

import sys
import os

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
)
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont, QIcon

from components.status_bar import PersistentStatusBar
from tabs.overview import OverviewTab
from tabs.prereqs import PrereqsTab
from tabs.tech_tools import TechToolsTab
from tabs.gamer_tools import GamerToolsTab
from tabs.ios.tab import IosDriverTab
from tabs.android.tab import AndroidDriverTab
from tabs.hardware.tab import HardwareHealthTab
from utils.hwid import get_smbios_info, get_display_summary
from utils.paths import resource_path
from utils.resource_manager import configure_global_thread_pool, install_global_crash_handler

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
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move((geo.width() - self.width()) // 2,
                      (geo.height() - self.height()) // 2)

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
        self.tabs.addTab(PrereqsTab(),        "⚙️  Prerequisites")
        self.tabs.addTab(TechToolsTab(),      "🔧  Tech Tools")
        self.tabs.addTab(GamerToolsTab(),     "🎮  Gamer Tools")
        self.tabs.addTab(IosDriverTab(),      "📱  iOS Tools")
        self.tabs.addTab(AndroidDriverTab(),  "🤖  Android Tools")

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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
