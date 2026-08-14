# =============================================================================
# NicksFix — Cross-Platform Command Builder
# Maps logical tool/install keys to native OS package manager commands.
# Supports: winget/DISM (Windows), brew (macOS), apt (Linux).
# =============================================================================

import platform


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
                "process_list": (
                    "tasklist /v /fo csv | findstr /i \"cpu\"",
                    "List running processes with verbose detail",
                    "low",
                ),
            }

        elif self.os_type == "Darwin":
            return {
                "wsl2": (
                    "echo 'WSL2 is a Windows-only feature. Not applicable on macOS.'",
                    "WSL2 is not available on macOS",
                    "low",
                ),
                "vcredist": (
                    "echo 'Visual C++ Redistributable is a Windows-only component.'",
                    "VC++ Redist is not applicable on macOS",
                    "low",
                ),
                "dotnet": (
                    "brew install --cask dotnet-sdk",
                    "Install .NET SDK via Homebrew",
                    "medium",
                ),
                "system_update": (
                    "brew update && brew upgrade",
                    "Update and upgrade all Homebrew packages",
                    "medium",
                ),
                "directx": (
                    "echo 'DirectX is a Windows-only technology.'",
                    "DirectX is not available on macOS",
                    "low",
                ),
                "disk_health": (
                    "diskutil list && diskutil info /",
                    "List disks and show root volume info",
                    "low",
                ),
                "network_diag": (
                    "ifconfig && netstat -an | grep LISTEN",
                    "Display network interfaces and listening ports",
                    "low",
                ),
                "flush_dns": (
                    "sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder",
                    "Flush macOS DNS cache",
                    "medium",
                ),
                "temp_clean": (
                    "rm -rf ~/Library/Caches/* /tmp/* 2>/dev/null; echo 'Cache cleanup complete.'",
                    "Clear user and system cache files",
                    "medium",
                ),
                "sfc_scan": (
                    "echo 'SFC is a Windows-only tool. Use Disk Utility on macOS.'",
                    "System File Checker is not available on macOS",
                    "low",
                ),
                "gpu_info": (
                    "system_profiler SPDisplaysDataType",
                    "Display GPU/Display adapter information",
                    "low",
                ),
                "process_list": (
                    "ps aux --sort=-%cpu | head -20",
                    "List top 20 CPU-consuming processes",
                    "low",
                ),
            }

        else:  # Linux
            return {
                "wsl2": (
                    "echo 'WSL2 is a Windows-only feature. Not applicable on Linux.'",
                    "WSL2 is not available on Linux",
                    "low",
                ),
                "vcredist": (
                    "echo 'Visual C++ Redistributable is a Windows-only component.'",
                    "VC++ Redist is not applicable on Linux",
                    "low",
                ),
                "dotnet": (
                    "sudo apt-get update && sudo apt-get install -y dotnet-runtime-8.0",
                    "Install .NET 8 Runtime via apt",
                    "medium",
                ),
                "system_update": (
                    "sudo apt-get update && sudo apt-get upgrade -y",
                    "Update package lists and upgrade all packages",
                    "medium",
                ),
                "directx": (
                    "echo 'DirectX is a Windows-only technology. Consider Vulkan/Mesa on Linux.'",
                    "DirectX is not available on Linux",
                    "low",
                ),
                "disk_health": (
                    "lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT && sudo smartctl -a /dev/sda 2>/dev/null || echo 'smartctl not available'",
                    "List block devices and check SMART health",
                    "low",
                ),
                "network_diag": (
                    "ip addr && ss -tulnp",
                    "Display network interfaces and listening sockets",
                    "low",
                ),
                "flush_dns": (
                    "sudo systemd-resolve --flush-caches 2>/dev/null || sudo resolvectl flush-caches 2>/dev/null; echo 'DNS cache flushed.'",
                    "Flush systemd-resolved DNS cache",
                    "low",
                ),
                "temp_clean": (
                    "sudo rm -rf /tmp/* /var/tmp/* 2>/dev/null; echo 'Temp directories cleaned.'",
                    "Clear temporary file directories",
                    "medium",
                ),
                "sfc_scan": (
                    "sudo apt-get install -f && sudo dpkg --configure -a",
                    "Repair broken packages and reconfigure dpkg",
                    "high",
                ),
                "gpu_info": (
                    "lspci | grep -iE 'vga|3d|display'",
                    "List PCI GPU/display devices",
                    "low",
                ),
                "process_list": (
                    "ps aux --sort=-%cpu | head -20",
                    "List top 20 CPU-consuming processes",
                    "low",
                ),
            }

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
