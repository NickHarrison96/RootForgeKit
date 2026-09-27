# =============================================================================
# RootForgeKit — Tool Card
# A single row in the Tech / Gamer tool lists: status glyph, name, one-line
# description, and a single action button. Styled by styles.qss (#ToolCard).
# =============================================================================

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


# status key -> (glyph, colour, tooltip)
STATUS = {
    "checking":  ("⏳", "#8b949e", "Checking this PC…"),
    "installed": ("✅", "#00e676", "Installed"),
    "arp":       ("🔵", "#29b6f6", "Installed on this PC, but not from winget"),
    "missing":   ("❌", "#ff5252", "Not installed"),
    "update":    ("⬆️", "#ffc107", "Update available"),
    "unknown":   ("❔", "#8b949e", "Status unknown"),
    "ready":     ("●", "#00e5ff", "Ready to run"),
    "running":   ("◉", "#ffc107", "Running…"),
    "done":      ("✓", "#00e676", "Completed"),
    "failed":    ("✗", "#ff5252", "Failed"),
}

# Statuses worth a visible line even with no detail attached. "ready" is the
# resting state of every command card, so it stays hidden — one line of
# "Ready to run" under 50 cards is noise, not feedback.
_ALWAYS_SHOW = {"checking", "update", "missing", "unknown",
                "running", "done", "failed", "arp"}


class ToolCard(QFrame):
    """One actionable tool row."""

    actionRequested = Signal(object)  # emits the card itself

    def __init__(self, icon: str, name: str, description: str,
                 action_text: str = "Run", risk: str = "low", parent=None):
        super().__init__(parent)
        self.setObjectName("ToolCard")
        self.setToolTip(description)
        self._status_key = "ready"
        self._status_detail = ""
        self._status_text = ""

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(14)

        self.glyph = QLabel(icon)
        self.glyph.setObjectName("ToolCardGlyph")
        self.glyph.setFont(QFont("Segoe UI Emoji", 16))
        self.glyph.setFixedWidth(30)
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.glyph.setToolTip(description)
        row.addWidget(self.glyph)

        text = QVBoxLayout()
        text.setSpacing(2)

        self.name = QLabel(name)
        self.name.setObjectName("ToolCardName")
        self.name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        text.addWidget(self.name)

        self.desc = QLabel(description)
        self.desc.setObjectName("ToolCardDesc")
        self.desc.setFont(QFont("Segoe UI", 9))
        self.desc.setWordWrap(True)
        text.addWidget(self.desc)

        # Visible outcome line. Set status details used to live only in a
        # tooltip, which meant a failed run and a successful one looked
        # identical unless you hovered the row. This is the row's answer to
        # "did that actually work?".
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("ToolCardStatus")
        self.status_lbl.setFont(QFont("Segoe UI", 9))
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setVisible(False)
        text.addWidget(self.status_lbl)

        row.addLayout(text, stretch=1)

        self.action_btn = QPushButton(action_text)
        self.action_btn.setObjectName("ToolRunBtn")
        self.action_btn.setProperty("risk", risk)
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setFixedWidth(118)
        self.action_btn.setMinimumHeight(28)
        # Deliberately a lambda rather than
        # `self.action_btn.clicked.connect(self.actionRequested.emit)`.
        # QAbstractButton.clicked carries a defaulted `checked` parameter that
        # PySide6 does not forward when the slot is another signal's emit, so
        # the straight connection calls emit() with zero arguments and raises
        # "actionRequested(PyObject) needs 1 argument(s) 0 given" on every
        # press. The lambda pins the arity to exactly one — the card.
        self.action_btn.clicked.connect(
            lambda _checked=False, _card=self: _card.actionRequested.emit(_card)
        )
        row.addWidget(self.action_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

    # -- status ------------------------------------------------------------

    @property
    def status_key(self) -> str:
        return self._status_key

    @property
    def status_detail(self) -> str:
        return self._status_detail

    @property
    def status_text(self) -> str:
        return self._status_text

    def set_status(self, status: str, detail: str = "") -> None:
        """Set the card's state and render it twice: the glyph, and a visible
        status line under the description.

        `detail` carries the specifics — versions, exit codes, the reason a
        check failed — so the row answers on its own without a tooltip.
        """
        glyph, colour, tip = STATUS.get(status, STATUS["unknown"])
        if status not in STATUS:
            tip = f"Unknown status '{status}'"
        text = f"{tip} — {detail}" if detail else tip

        self._status_key = status
        self._status_detail = detail
        self._status_text = text

        self.glyph.setText(glyph)
        self.glyph.setStyleSheet(f"color: {colour}; background: transparent;")
        self.glyph.setToolTip(text)

        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"color: {colour}; background: transparent;")
        self.status_lbl.setToolTip(text)
        self.status_lbl.setVisible(bool(detail) or status in _ALWAYS_SHOW)

    def set_action(self, text: str, enabled: bool = True) -> None:
        self.action_btn.setText(text)
        self.action_btn.setEnabled(enabled)

    @property
    def risk(self) -> str:
        return self.action_btn.property("risk") or "low"
