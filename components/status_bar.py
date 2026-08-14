# =============================================================================
# NicksFix — Persistent Bottom Status Taskbar
# QStatusBar component that remains visible across ALL views (login splash +
# all interior tabs). Displays:
#   Left:  Session state (● SYSTEM READY / ● LOGGED IN [ROLE])
#   Right: SMBIOS Motherboard Make/Model + Host ID hash
# =============================================================================

from PyQt6.QtWidgets import QStatusBar, QLabel, QWidget, QHBoxLayout, QFrame, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class PersistentStatusBar(QStatusBar):
    """
    Persistent bottom status bar attached to QMainWindow.

    Displays:
        Left side:  Session state indicator with colored dot
        Right side: SMBIOS motherboard identity + truncated Host ID hash

    Usage:
        status_bar = PersistentStatusBar()
        main_window.setStatusBar(status_bar)
        status_bar.set_hwid_info(board_label, host_id_short)
        status_bar.set_session_state("technician")
    """

    sign_out_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PersistentStatusBar")
        self.setSizeGripEnabled(False)
        self.setFixedHeight(32)
        self._setup_ui()

    def _setup_ui(self):
        """Build the status bar layout with left and right sections."""

        # ---- Left Section: Session State ----
        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self._state_label = QLabel("●  SYSTEM READY")
        self._state_label.setObjectName("StatusStateLabel")
        self._state_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self._state_label.setStyleSheet("color: #4caf50; padding-left: 8px;")
        left_layout.addWidget(self._state_label)

        self._sign_out_btn = QPushButton("Sign Out")
        self._sign_out_btn.setObjectName("StatusSignOutBtn")
        self._sign_out_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sign_out_btn.setVisible(False)   # only shown once actually logged in
        self._sign_out_btn.clicked.connect(self.sign_out_requested.emit)
        left_layout.addWidget(self._sign_out_btn)

        left_layout.addStretch()
        self.addWidget(left_widget, stretch=1)

        # ---- Right Section: SMBIOS Identity ----
        right_widget = QWidget()
        right_widget.setObjectName("StatusRightWidget")
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 12, 0)
        right_layout.setSpacing(12)

        # Separator dot
        sep = QLabel("│")
        sep.setObjectName("StatusSep")
        sep.setFont(QFont("Consolas", 9))
        sep.setStyleSheet("color: #30363d;")
        right_layout.addWidget(sep)

        # Motherboard label
        self._board_label = QLabel("🖥  Detecting motherboard...")
        self._board_label.setObjectName("StatusBoardLabel")
        self._board_label.setFont(QFont("Segoe UI", 9))
        self._board_label.setStyleSheet("color: #8b949e;")
        right_layout.addWidget(self._board_label)

        # Another separator
        sep2 = QLabel("│")
        sep2.setObjectName("StatusSep")
        sep2.setFont(QFont("Consolas", 9))
        sep2.setStyleSheet("color: #30363d;")
        right_layout.addWidget(sep2)

        # Host ID hash
        self._hwid_label = QLabel("HWID: ...")
        self._hwid_label.setObjectName("StatusHwidLabel")
        self._hwid_label.setFont(QFont("Consolas", 9))
        self._hwid_label.setStyleSheet("color: #536dfe;")
        self._hwid_label.setToolTip("Hardware Host ID (SHA-256)")
        right_layout.addWidget(self._hwid_label)

        self.addPermanentWidget(right_widget)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_hwid_info(self, board_label: str, host_id_short: str, host_id_full: str = ""):
        """
        Update the SMBIOS identity display.

        Args:
            board_label:    "Manufacturer Model" string
            host_id_short:  First 16 chars of the SHA-256 hash
            host_id_full:   Full 64-char hash (shown in tooltip)
        """
        self._board_label.setText(f"🖥  {board_label}")
        self._hwid_label.setText(f"HWID: {host_id_short}")
        if host_id_full:
            self._hwid_label.setToolTip(f"Full Host ID: {host_id_full}")

    def set_session_state(self, role: str, username: str = "", display_role: str | None = None):
        """
        Update the session state indicator.

        Args:
            role:         "guest", "technician", or "ready" (pre-login) — drives
                          tab access, unchanged by this method.
            username:     Authenticated username, shown for a real (non-guest,
                          non-debug) session.
            display_role: The server-reported role ("admin"/"technician") shown
                          in the badge. Defaults to `role`. Kept separate from
                          `role` because the app grants admin and technician
                          identical tab access — only the badge distinguishes them.
        """
        display_role = display_role or role
        who = f" as {username}" if username and role == "technician" else ""
        if role == "technician" and display_role == "admin":
            self._state_label.setText(f"●  LOGGED IN [ADMIN]{who}")
            self._state_label.setStyleSheet("color: #ff5252; padding-left: 8px; font-weight: bold;")
            self._sign_out_btn.setVisible(True)
        elif role == "technician":
            self._state_label.setText(f"●  LOGGED IN [TECHNICIAN]{who}")
            self._state_label.setStyleSheet("color: #00e5ff; padding-left: 8px;")
            self._sign_out_btn.setVisible(True)
        elif role == "guest":
            self._state_label.setText("●  LOGGED IN [GUEST]")
            self._state_label.setStyleSheet("color: #ffc107; padding-left: 8px;")
            self._sign_out_btn.setVisible(True)
        else:
            self._state_label.setText("●  SYSTEM READY")
            self._state_label.setStyleSheet("color: #4caf50; padding-left: 8px;")
            self._sign_out_btn.setVisible(False)

    def set_custom_message(self, message: str, color: str = "#8b949e"):
        """Set a temporary custom message on the left side."""
        self._state_label.setText(f"●  {message}")
        self._state_label.setStyleSheet(f"color: {color}; padding-left: 8px;")
