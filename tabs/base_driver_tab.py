import platform
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLabel, QGroupBox, QFrame, QSizePolicy, QSplitter
)
from PySide6.QtCore import Qt
from utils.resource_manager import configure_global_thread_pool


# ── Collapsible Section Widget ────────────────────────────────────────────────


class CollapsibleSection(QWidget):
    """
    A widget that can be collapsed/expanded via a header button.
    Used across the app for accordion-style UI sections.
    """
    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        self._expanded = expanded

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header row
        self._header = QPushButton()
        self._header.setObjectName("CollapsibleHeader")
        self._header.setCheckable(True)
        self._header.setChecked(expanded)
        self._header.clicked.connect(self._toggle)
        self._update_header_text(title)
        outer.addWidget(self._header)

        # Content container
        self._content = QFrame()
        self._content.setObjectName("CollapsibleContent")
        self._content.setVisible(expanded)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 8, 12, 8)
        outer.addWidget(self._content)

        self._title = title

    def _update_header_text(self, title: str):
        arrow = "▼" if self._expanded else "▶"
        self._header.setText(f"  {arrow}  {title}")

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._update_header_text(self._title)
        self._header.setChecked(self._expanded)

    def content_layout(self):
        return self._content_layout

    def set_expanded(self, val: bool):
        if val != self._expanded:
            self._expanded = val
            self._content.setVisible(val)
            self._update_header_text(self._title)
            self._header.setChecked(val)


# ── Base Driver Tab ───────────────────────────────────────────────────────────
# Stripped down: no requirements checklist (that now lives in PrereqsTab).
# Just provides the basic layout scaffold (header, tools panel, verbose console)
# for iOS and Android device tool tabs.

class BaseDriverTab(QWidget):
    def __init__(self, platform_name: str):
        super().__init__()
        self.platform_name = platform_name
        self.host_os = platform.system().lower()
        self.allocated_cores = configure_global_thread_pool()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Header ──────────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        self.os_label = QLabel(
            f"Host OS: <b>{platform.system()} {platform.release()}</b> | "
            f"Allocated Workers: <b>{self.allocated_cores} Core(s)</b>"
        )
        header_layout.addWidget(self.os_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # ── Resizable split: top = tools/content, bottom = verbose console ──
        self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        self.content_splitter.setObjectName("TabContentSplitter")
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(10)

        # Top pane — subclasses insert their views into self.content_layout
        top_pane = QWidget()
        self.content_layout = QVBoxLayout(top_pane)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)

        self.tools_group = QGroupBox(f"Active {self.platform_name} Actions")
        self.tools_layout = QHBoxLayout(self.tools_group)
        self.content_layout.addWidget(self.tools_group)
        self.content_splitter.addWidget(top_pane)

        # Bottom pane — verbose console
        console_pane = QWidget()
        console_layout = QVBoxLayout(console_pane)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(4)
        console_layout.addWidget(QLabel("Verbose Terminal Output:"))

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(60)
        self.console.setStyleSheet(
            "font-family: monospace; background-color: #1e1e1e; color: #d4d4d4;"
        )
        console_layout.addWidget(self.console)
        self.content_splitter.addWidget(console_pane)

        self.content_splitter.setStretchFactor(0, 3)
        self.content_splitter.setStretchFactor(1, 2)
        self.content_splitter.setSizes([420, 220])
        layout.addWidget(self.content_splitter, stretch=1)

    def log_verbose(self, text: str):
        self.console.append(text)
