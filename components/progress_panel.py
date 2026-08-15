# =============================================================================
# RootForgeKit — Operation Progress Panel
#
# Shared progress UI for long-running device operations (backup, restore, DDI
# mount, IPSW flash, bulk pull). Pairs with utils.process_runner:
#
#     self.progress = OperationProgressPanel()
#     self.runner   = StreamingProcessRunner()
#     self.progress.bind(self.runner)
#     self.runner.start(["-m", "pymobiledevice3", "backup2", "backup", path])
#
# Shows a live percentage bar (or an indeterminate sweep when the total is
# unknown), elapsed time, the current step, a cancel button, and an
# expandable log.
# =============================================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QPlainTextEdit, QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from utils.process_runner import format_duration


class OperationProgressPanel(QFrame):
    """Live progress display for a StreamingProcessRunner."""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProgressPanel")
        self._runner = None
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick)
        self._seconds = 0
        self._log_visible = False
        self._build_ui()
        self.setVisible(False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # ---- Header: title + elapsed + cancel ----
        header = QHBoxLayout()
        header.setSpacing(8)

        self.title_label = QLabel("Working…")
        self.title_label.setObjectName("ProgressTitle")
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        header.addWidget(self.title_label)

        header.addStretch()

        self.elapsed_label = QLabel("0s")
        self.elapsed_label.setObjectName("ProgressElapsed")
        self.elapsed_label.setFont(QFont("Consolas", 9))
        header.addWidget(self.elapsed_label)

        self.btn_log = QPushButton("Details")
        self.btn_log.setObjectName("ProgressLogBtn")
        self.btn_log.setCheckable(True)
        self.btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_log.setToolTip("Show the raw operation log")
        self.btn_log.clicked.connect(self._toggle_log)
        header.addWidget(self.btn_log)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("ProgressCancelBtn")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel)
        header.addWidget(self.btn_cancel)

        layout.addLayout(header)

        # ---- Progress bar ----
        self.bar = QProgressBar()
        self.bar.setObjectName("OperationBar")
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        # ---- Status line + percent ----
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self.status_label = QLabel("Preparing…")
        self.status_label.setObjectName("ProgressStatus")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setWordWrap(False)
        status_row.addWidget(self.status_label, stretch=1)

        self.percent_label = QLabel("")
        self.percent_label.setObjectName("ProgressPercent")
        self.percent_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        status_row.addWidget(self.percent_label)

        layout.addLayout(status_row)

        # ---- Collapsible log ----
        self.log = QPlainTextEdit()
        self.log.setObjectName("ProgressLog")
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 8))
        self.log.setMaximumBlockCount(2000)
        self.log.setFixedHeight(120)
        self.log.setVisible(False)
        layout.addWidget(self.log)

    # -------------------------------------------------------------------------
    # Wiring
    # -------------------------------------------------------------------------

    def bind(self, runner):
        """Connect this panel to a StreamingProcessRunner."""
        self._runner = runner
        runner.progress.connect(self.set_progress)
        runner.status.connect(self.set_status)
        runner.output.connect(self.append_log)
        runner.finished.connect(self.finish)
        self.cancel_requested.connect(runner.cancel)

    # -------------------------------------------------------------------------
    # State
    # -------------------------------------------------------------------------

    def begin(self, title: str):
        """Show the panel and reset it for a new operation."""
        self.title_label.setText(title)
        self.status_label.setText("Preparing…")
        self.percent_label.setText("")
        self.log.clear()
        self._seconds = 0
        self.elapsed_label.setText("0s")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("Cancel")
        self.set_progress(-1)
        self.setVisible(True)
        self._elapsed_timer.start()

    def set_progress(self, percent: int):
        """percent < 0 switches the bar to an indeterminate sweep."""
        if percent is None or percent < 0:
            self.bar.setRange(0, 0)          # Qt renders a moving sweep
            self.percent_label.setText("")
        else:
            if self.bar.maximum() == 0:
                self.bar.setRange(0, 100)
            self.bar.setValue(percent)
            self.percent_label.setText(f"{percent}%")

    def set_status(self, text: str):
        metrics = self.status_label.fontMetrics()
        self.status_label.setText(
            metrics.elidedText(text, Qt.TextElideMode.ElideRight,
                               max(120, self.status_label.width()))
        )
        self.status_label.setToolTip(text)

    def append_log(self, line: str):
        self.log.appendPlainText(line)

    def finish(self, ok: bool, message: str):
        self._elapsed_timer.stop()
        self.btn_cancel.setText("Close")
        self.btn_cancel.setEnabled(True)

        if ok:
            self.bar.setRange(0, 100)
            self.bar.setValue(100)
            self.percent_label.setText("100%")
            self.title_label.setText("✅  " + self.title_label.text().lstrip("✅⚠️ ").strip())
        else:
            self.bar.setRange(0, 100)
            self.title_label.setText("⚠️  " + self.title_label.text().lstrip("✅⚠️ ").strip())

        self.set_status(message)
        self.append_log(message)
        self.setProperty("state", "ok" if ok else "error")
        self._restyle()

    def _restyle(self):
        """Re-evaluate QSS after a dynamic property change."""
        self.style().unpolish(self)
        self.style().polish(self)

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    def _tick(self):
        self._seconds += 1
        self.elapsed_label.setText(format_duration(self._seconds))

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        self.log.setVisible(self._log_visible)
        self.btn_log.setChecked(self._log_visible)

    def _on_cancel(self):
        running = self._runner is not None and self._runner.is_running()
        if running:
            self.btn_cancel.setEnabled(False)
            self.cancel_requested.emit()
        else:
            # Operation already finished — this is a "Close" press.
            self.setVisible(False)
            self.setProperty("state", "")
            self._restyle()
