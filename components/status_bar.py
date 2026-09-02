# =============================================================================
# RootForgeKit — Persistent Bottom Status Taskbar
# QStatusBar component that remains visible across ALL interior tabs. Displays:
#   Left:  System state (● SYSTEM READY)
#   Right: SMBIOS Motherboard Make/Model + Host ID hash
# =============================================================================

from PySide6.QtWidgets import QStatusBar, QLabel, QWidget, QHBoxLayout
from PySide6.QtGui import QFont


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
    """

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

    def set_custom_message(self, message: str, color: str = "#8b949e"):
        """Set a temporary custom message on the left side."""
        self._state_label.setText(f"●  {message}")
        self._state_label.setStyleSheet(f"color: {color}; padding-left: 8px;")
