# =============================================================================
# RootForgeKit — Batch Package & Preset Profile Installer
# Automated silent batch package installation via winget (Windows) or brew (macOS)
# =============================================================================

import platform

from PySide6.QtCore import QThread, Signal

from utils.resource_manager import safe_run_command

PRESET_PROFILES = {
    "gaming_essentials": {
        "name": "🎮 Gamer Essentials Profile",
        "description": "DirectX, VC++ Runtimes, Discord, Steam, 7-Zip, MSI Afterburner",
        "windows_packages": [
            "Microsoft.VCRedist.2015+.x64",
            "Microsoft.DirectX",
            "Discord.Discord",
            "Valve.Steam",
            "7zip.7zip",
            "Guru3D.MSIAfterburner"
        ],
        "darwin_packages": [
            "discord",
            "steam",
            "keka"
        ]
    },
    "tech_utilities": {
        "name": "🛠 Tech & Diagnostic Utilities",
        "description": "7-Zip, Notepad++, Wireshark, VS Code, Git, Python 3.12, Process Hacker",
        "windows_packages": [
            "7zip.7zip",
            "Notepad++.Notepad++",
            "WiresharkFoundation.Wireshark",
            "Microsoft.VisualStudioCode",
            "Git.Git",
            "Python.Python.3.12"
        ],
        "darwin_packages": [
            "visual-studio-code",
            "wireshark",
            "git",
            "python@3.12"
        ]
    }
}


class BatchPackageInstaller:
    """
    Automated silent batch installer for software preset profiles.
    Uses winget on Windows and brew on macOS.
    """

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda msg: print(msg))
        self.host_os = platform.system().lower()

    def install_profile(self, profile_key: str) -> bool:
        if profile_key not in PRESET_PROFILES:
            self.log(f"[-] Unknown profile key: {profile_key}")
            return False

        profile = PRESET_PROFILES[profile_key]
        self.log(f"\n🚀 Starting batch installation for '{profile['name']}'...")

        if self.host_os == "windows":
            packages = profile["windows_packages"]
            return self._install_winget_packages(packages)
        elif self.host_os == "darwin":
            packages = profile["darwin_packages"]
            return self._install_brew_packages(packages)
        else:
            self.log(f"[-] Linux batch installation requires native apt/dnf scripts.")
            return False

    def _install_winget_packages(self, packages: list[str]) -> bool:
        success_count = 0
        for pkg in packages:
            self.log(f"[*] Installing package via winget: {pkg}...")
            cmd = ["winget", "install", "--id", pkg, "-e", "--accept-package-agreements", "--accept-source-agreements", "--silent"]
            ok, out = safe_run_command(cmd, timeout=120)
            if ok:
                self.log(f"[+] Successfully installed {pkg}")
                success_count += 1
            else:
                self.log(f"[-] Failed to install {pkg}: {out}")

        self.log(f"\n[+] Batch Installation Complete: {success_count}/{len(packages)} succeeded.")
        return success_count == len(packages)

    def _install_brew_packages(self, packages: list[str]) -> bool:
        success_count = 0
        for pkg in packages:
            self.log(f"[*] Installing package via brew: {pkg}...")
            cmd = ["brew", "install", pkg]
            ok, out = safe_run_command(cmd, timeout=120)
            if ok:
                self.log(f"[+] Successfully installed {pkg}")
                success_count += 1
            else:
                self.log(f"[-] Failed to install {pkg}: {out}")

        self.log(f"\n[+] Batch Installation Complete: {success_count}/{len(packages)} succeeded.")
        return success_count == len(packages)


class BatchInstallWorker(QThread):
    """
    Runs BatchPackageInstaller.install_profile() off the UI thread.

    Each package install can legitimately take minutes (first-time downloads
    of VS Code, Wireshark, etc.), and a profile chains several of them —
    calling install_profile() directly from a button's clicked handler blocks
    the whole Qt event loop for the entire run, freezing the app. log_line
    carries terminal output back to the UI thread instead of the installer
    touching a widget directly from a worker thread, which Qt doesn't allow.
    """
    log_line = Signal(str)
    finished_profile = Signal(bool)

    def __init__(self, profile_key: str, parent=None):
        super().__init__(parent)
        self.profile_key = profile_key

    def run(self):
        installer = BatchPackageInstaller(log_callback=self.log_line.emit)
        success = installer.install_profile(self.profile_key)
        self.finished_profile.emit(success)
