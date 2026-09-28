# =============================================================================
# RootForgeKit — SecretSauce Tab
#
# Same shape as TechToolsTab / GamerToolsTab (see tabs/tool_tab_base.py): a
# scrollable stack of CollapsibleSections holding ToolCards above a live
# terminal console. Only difference is the gate — the tab refuses to render
# until the passphrase is entered.
# =============================================================================

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout,
)

from PySide6.QtWidgets import QApplication

from tabs.tool_tab_base import ToolTabBase
from utils.command_builder import ps_encoded_command
from utils.elevation import is_admin, relaunch_as_admin

# The passphrase prompt. Kept as module constants so the question and the
# answer live next to each other and are trivial to change in one place.
GATE_PROMPT = "What's the Krabby Patty Secret Formula"
GATE_PASSPHRASE = "kush"

# The tab also needs Administrator for the activation commands. The passphrase
# is the first gate; elevation is the second. Both must pass before anything
# in here is visible.


class SecretGate(QDialog):
    """
    The passphrase prompt shown when the tab is selected.

    Styled by styles.qss (#SecretGateDialog) rather than a bare QInputDialog so
    it matches the rest of the app instead of dropping a native grey box into a
    dark UI.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SecretGateDialog")
        self.setWindowTitle("🔒  Restricted")
        self.setModal(True)
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        title = QLabel("🍔  SecretSauce")
        title.setObjectName("TabSectionTitle")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        root.addWidget(title)

        # The prompt text is the joke, so give it room to breathe rather than
        # truncating it in a one-line label.
        prompt = QLabel(GATE_PROMPT)
        prompt.setObjectName("TabSubtitle")
        prompt.setWordWrap(True)
        root.addWidget(prompt)

        self.input = QLineEdit()
        self.input.setObjectName("SecretGateInput")
        self.input.setPlaceholderText("passphrase")
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.input.returnPressed.connect(self._submit)
        root.addWidget(self.input)

        self.hint = QLabel("")
        self.hint.setObjectName("TabSubtitle")
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        root.addWidget(self.hint)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._submit)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        # A wrong guess re-prompts in place (see _submit), so there is no
        # attempt counter to thread through here.
        self.input.setFocus()

    def _submit(self) -> None:
        if self.input.text().strip().lower() == GATE_PASSPHRASE:
            self.accept()
        else:
            self.input.clear()
            self.hint.setText("That's not the formula. Try again.")
            self.hint.setVisible(True)
            self.input.setFocus()


class SecretSauceTab(ToolTabBase):
    """Licensing diagnostics behind the passphrase gate."""

    def __init__(self, parent=None):
        super().__init__(
            title="🍔  SecretSauce",
            subtitle="Licensing diagnostics and edition activation. "
                      "Requires the passphrase and Administrator privileges.",
            console_label="📟  Sauce Console",
            parent=parent,
        )
        self._build()
        self.finish_sections()

    def _build(self) -> None:
        # ---- Licensing state -----------------------------------------
        section = self.add_section("🔑  Licensing State", expanded=True)

        self.add_raw_card(
            section, "licence_status",
            "🔍", "License Status (read-only)",
            "Query the local licensing store for what Windows actually thinks "
            "it is licensed as, and whether that license is activated.",
            ps_encoded_command(
                "Get-CimInstance SoftwareLicensingProduct | "
                "Where-Object { $_.PartialProductKey -and $_.Name -notlike '*Genuine*' } | "
                "Select-Object Name, Description, LicenseStatus, "
                "GracePeriodRemaining | Format-List"
            ),
            risk="low",
        )

        self.add_raw_card(
            section, "licence_dlv",
            "📜", "Detailed License Report",
            "The full slmgr /dlv dump — channel, partial key, expiry and "
            "notification state.",
            "slmgr /dlv",
            risk="low",
        )

        self.add_raw_card(
            section, "licence_oem",
            "🏷️", "Installed OEM Key",
            "The firmware-embedded OEM key, if the manufacturer supplied one.",
            "slmgr /oem",
            risk="low",
        )

        # ---- Activation settings --------------------------------------
        section = self.add_section("⚙️  Activation Settings")

        self.add_raw_card(
            section, "open_activation",
            "🔧", "Open Activation Settings",
            "Windows' own activation page — change key, troubleshoot, or "
            "buy a genuine license.",
            "start ms-settings:activation",
            risk="low",
            skip_confirm=True,
        )

        self.add_raw_card(
            section, "open_activation_troubleshoot",
            "🩺", "Activation Troubleshooter",
            "Run Microsoft's built-in activation troubleshooter.",
            "start ms-settings:activationtroubleshoot",
            risk="low",
            skip_confirm=True,
        )

        # ---- Edition activation --------------------------------------
        section = self.add_section("🔑  Edition Activation", expanded=True)

        self.add_raw_card(
            section, "activate_pro",
            "🟦", "Activate Pro Edition",
            "KMS activation for Windows Pro. Requires elevation.",
            "slmgr /upk && slmgr /ipk W269N-WFGWX-YVC9B-4J6C9-T83GX && "
            "slmgr /skms kms8.msguides.com && slmgr /ato",
            risk="high",
        )

        self.add_raw_card(
            section, "activate_enterprise",
            "🟪", "Activate Enterprise Edition",
            "KMS activation for Windows Enterprise. Requires elevation.",
            "slmgr.vbs /upk && slmgr /ipk NPPR9-FWDCX-D2C8J-H872K-2YT43 && "
            "slmgr /skms kms8.msguides.com && slmgr /ato",
            risk="high",
        )

        self.add_raw_card(
            section, "set_server_standard",
            "🔄", "Set Edition to Server Standard",
            "Changes the reported Windows edition via DISM. Requires "
            "elevation and the correct product key.",
            "dism /online /Set-Edition:ServerStandard /ProductKey:"
            "W269N-WFGWX-YVC9B-4J6C9-T83GX /AcceptEula",
            risk="high",
        )

        # ---- Diagnostics ----------------------------------------------
        section = self.add_section("🧬  Machine Fingerprint")
        self.add_command_card(
            section, "disk_health", "💽", "Drive Health",
            "Because if you are going to read a licence out loud you may as "
            "well know the disk is honest.",
        )
        self.add_command_card(
            section, "process_list", "⚡", "Process Priority",
            "Top CPU consumers. The sauce is expensive.",
        )

        # ---- Hide & Disable -------------------------------------------
        section = self.add_section("🚫  Hide & Disable", expanded=True)
        self.add_command_card(
            section, "disable_cortana", "🤖", "Disable Cortana",
            "Cortana and web search in the Start menu. Requires elevation.",
        )
        self.add_raw_card(
            section, "remove_dopilot", "🤖", "Remove DPilot",
            "Windows 11 DPilot overlay assistant. Elevated.",
            "REG ADD \"HKLM\\SOFTWARE\\Policies\\Microsoft\\"
            "Windows\\WindowsCopilot\" /v TurnOffWindowsCopilot /t "
            "REG_DWORD /d 1 /f",
            risk="medium",
        )
        self.add_raw_card(
            section, "god_mode", "👑", "Enable God Mode",
            "Creates a GodMode folder on the desktop with all system "
            "settings.",
            "mkdir \"%USERPROFILE%\\Desktop\\GodMode."
            "{ED7BA470-8E54-465E-825C-9931E9D1D5C7}\"",
            risk="low",
            skip_confirm=True,
        )


class SecretGatekeeper:
    """
    Gates a tab behind the passphrase prompt.

    Attach after the tab has been added to the QTabWidget:

        gate = SecretGatekeeper(main_window.tabs, secret_index)

    Selecting the gated tab without the passphrase bounces the user straight
    back to wherever they were, and a `currentChanged` signal raised by that
    bounce is ignored so the gate cannot recurse.
    """

    def __init__(self, tab_widget, index: int):
        self.tabs = tab_widget
        self.index = index
        self.unlocked = False
        self._fallback = 0
        self._busy = False
        self.tabs.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, current: int) -> None:
        if self._busy or self.unlocked or current != self.index:
            return

        self._busy = True
        try:
            dialog = SecretGate(self.tabs)
            try:
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    self.unlocked = True
            finally:
                dialog.deleteLater()
            if not self.unlocked:
                # Wrong answer or cancelled — return to the previous tab.
                self.tabs.setCurrentIndex(self._fallback)
                return

            # The passphrase passed. The activation commands inside this
            # tab need Administrator, so elevate before showing anything.
            if not is_admin():
                started, message = relaunch_as_admin("--secret-sauce")
                if started:
                    # Hand off to the elevated instance and close this
                    # one. The elevated instance will unlock the tab
                    # via --secret-sauce on startup.
                    QApplication.quit()
                else:
                    # Elevation was declined or failed — keep the tab
                    # locked so the content stays hidden.
                    self.unlocked = False
                    self.tabs.setCurrentIndex(self._fallback)
        finally:
            self._busy = False

    def unlock_elevated(self) -> None:
        """Unlock the tab after the elevated instance starts.

        Called by main.py when it detects --secret-sauce in argv —
        the app was relaunched as Administrator for this tab.
        """
        self.unlocked = True
        self.tabs.setCurrentIndex(self.index)

    def lock(self) -> None:
        """Re-arm the gate, e.g. when the tab is hidden."""
        self.unlocked = False

    def remember_fallback(self, index: int) -> None:
        """Note which tab to bounce back to. Defaults to the first one."""
        if index != self.index:
            self._fallback = index
