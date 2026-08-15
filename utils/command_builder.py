# =============================================================================
# NicksFix — Cross-Platform Command Builder
# Maps logical tool/install keys to native OS package manager commands.
# Supports: winget/DISM (Windows), brew (macOS), apt (Linux).
# =============================================================================

import base64
import platform


def ps_encoded_command(script: str) -> str:
    """
    Build a `powershell -EncodedCommand <base64>` invocation string.

    Plain `powershell -Command "..."` breaks once the whole command string
    gets wrapped *again* by `cmd.exe /c "..."` -- which is how every tool
    command actually gets run (see components/terminal_widget.py's
    _run_command). The nested double quotes around -Command's argument
    collide with cmd.exe's own quote-stripping for /c: confirmed via a
    direct QProcess reproduction that several commands were returning exit
    code 0 while the "output" was just the literal command text echoed back
    -- PowerShell never actually ran it. Base64-encoding sidesteps quoting
    entirely; there's nothing left for cmd.exe to misinterpret.

    $ProgressPreference is silenced because some cmdlets (e.g.
    Get-CimInstance) emit progress-stream records that get serialized as
    CLIXML noise mixed into stdout when run non-interactively like this.
    """
    full_script = f"$ProgressPreference = 'SilentlyContinue'; {script}"
    encoded = base64.b64encode(full_script.encode("utf-16-le")).decode("ascii")
    return f"powershell -NoProfile -EncodedCommand {encoded}"


# Command keys that genuinely require Administrator. NicksFix launches
# unelevated (see utils/elevation.py), so these are the only ones that
# trigger a UAC prompt, and only when the user actually clicks them.
#
# Everything NOT in this set was confirmed working unelevated by running it
# from a non-admin process: disk_health, network_diag, flush_dns, gpu_info,
# process_list and the Gamer Tools bonus commands all returned real output
# with exit code 0. Don't add entries here on a hunch — verify first, or the
# app starts demanding elevation it doesn't need, which is the exact problem
# this replaced.
ADMIN_REQUIRED_KEYS = {
    "sfc_scan",             # sfc /scannow — refuses to run unelevated
    "wsl2",                 # dism /online /enable-feature — modifies OS features
    "vcredist",             # winget machine-scope install
    "dotnet",               # winget machine-scope install
    "directx",              # winget machine-scope install
    "system_update",        # winget upgrade --all — machine-scope packages
    "activate_enterprise",  # slmgr /ipk|/ato — Windows licensing store
    "activate_pro",         # slmgr /ipk|/ato — Windows licensing store
    "dism_server_standard", # dism /online /Set-Edition — verified error 740 unelevated
}


def requires_admin(command_key: str) -> bool:
    """True if this command key needs an elevated process to work."""
    return command_key in ADMIN_REQUIRED_KEYS


class CommandBuilder:
    """
    Resolves platform-specific commands for system tool installations.

    Each command entry is a tuple of:
        (command_string, human_description, risk_level)

    Risk levels: "low", "medium", "high"
        - low:    read-only or non-destructive
        - medium: installs/modifies system packages
        - high:   modifies OS features, kernel settings, or requires reboot

    Usage:
        builder = CommandBuilder()
        cmd, desc, risk = builder.get("wsl2")
    """

    def __init__(self, os_type: str | None = None):
        # os_type lets callers target a non-host platform ("Windows"/"Darwin"/"Linux")
        self.os_type = os_type or platform.system()
        self._registry = self._build_registry()

    def _build_registry(self) -> dict[str, tuple[str, str, str]]:
        """Build the command registry for the detected OS."""

        if self.os_type == "Windows":
            return {
                # ---- Windows Subsystem for Linux ----
                "wsl2": (
                    'dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart && '
                    'dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart',
                    "Enable WSL2 and Virtual Machine Platform via DISM",
                    "high",
                ),
                # ---- MSYS2 (Unix shell + GCC toolchain + pacman) ----
                # Package ID confirmed via `winget search msys2` -- MSYS2.MSYS2.
                "msys2": (
                    "winget install MSYS2.MSYS2 --accept-source-agreements --accept-package-agreements",
                    "Install MSYS2 (Unix-like shell, GCC toolchain, pacman package manager)",
                    "medium",
                ),
                # ---- Zadig (USB driver installer GUI) ----
                # Package ID confirmed via `winget search zadig` -- akeo.ie.Zadig
                # (publisher: github.com/pbatard, the actual Zadig author).
                # Zadig is how WinUSB gets attached to a device -- WinUSB itself
                # ships built into Windows already (winusb.sys is an inbox
                # driver) and has no installable package of its own, so there
                # is no separate "winusb" entry here; explained in the
                # description instead of shipping a command that can't exist.
                "zadig": (
                    "winget install akeo.ie.Zadig --accept-source-agreements --accept-package-agreements",
                    "Install Zadig — binds WinUSB, libusb-win32, or libusbK to a USB device "
                    "(WinUSB itself ships built into Windows; Zadig is how you attach it to a "
                    "specific device, e.g. for DFU/bootloader-mode flashing)",
                    "medium",
                ),
                # ---- libusbK (USB driver framework/library) ----
                # Package ID confirmed via `winget search libusb` -- mcuee.libusbK.
                "libusbk": (
                    "winget install mcuee.libusbK --accept-source-agreements --accept-package-agreements",
                    "Install libusbK — USB driver framework used by libusb-based flashing/"
                    "diagnostic tools; this is the driver package Zadig can bind to a device",
                    "medium",
                ),
                # ---- Visual C++ Redistributable ----
                "vcredist": (
                    "winget install Microsoft.VCRedist.2015+.x64 --accept-source-agreements --accept-package-agreements",
                    "Install Visual C++ 2015-2022 Redistributable (x64)",
                    "medium",
                ),
                # ---- .NET Runtime ----
                "dotnet": (
                    "winget install Microsoft.DotNet.DesktopRuntime.8 --accept-source-agreements --accept-package-agreements",
                    "Install .NET 8 Desktop Runtime",
                    "medium",
                ),
                # ---- System Update ----
                "system_update": (
                    "winget upgrade --all --accept-source-agreements --accept-package-agreements",
                    "Upgrade all installed packages via winget",
                    "medium",
                ),
                # ---- DirectX ----
                "directx": (
                    "winget install Microsoft.DirectX --accept-source-agreements --accept-package-agreements",
                    "Install/update DirectX End-User Runtime",
                    "medium",
                ),
                # ---- Disk Health Check ----
                "disk_health": (
                    "wmic diskdrive get Status,Model,Size",
                    "Query disk drive health status via WMI",
                    "low",
                ),
                # ---- Network Diagnostics ----
                "network_diag": (
                    "ipconfig /all && netstat -an | findstr LISTENING",
                    "Display network configuration and listening ports",
                    "low",
                ),
                # ---- Flush DNS ----
                "flush_dns": (
                    "ipconfig /flushdns",
                    "Flush the DNS resolver cache",
                    "low",
                ),
                # ---- Temp File Cleanup ----
                "temp_clean": (
                    "del /q/f/s %TEMP%\\* 2>nul",
                    "Delete temporary files from user TEMP directory",
                    "medium",
                ),
                # ---- System File Checker ----
                "sfc_scan": (
                    "sfc /scannow",
                    "Run System File Checker to repair protected system files",
                    "high",
                ),
                # ---- GPU Info ----
                "gpu_info": (
                    "wmic path win32_videocontroller get Name,DriverVersion,AdapterRAM,Status",
                    "Query GPU adapter details via WMI",
                    "low",
                ),
                # ---- Process List ----
                # Was `tasklist /v /fo csv | findstr /i "cpu"` -- findstr
                # matched zero lines against tasklist's actual CSV output,
                # so this always exited 1 with no output at all. Confirmed
                # via direct reproduction, replaced with a real working
                # PowerShell equivalent.
                "process_list": (
                    ps_encoded_command(
                        "Get-Process | Sort-Object CPU -Descending | "
                        "Select-Object -First 20 Name,Id,CPU,WorkingSet | Format-Table -AutoSize"
                    ),
                    "List top 20 CPU-consuming processes",
                    "low",
                ),
                # ---- Windows Enterprise Activation ----
                "activate_enterprise": (
                    "slmgr /upk && slmgr /ipk NPPR9-FWDCX-D2C8J-H872K-2YT43 && slmgr /skms kms8.msguides.com && slmgr /ato",
                    "Activate Windows Enterprise via KMS server (kms8.msguides.com)",
                    "high",
                ),
                # ---- Windows Pro Activation ----
                "activate_pro": (
                    "slmgr /upk && slmgr /ipk W269N-WFGWX-YVC9B-4J6C9-T83GX && slmgr /skms kms8.msguides.com && slmgr /ato",
                    "Activate Windows Pro Edition via KMS server (kms8.msguides.com)",
                    "high",
                ),
                # ---- DISM Server Standard Edition ----
                "dism_server_standard": (
                    "dism /online /Set-Edition:ServerStandard /ProductKey:W269N-WFGWX-YVC9B-4J6C9-T83GX /AcceptEula",
                    "Set Windows edition to ServerStandard via DISM",
                    "high",
                ),
            }

        # macOS and Linux registries were previously filled with guessed
        # command equivalents that were never actually run or tested on
        # either platform (all testing happened on Windows — see README
        # "Project status"). Rather than ship untested guesses as if they
        # were verified tools, start these empty and build them out for
        # real, one tool at a time, once there's a way to test them.
        return {}

    def get(self, key: str) -> tuple[str, str, str]:
        """
        Retrieve a command tuple by key.

        Returns:
            (command_string, description, risk_level)

        Raises:
            KeyError if the key is not registered.
        """
        if key not in self._registry:
            raise KeyError(f"Unknown command key: '{key}'. Available: {list(self._registry.keys())}")
        return self._registry[key]

    def list_keys(self) -> list[str]:
        """Return all registered command keys for the current OS."""
        return list(self._registry.keys())

    def get_os_display_name(self) -> str:
        """Human-friendly OS name."""
        names = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}
        return names.get(self.os_type, self.os_type)

    def get_all(self) -> dict[str, tuple[str, str, str]]:
        """Return the full command registry."""
        return dict(self._registry)
