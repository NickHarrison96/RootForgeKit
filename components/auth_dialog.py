# =============================================================================
# RootForgeKit — Login Splash & Role State Signal Manager
# Embeddable QWidget (not QDialog) that lives inside QStackedWidget so the
# persistent QStatusBar remains visible underneath. Emits role signal on auth.
#
# Backed by utils.auth_client.AuthClient — a self-hosted FastAPI/SQLite auth
# server with HWID license binding (see server/README.md). Network calls run
# on a background QThread so a slow or offline server never freezes the UI.
#
# Role mapping: the server tracks "admin" / "technician". This app's tab
# gating only knows "technician" (every `role != "technician"` check across
# tabs) — both server roles resolve to the app role "technician" here. There
# is no separate admin-only surface in the UI yet.
# =============================================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QSizePolicy, QSpacerItem,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QPixmap

from utils.auth_client import AuthClient, AuthResult
from utils.paths import resource_path


class _AuthWorker(QThread):
    """Runs one AuthClient call off the UI thread."""
    result_ready = Signal(object)  # AuthResult

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self):
        self.result_ready.emit(self._fn(*self._args))


# Non-fatal statuses where the request round-tripped but auth did not
# succeed — the form should re-enable and let the user try again.
_RETRY_STATUSES = {
    "invalid_credentials", "hwid_mismatch", "rate_limited",
    "username_taken", "weak_password", "offline", "server_error",
}


class AuthSplash(QWidget):
    """
    Full-page login splash widget embedded as page 0 of QStackedWidget.
    The persistent QStatusBar remains visible below this page.

    Signals:
        auth_complete(str, str, str, str): Emitted with
                                       (role, username, server_role, tier) on
                                       success. role is "technician" or
                                       "guest" and drives tab gating; username
                                       is "" for guest sessions; server_role is
                                       the raw role the auth server reported
                                       ("admin"/"technician"/"guest"), for
                                       display purposes only; tier is
                                       "free"/"paid"/"diamond"/"guest" (see
                                       utils/tiers.py) for feature gating.
    """
    auth_complete = Signal(str, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.role = "guest"
        self.server_role = "guest"
        self.tier = "guest"
        self.client = AuthClient()
        self._register_mode = False
        self._worker: _AuthWorker | None = None
        self.setObjectName("AuthSplash")
        self._setup_ui()
        self._check_saved_session()

    def _setup_ui(self):
        """Build the centered login splash layout."""
        # Outer layout centers the login card vertically and horizontally
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ---- Login Card Container ----
        card = QFrame()
        card.setObjectName("AuthCard")
        card.setFixedSize(440, 610)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(44, 32, 44, 32)
        card_layout.setSpacing(0)

        # ---- App Branding ----
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap(resource_path("resources", "app.png"))
        if logo_pixmap.isNull():
            # Keep the old emoji as a fallback so a missing asset degrades to
            # the previous look instead of an empty gap in the card.
            logo_label.setText("🔧")
            logo_label.setFont(QFont("Segoe UI Emoji", 40))
        else:
            logo_label.setPixmap(logo_pixmap.scaled(
                96, 96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        card_layout.addWidget(logo_label)
        card_layout.addSpacing(8)

        title_label = QLabel("RootForgeKit")
        title_label.setObjectName("AuthTitle")
        title_label.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_label)

        subtitle_label = QLabel("System Utility & Diagnostic Suite")
        subtitle_label.setObjectName("AuthSubtitle")
        subtitle_label.setFont(QFont("Segoe UI", 10))
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(subtitle_label)

        byline_label = QLabel("by KushNick420")
        byline_label.setObjectName("AuthByline")
        byline_label.setFont(QFont("Segoe UI", 9))
        byline_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(byline_label)
        card_layout.addSpacing(18)

        # ---- Separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("AuthSeparator")
        card_layout.addWidget(sep)
        card_layout.addSpacing(16)

        # ---- Username ----
        user_lbl = QLabel("Username")
        user_lbl.setObjectName("AuthFieldLabel")
        user_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        card_layout.addWidget(user_lbl)
        card_layout.addSpacing(5)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        self.username_input.setObjectName("AuthInput")
        self.username_input.setMinimumHeight(40)
        card_layout.addWidget(self.username_input)
        card_layout.addSpacing(14)

        # ---- Password ----
        pass_lbl = QLabel("Password")
        pass_lbl.setObjectName("AuthFieldLabel")
        pass_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        card_layout.addWidget(pass_lbl)
        card_layout.addSpacing(5)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setObjectName("AuthInput")
        self.password_input.setMinimumHeight(40)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(6)

        # ---- Status Label ----
        self.status_label = QLabel("")
        self.status_label.setObjectName("AuthStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(34)
        card_layout.addWidget(self.status_label)
        card_layout.addSpacing(10)

        # ---- Submit Button (Sign In / Create Account, per mode) ----
        self.submit_btn = QPushButton("🔐  Sign In as Technician")
        self.submit_btn.setObjectName("AuthLoginBtn")
        self.submit_btn.setMinimumHeight(36)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.clicked.connect(self._handle_submit)
        card_layout.addWidget(self.submit_btn)
        card_layout.addSpacing(8)

        # ---- Mode toggle: Sign In <-> Create Account ----
        self.mode_toggle_btn = QPushButton("Need an account? Register")
        self.mode_toggle_btn.setObjectName("AuthModeToggleBtn")
        self.mode_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_toggle_btn.setFlat(True)
        self.mode_toggle_btn.clicked.connect(self._toggle_mode)
        card_layout.addWidget(self.mode_toggle_btn)
        card_layout.addSpacing(10)

        # ---- Guest Button ----
        self.guest_btn = QPushButton("Continue as Guest")
        self.guest_btn.setObjectName("AuthGuestBtn")
        self.guest_btn.setMinimumHeight(32)
        self.guest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.guest_btn.clicked.connect(self._handle_guest)
        card_layout.addWidget(self.guest_btn)

        card_layout.addStretch()

        outer.addWidget(card)

        # ---- Enter key bindings ----
        self.password_input.returnPressed.connect(self._handle_submit)
        self.username_input.returnPressed.connect(lambda: self.password_input.setFocus())

    # -------------------------------------------------------------------------
    # Mode toggle (Sign In <-> Create Account)
    # -------------------------------------------------------------------------

    def _toggle_mode(self):
        self._register_mode = not self._register_mode
        if self._register_mode:
            self.submit_btn.setText("✨  Create Account")
            self.mode_toggle_btn.setText("Already have an account? Sign In")
        else:
            self.submit_btn.setText("🔐  Sign In as Technician")
            self.mode_toggle_btn.setText("Need an account? Register")
        self._set_status("", "")

    # -------------------------------------------------------------------------
    # Startup auto-login
    # -------------------------------------------------------------------------

    def _check_saved_session(self):
        """
        Non-blocking check for a saved session on launch, so a returning user
        does not have to re-enter credentials every time. The form paints
        immediately either way — this only short-circuits it on success.
        """
        self._set_status("Checking for a saved session…", "#8b949e")
        self._run_worker(self.client.verify_saved_session, callback=self._on_session_checked)

    def _on_session_checked(self, result: AuthResult):
        if result.ok:
            self.role = "technician"
            self.server_role = result.role or "technician"
            self.tier = result.tier or "free"
            self._set_status(f"✅  Welcome back, {result.username}.", "#00e676")
            self.auth_complete.emit(self.role, result.username or "", self.server_role, self.tier)
        else:
            # offline / no_session / invalid_credentials: just clear the
            # "checking" message and let the user sign in normally.
            self._set_status("", "")

    # -------------------------------------------------------------------------
    # Sign In / Create Account
    # -------------------------------------------------------------------------

    def _handle_submit(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            self._set_status("⚠️  Please enter both username and password.", "#f0a500")
            return

        self._set_controls_enabled(False)
        if self._register_mode:
            self._set_status("Creating account…", "#8b949e")
            self._run_worker(self.client.register, username, password,
                             callback=self._on_auth_result)
        else:
            self._set_status("Signing in…", "#8b949e")
            self._run_worker(self.client.login, username, password,
                             callback=self._on_auth_result)

    def _on_auth_result(self, result: AuthResult):
        self._set_controls_enabled(True)

        if result.ok:
            self.role = "technician"
            self.server_role = result.role or "technician"
            self.tier = result.tier or "free"
            verb = "Account created" if self._register_mode else "Authenticated"
            self._set_status(f"✅  {verb} as {result.username}.", "#00e676")
            self.auth_complete.emit(self.role, result.username or "", self.server_role, self.tier)
            return

        if result.status in _RETRY_STATUSES:
            self._set_status(f"❌  {result.message}", "#ff5252")
            self.password_input.clear()
            self.password_input.setFocus()
        else:
            self._set_status(f"❌  {result.message}", "#ff5252")

    def _handle_guest(self):
        """Emit guest role and allow navigation to main view. No server call."""
        self.role = "guest"
        self.server_role = "guest"
        self.tier = "guest"
        self.auth_complete.emit(self.role, "", self.server_role, self.tier)

    def get_role(self) -> str:
        """Return the resolved role."""
        return self.role

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _run_worker(self, fn, *args, callback=None):
        """Run an AuthClient call off the UI thread; deliver result to callback."""
        target = callback or (lambda _r: None)
        self._worker = _AuthWorker(fn, *args, parent=self)
        self._worker.result_ready.connect(target)
        self._worker.start()

    def _set_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};" if color else "")

    def _set_controls_enabled(self, enabled: bool):
        for widget in (self.username_input, self.password_input,
                      self.submit_btn, self.guest_btn, self.mode_toggle_btn):
            widget.setEnabled(enabled)
