# =============================================================================
# RootForgeKit — Main Application Entry Point
# Architecture:
#   QMainWindow
#     ├── QStackedWidget (central widget)
#     │     ├── Page 0: AuthSplash (login/welcome)
#     │     └── Page 1: QTabWidget (Overview, Prereqs, Tech, Gamer)
#     └── PersistentStatusBar (always visible across all pages)
#
# HWID is queried in a background thread and pushed to the status bar.
# =============================================================================

import sys
import os

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QStackedWidget,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon

from components.auth_dialog import AuthSplash
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
        - QStackedWidget as central widget
            Page 0 → AuthSplash  (login screen, status bar visible below)
            Page 1 → QTabWidget  (all tool tabs)
        - PersistentStatusBar at bottom (always visible)
    """

    def __init__(self):
        super().__init__()
        self.role = "guest"
        self.username = ""
        self.tier = "guest"

        # Configure worker thread pool limits based on host CPU topology
        self.allocated_cores = configure_global_thread_pool()

        self._setup_window()
        self._setup_status_bar()
        self._setup_views()
        self._start_hwid_query()

        # Intercept crashes globally and direct them to active tab console
        install_global_crash_handler(log_callback=self.route_crash_to_console)

    def route_crash_to_console(self, crash_report: str):
        """Routes unhandled exceptions directly into the active tab console."""
        current = self.stack.currentWidget()
        if isinstance(current, QTabWidget):
            active_tab = current.currentWidget()
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
        self.status_bar.sign_out_requested.connect(self._on_sign_out)
        self.setStatusBar(self.status_bar)

    def _setup_views(self):
        """Build the QStackedWidget with auth splash and tab pages."""
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # ---- Page 0: Login Splash ----
        self.auth_splash = AuthSplash()
        self.auth_splash.auth_complete.connect(self._on_auth_complete)
        self.stack.addWidget(self.auth_splash)  # index 0

        # ---- Page 1: Tab Container (built but not shown yet) ----
        # Tabs are constructed lazily in _on_auth_complete to pass the role
        # We add a placeholder that gets replaced on auth
        self._tabs_placeholder = QTabWidget()
        self.stack.addWidget(self._tabs_placeholder)  # index 1

        # Start on the login splash
        self.stack.setCurrentIndex(0)

    def _build_tabs(self, role: str, tier: str = "free", display_role: str = "") -> QTabWidget:
        """
        Construct the main tab widget with role-gated tabs.

        Guest sessions only get Overview + Hardware Health — no Prerequisites,
        Tech/Gamer Tools, or iOS/Android device tools. Registered sessions
        (technician or admin — both pass role="technician" here, see
        components/auth_dialog.py) get every tab; `tier` is threaded into
        Tech/Gamer Tools for future per-feature gating (see utils/tiers.py) —
        every tab is visible at "free" tier today, no individual tool is tier
        -locked yet. `display_role` lets those tabs bypass tier checks for
        admins regardless of stored tier (see utils.tiers.has_tier_access).
        """
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setObjectName("MainTabs")

        tabs.addTab(OverviewTab(),           "📊  Overview")
        tabs.addTab(HardwareHealthTab(),     "🩺  Hardware Health")

        if role != "guest":
            tabs.addTab(PrereqsTab(),            "⚙️  Prerequisites")
            tabs.addTab(TechToolsTab(role=role, tier=tier, display_role=display_role), "🔧  Tech Tools")
            tabs.addTab(GamerToolsTab(role=role, tier=tier, display_role=display_role),"🎮  Gamer Tools")
            tabs.addTab(IosDriverTab(),          "📱  iOS Tools")
            tabs.addTab(AndroidDriverTab(),      "🤖  Android Tools")

        return tabs

    def _start_hwid_query(self):
        """Launch SMBIOS query in background thread."""
        self._hwid_worker = HwidWorker()
        self._hwid_worker.hwid_ready.connect(self._on_hwid_ready)
        self._hwid_worker.start()

    # -------------------------------------------------------------------------
    # Signal Handlers
    # -------------------------------------------------------------------------

    def _on_auth_complete(self, role: str, username: str = "", server_role: str = "", tier: str = "free"):
        """Handle authentication result — build tabs and switch to main view."""
        self.role = role
        self.username = username
        self.tier = tier
        display_role = server_role or role
        print(f"[AUTH] Authenticated as: {role}" + (f" ({username})" if username else ""))

        # Update status bar session state (tab-gating role stays "technician"
        # for admins too — display_role only changes the badge shown).
        self.status_bar.set_session_state(role, username, display_role)

        # Update window title with the actual server role
        who = f" — {username}" if username else ""
        self.setWindowTitle(
            f"RootForgeKit v{APP_VERSION} — System Utility & Diagnostic Suite  [{display_role.upper()}]{who}"
        )

        # Replace the placeholder tab widget with the real one. This only
        # exists in the stack the very first time — after a sign-out,
        # _on_sign_out() already removed and deleted whatever was showing
        # (the placeholder or a previous _main_tabs), so _tabs_placeholder
        # is a dangling reference on every login after the first. Guard on
        # it rather than unconditionally touching it, which crashed with
        # "wrapped C/C++ object ... has been deleted" on sign-out → sign-in.
        self._main_tabs = self._build_tabs(role, tier, display_role)
        if self._tabs_placeholder is not None:
            self.stack.removeWidget(self._tabs_placeholder)
            self._tabs_placeholder.deleteLater()
            self._tabs_placeholder = None
        self.stack.addWidget(self._main_tabs)

        # Switch to tab view (index 1 after removal+add = index 1)
        self.stack.setCurrentWidget(self._main_tabs)

    def _on_sign_out(self):
        """Log out the current session and return to the login splash."""
        from utils.auth_client import AuthClient
        AuthClient().logout()

        self.role = "guest"
        self.username = ""
        self.tier = "guest"
        self.status_bar.set_session_state("ready")
        self.setWindowTitle(f"RootForgeKit v{APP_VERSION} — System Utility & Diagnostic Suite")

        # Swap in a fresh AuthSplash — simpler and more reliable than trying
        # to rewind the previous instance's internal (possibly mid-request)
        # state.
        fresh_splash = AuthSplash()
        fresh_splash.auth_complete.connect(self._on_auth_complete)

        current = self.stack.currentWidget()
        self.stack.addWidget(fresh_splash)
        self.stack.setCurrentWidget(fresh_splash)
        if current is not None:
            self.stack.removeWidget(current)
            current.deleteLater()
        self.auth_splash = fresh_splash

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
