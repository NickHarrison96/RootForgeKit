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
