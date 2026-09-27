# =============================================================================
# RootForgeKit — Persistent Bottom Status Taskbar
# QStatusBar component that remains visible across ALL interior tabs. Displays:
#   Left:   System state (● SYSTEM READY)
#   Centre: Operation progress bar + caption (hidden when idle)
#   Right:  SMBIOS Motherboard Make/Model + Host ID hash
#
# All three live inside ONE container widget with stretch factors 1 / 0 / 1.
# QStatusBar's natural behaviour — a left-anchored widget plus a right-anchored
# permanent widget — cannot express "dead centre": there is no item whose
# position is computed as (available - centre_width) / 2. Splitting the space
# evenly between a left half and a right half does exactly that, and it keeps
# the bar centred whether the caption is shown or hidden.
# =============================================================================

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QStatusBar, QWidget,
)

# How long a "✓ Done" / "✗ Failed" line stays up before the bar disappears.
RESULT_FLASH_MS = 2400

# Fixed width of the centre caption slot. A QLabel reports its full text
# width as its *minimum*, and a QStatusBar's minimum propagates straight
# into QMainWindow.minimumSizeHint() — so an uncapped caption literally
# widens the application window as the words get longer. Pinning the slot
# keeps the bar's minimum below the content-driven one no matter what we
# print; the text is elided to match and the full string goes in a tooltip.
CAPTION_WIDTH = 460


class PersistentStatusBar(QStatusBar):
    """
    Persistent bottom status bar attached to QMainWindow.

    Displays:
        Left side:  Session state indicator with colored dot
        Centre:     Live progress bar for the operation currently running
        Right side: SMBIOS motherboard identity + truncated Host ID hash

    Usage:
        status_bar = PersistentStatusBar()
        main_window.setStatusBar(status_bar)
        status_bar.set_hwid_info(board_label, host_id_short)

        status_bar.begin_operation("Installing Docker Desktop")
        status_bar.set_progress(3, "Installing Docker Desktop (3/6)")
        status_bar.end_operation("Installed", ok=True)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PersistentStatusBar")
        self.setSizeGripEnabled(False)
        self.setFixedHeight(32)
        self._op_token = 0
        self._op_max = 0
        self._setup_ui()

    def _setup_ui(self):
        """Build the status bar as one left/centre/right container."""

        container = QWidget()
        container.setObjectName("StatusContainer")
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # ---- Left: session state -------------------------------------
        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self._state_label = QLabel("●  SYSTEM READY")
        self._state_label.setObjectName("StatusStateLabel")
        self._state_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self._state_label.setStyleSheet("color: #4caf50; padding-left: 8px;")
        left_layout.addWidget(self._state_label)
        left_layout.addStretch(1)

        # ---- Centre: operation progress ------------------------------
        self._op_widget = QWidget()
        self._op_widget.setObjectName("StatusOpWidget")
        op_layout = QHBoxLayout(self._op_widget)
        op_layout.setContentsMargins(16, 0, 16, 0)
        op_layout.setSpacing(10)

        self._op_label = QLabel("")
        self._op_label.setObjectName("StatusOpLabel")
        self._op_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self._op_label.setStyleSheet("color: #00e5ff; padding: 0 2px;")
        self._op_label.setFixedWidth(CAPTION_WIDTH)
        self._op_label.setAlignment(Qt.AlignCenter)
        op_layout.addWidget(self._op_label)

        self._progress = QProgressBar()
        self._progress.setObjectName("StatusBarProgress")
        self._progress.setFixedWidth(240)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)  # indeterminate until told otherwise
        # A 6px bar inside a 32px line would otherwise sit wherever the box
        # layout's default cross-axis alignment drops it.
        op_layout.addWidget(self._progress, alignment=Qt.AlignVCenter)
        op_layout.setAlignment(self._op_label, Qt.AlignVCenter)
        self._op_widget.hide()

        # ---- Right: SMBIOS identity -----------------------------------
        right_widget = QWidget()
        right_widget.setObjectName("StatusRightWidget")
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 12, 0)
        right_layout.setSpacing(12)
        right_layout.addStretch(1)   # push the identity text to the far right

        sep = QLabel("│")
        sep.setObjectName("StatusSep")
        sep.setFont(QFont("Consolas", 9))
        sep.setStyleSheet("color: #30363d;")
        right_layout.addWidget(sep)

        self._board_label = QLabel("🖥  Detecting motherboard...")
        self._board_label.setObjectName("StatusBoardLabel")
        self._board_label.setFont(QFont("Segoe UI", 9))
        self._board_label.setStyleSheet("color: #8b949e;")
        right_layout.addWidget(self._board_label)

        sep2 = QLabel("│")
        sep2.setObjectName("StatusSep")
        sep2.setFont(QFont("Consolas", 9))
        sep2.setStyleSheet("color: #30363d;")
        right_layout.addWidget(sep2)

        self._hwid_label = QLabel("HWID: ...")
        self._hwid_label.setObjectName("StatusHwidLabel")
        self._hwid_label.setFont(QFont("Consolas", 9))
        self._hwid_label.setStyleSheet("color: #536dfe;")
        self._hwid_label.setToolTip("Hardware Host ID (SHA-256)")
        right_layout.addWidget(self._hwid_label)

        # 1 : 0 : 1 — the centre item lands exactly in the middle of the bar.
        row.addWidget(left_widget, stretch=1)
        row.addWidget(self._op_widget, stretch=0)
        row.addWidget(right_widget, stretch=1)

        self.addWidget(container, stretch=1)
        # Kept for geometry assertions and debugging.
        self._container = container

    # -------------------------------------------------------------------------
    # Public API — identity
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

    # -------------------------------------------------------------------------
    # Public API — centre progress
    # -------------------------------------------------------------------------

    def begin_operation(self, label: str, *, indeterminate: bool = True,
                        maximum: int = 0) -> None:
        """Show the progress bar for an operation about to start.

        Args:
            label:          Caption shown beside the bar.
            indeterminate:  True for "working, duration unknown" (animated
                            bar). False when `maximum` is a real count.
            maximum:        Total units when indeterminate is False.
        """
        self._op_token += 1
        self._progress.show()
        if indeterminate:
            self._op_max = 0
            self._progress.setRange(0, 0)
        else:
            self._op_max = max(1, maximum)
            self._progress.setRange(0, self._op_max)
            self._progress.setValue(0)
        self._set_op_caption(label, "#00e5ff")
        self._op_widget.show()

    def set_progress(self, value: int, label: str | None = None) -> None:
        """Advance a determinate bar. Ignored if no operation is running."""
        if not self._op_widget.isVisible():
            return
        if self._op_max <= 0:
            # Became determinate after being started as indeterminate.
            self._op_max = 1
            self._progress.setRange(0, 1)
        self._progress.setValue(max(0, min(value, self._op_max)))
        if label is not None:
            self._set_op_caption(label, "#00e5ff")

    def end_operation(self, message: str = "", ok: bool = True) -> None:
        """Hide the bar, optionally flashing a result line first.

        The flash is token-guarded: starting a new operation invalidates any
        pending hide scheduled by a previous one.
        """
        self._progress.hide()
        if not message:
            self._op_widget.hide()
            self._op_label.setText("")
            return
        self._set_op_caption(message, "#00e676" if ok else "#ff5252")
        token = self._op_token
        QTimer.singleShot(RESULT_FLASH_MS, lambda: self._clear_flash(token))

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _set_op_caption(self, text: str, colour: str) -> None:
        fm = self._op_label.fontMetrics()
        # Reserve a little slack for the QSS padding (0 2px + 0 4px).
        room = CAPTION_WIDTH - 16
        if fm.horizontalAdvance(text) > room:
            text = fm.elidedText(text, Qt.ElideMiddle, room)
        self._op_label.setText(text)
        self._op_label.setToolTip(text)
        self._op_label.setStyleSheet(f"color: {colour}; padding: 0 2px;")

    def _clear_flash(self, token: int) -> None:
        # Only the operation that scheduled this hide may carry it out; if a
        # newer operation has since begun, leave its caption alone.
        if token != self._op_token:
            return
        self._op_widget.hide()
        self._op_label.setText("")
