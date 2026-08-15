# =============================================================================
# RootForgeKit — Asynchronous Terminal Console Widget
# QProcess-powered live terminal with real-time output streaming,
# double-layer Y/N confirmation, and Clear/Copy/Abort controls.
# =============================================================================

import platform

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt, QProcess, Signal
from PySide6.QtGui import QFont, QTextCursor, QColor

from utils.elevation import is_admin, relaunch_as_admin


class TerminalConsoleWidget(QWidget):
    """
    Embeddable async terminal console for running system commands.

    Features:
        - QProcess-backed non-blocking execution (preserves 60 FPS UI)
        - Real-time stdout/stderr streaming with retro styling
        - Double-layer protection: confirmation dialogs before any execution
        - Clear Console, Copy Logs, Abort Process toolbar

    Usage:
        terminal = TerminalConsoleWidget()
        terminal.execute_command("echo Hello", "Test echo", "low")
    """
    command_finished = Signal(int, str)  # exit_code, command_key

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._current_command_key = ""
        self._setup_ui()

    def _setup_ui(self):
        """Build the terminal console layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ---- Header / Status Bar ----
        header = QFrame()
        header.setObjectName("TerminalHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)

        self.status_label = QLabel("● Terminal Ready")
        self.status_label.setObjectName("TerminalStatus")
        self.status_label.setFont(QFont("Consolas", 9))
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()

        # ---- Toolbar Buttons ----
        self.clear_btn = QPushButton("🗑 Clear")
        self.clear_btn.setObjectName("TerminalBtn")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("Clear the console output")
        self.clear_btn.clicked.connect(self._clear_console)
        header_layout.addWidget(self.clear_btn)

        self.copy_btn = QPushButton("📋 Copy")
        self.copy_btn.setObjectName("TerminalBtn")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setToolTip("Copy all logs to clipboard")
        self.copy_btn.clicked.connect(self._copy_logs)
        header_layout.addWidget(self.copy_btn)

        self.abort_btn = QPushButton("⛔ Abort")
        self.abort_btn.setObjectName("TerminalAbortBtn")
        self.abort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.abort_btn.setToolTip("Kill the running process")
        self.abort_btn.clicked.connect(self._abort_process)
        self.abort_btn.setEnabled(False)
        header_layout.addWidget(self.abort_btn)

        layout.addWidget(header)

        # ---- Console Output Area ----
        self.console = QPlainTextEdit()
        self.console.setObjectName("TerminalConsole")
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 10))
        self.console.setMinimumHeight(60)
        self.console.setMaximumBlockCount(5000)  # Prevent unbounded memory growth
        layout.addWidget(self.console)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def execute_command(self, command: str, description: str, risk_level: str,
                        command_key: str = "", skip_confirm: bool = False,
                        requires_admin: bool = False) -> bool:
        """
        Execute a command with double-layer confirmation protection.

        Args:
            command:        The shell command string to run.
            description:    Human-readable explanation of what the command does.
            risk_level:     "low", "medium", or "high" — affects confirmation severity.
            command_key:    Optional key identifier for the command.
            skip_confirm:   If True, skip confirmation (use with caution).
            requires_admin: If True, this command cannot work unelevated —
                            offer to relaunch RootForgeKit as Administrator rather
                            than letting it fail with a cryptic access error.

        Returns:
            True if the command was actually started, False if it was refused
            at any gate (already busy, needs elevation, or user cancelled).

            Callers that change UI state *before* calling this — e.g. flipping a
            card to "Installing..." — must reset it when this returns False.
            Otherwise the card sits on a spinner forever, because
            _on_command_finished only fires for commands that really ran.
        """
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(
                self, "Process Running",
                "A command is already running. Please wait for it to finish or abort it.",
            )
            return False

        # ---- Elevation gate ----
        # RootForgeKit runs unelevated by default; only the handful of tools that
        # genuinely need Administrator ask for it, and only when clicked.
        #
        # This always stops the current call: _offer_elevation either declines,
        # or starts a *separate* elevated process that will run the command.
        # Either way this instance must not continue on to execute it.
        if requires_admin and not is_admin():
            self._offer_elevation(description)
            return False

        # ---- Layer 1: Information dialog ----
        if not skip_confirm:
            risk_icons = {"low": "ℹ️", "medium": "⚠️", "high": "🚨"}
            risk_colors = {"low": "green", "medium": "orange", "high": "red"}
            icon = risk_icons.get(risk_level, "ℹ️")
            color = risk_colors.get(risk_level, "white")

            info_text = (
                f"{icon} <b>Command Explanation</b><br><br>"
                f"<b>What:</b> {description}<br>"
                f"<b>Risk Level:</b> <span style='color:{color};'>{risk_level.upper()}</span><br><br>"
                f"<b>Command:</b><br>"
                f"<code style='color:#00e5ff;'>{command}</code><br><br>"
                f"Do you want to proceed?"
            )

            reply = QMessageBox.question(
                self, "Confirm Execution",
                info_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                self._append_output("[CANCELLED] User declined execution.\n", "#f0a500")
                return False

        # ---- Layer 2: Final confirmation for high-risk commands ----
        if risk_level == "high" and not skip_confirm:
            reply2 = QMessageBox.warning(
                self, "⚠️ High-Risk Command",
                (
                    f"<b>This is a HIGH-RISK operation.</b><br><br>"
                    f"<b>{description}</b><br><br>"
                    f"This may modify core system components or require a reboot.<br>"
                    f"Are you absolutely sure you want to continue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply2 != QMessageBox.StandardButton.Yes:
                self._append_output("[CANCELLED] High-risk execution aborted by user.\n", "#ff5252")
                return False

        # ---- Execute ----
        self._current_command_key = command_key
        self._run_command(command)
        return True

    # -------------------------------------------------------------------------
    # Elevation
    # -------------------------------------------------------------------------

    def _offer_elevation(self, description: str) -> bool:
        """
        Explain that this tool needs Administrator and offer to relaunch.

        Always returns False — even on success, because the elevated instance
        is a brand new process; this one is shutting down and must not also
        run the command.
        """
        reply = QMessageBox.question(
            self, "Administrator Required",
            (
                f"<b>{description}</b><br><br>"
                "This tool cannot run without Administrator privileges.<br><br>"
                "RootForgeKit runs unelevated so it doesn't prompt for UAC on every "
                "launch — only tools that genuinely need it, like this one, ask.<br><br>"
                "Restart RootForgeKit as Administrator now?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._append_output(
                "[BLOCKED] Skipped — this tool requires Administrator privileges.\n",
                "#f0a500",
            )
            return False

        started, message = relaunch_as_admin()
        self._append_output(f"[*] {message}\n", "#00e5ff")
        if started:
            # Hand off to the elevated instance and close this one, so two
            # copies aren't running against the same machine at once.
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
        else:
            QMessageBox.warning(self, "Elevation Failed", message)
        return False

    # -------------------------------------------------------------------------
    # Internal Process Management
    # -------------------------------------------------------------------------

    def _run_command(self, command: str):
        """Spawn a QProcess and connect output signals."""
        self._append_output(f"$ {command}\n", "#00e5ff")
        self._set_status("running")

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._handle_stdout)
        self._process.readyReadStandardError.connect(self._handle_stderr)
        self._process.finished.connect(self._handle_finished)
        self._process.errorOccurred.connect(self._handle_error)

        # Platform-appropriate shell invocation
        system = platform.system()
        if system == "Windows":
            self._process.start("cmd.exe", ["/c", command])
        else:
            self._process.start("/bin/bash", ["-c", command])

        self.abort_btn.setEnabled(True)

    def _handle_stdout(self):
        """Stream stdout data to the console."""
        if self._process:
            data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
            self._append_output(data, "#c8e6c9")

    def _handle_stderr(self):
        """Stream stderr data to the console in red."""
        if self._process:
            data = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
            self._append_output(data, "#ff8a80")

    def _handle_finished(self, exit_code, exit_status):
        """Handle process completion."""
        if exit_code == 0:
            self._append_output(f"\n[DONE] Process exited successfully (code {exit_code}).\n", "#00e676")
        else:
            self._append_output(f"\n[EXIT] Process exited with code {exit_code}.\n", "#ff5252")

        self._set_status("ready")
        self.abort_btn.setEnabled(False)
        self.command_finished.emit(exit_code, self._current_command_key)
        self._process = None

    def _handle_error(self, error):
        """Handle QProcess errors (e.g., command not found)."""
        error_messages = {
            QProcess.ProcessError.FailedToStart: "Failed to start process. Is the command available?",
            QProcess.ProcessError.Crashed: "Process crashed unexpectedly.",
            QProcess.ProcessError.Timedout: "Process timed out.",
            QProcess.ProcessError.WriteError: "Write error occurred.",
            QProcess.ProcessError.ReadError: "Read error occurred.",
            QProcess.ProcessError.UnknownError: "Unknown process error.",
        }
        msg = error_messages.get(error, "Unknown error.")
        self._append_output(f"\n[ERROR] {msg}\n", "#ff5252")
        self._set_status("error")
        self.abort_btn.setEnabled(False)

    # -------------------------------------------------------------------------
    # Toolbar Actions
    # -------------------------------------------------------------------------

    def _clear_console(self):
        """Clear all console output."""
        self.console.clear()
        self._append_output("Console cleared.\n", "#78909c")

    def _copy_logs(self):
        """Copy entire console content to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.console.toPlainText())
            self._append_output("[Copied all logs to clipboard.]\n", "#64ffda")

    def _abort_process(self):
        """Kill the running process."""
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            reply = QMessageBox.question(
                self, "Abort Process",
                "Are you sure you want to kill the running process?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._process.kill()
                self._append_output("\n[ABORTED] Process killed by user.\n", "#ff5252")
                self._set_status("aborted")
                self.abort_btn.setEnabled(False)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _append_output(self, text: str, color: str = "#e0e0e0"):
        """Append colored text to the console."""
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Use HTML for colored output
        html = f"<span style='color:{color}; white-space:pre;'>{text}</span>"
        cursor.insertHtml(html)

        # Auto-scroll to bottom
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    def _set_status(self, state: str):
        """Update the status indicator."""
        states = {
            "ready":   ("● Terminal Ready",   "#4caf50"),
            "running": ("◉ Running...",        "#ffc107"),
            "error":   ("● Error",             "#ff5252"),
            "aborted": ("● Aborted",           "#ff9800"),
        }
        text, color = states.get(state, ("● Unknown", "#9e9e9e"))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")
