# =============================================================================
# RootForgeKit — Neofetch-Level Comprehensive System Telemetry Collector
# =============================================================================

import os
import sys
import platform
import time
import ctypes

try:
    import psutil
except ImportError:
    psutil = None

from utils import windows_hw


def get_formatted_uptime() -> str:
    if not psutil:
        return "Unknown"
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        hours, remainder = divmod(int(uptime_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)
    except Exception:
        return "Unknown"


def get_memory_info() -> str:
    if not psutil:
        return "Unknown"
    try:
        mem = psutil.virtual_memory()
        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        return f"{used_gb:.2f} GiB / {total_gb:.2f} GiB ({mem.percent}%)"
    except Exception:
        return "Unknown"


def get_swap_info() -> str:
    if not psutil:
        return "—"
    try:
        swap = psutil.swap_memory()
        used_gb = swap.used / (1024 ** 3)
        total_gb = swap.total / (1024 ** 3)
        return f"{used_gb:.2f} GiB / {total_gb:.2f} GiB ({swap.percent}%)"
    except Exception:
        return "—"


def get_cpu_info() -> str:
    # On Windows, read marketing name from registry
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
                if name:
                    cores = psutil.cpu_count(logical=True) if psutil else None
                    core_str = f" ({cores} threads)" if cores else ""
                    return f"{name}{core_str}"
        except Exception:
            pass

    try:
        cpu_name = platform.processor() or platform.machine()
        cores = psutil.cpu_count(logical=True) if psutil else None
        core_str = f" ({cores} threads)" if cores else ""
        return f"{cpu_name}{core_str}"
    except Exception:
        return "Unknown CPU"


def get_os_details() -> str:
    """Full detailed OS name, edition, and build version."""
    if platform.system() == "Windows":
        # The 10-vs-11 split is taken from CurrentBuildNumber rather than
        # ProductName, which Microsoft has left reading "Windows 10 ..." on
        # Windows 11 machines, and rather than CurrentMajorVersionNumber, which
        # is 10 on Windows 11 regardless. Build number is the authority.
        label = windows_hw.windows_version_label()
        if label:
            return label
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                pname = winreg.QueryValueEx(key, "ProductName")[0]
                dver = ""
                try:
                    dver = winreg.QueryValueEx(key, "DisplayVersion")[0]
                except Exception:
                    pass
                build = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
                ubr = ""
                try:
                    ubr = winreg.QueryValueEx(key, "UBR")[0]
                except Exception:
                    pass
                build_str = f"Build {build}.{ubr}" if ubr else f"Build {build}"
                return f"{pname} {dver} ({build_str})".replace("  ", " ")
        except Exception:
            pass
        return f"Windows {platform.release()} ({platform.version()})"
    elif platform.system() == "Darwin":
        return f"macOS {platform.mac_ver()[0]} ({platform.machine()})"
    elif platform.system() == "Linux":
        try:
            return platform.freedesktop_os_release().get("PRETTY_NAME", f"Linux {platform.release()}")
        except Exception:
            return f"Linux {platform.release()}"
    return f"{platform.system()} {platform.release()}"


def get_host_hardware() -> str:
    """Motherboard / Host model info."""
    if platform.system() == "Windows":
        label = windows_hw.baseboard_label()
        if label:
            return label
    return platform.node() or "PC"


def get_display_resolution() -> str:
    """Screen resolution in physical pixels."""
    if platform.system() == "Windows":
        size = windows_hw.display_resolution()
        if size:
            w, h = size
            monitors = windows_hw.display_count()
            mon_str = f" ({monitors} displays)" if monitors > 1 else ""
            return f"{w}x{h}{mon_str}"
    try:
        user32 = ctypes.windll.user32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        monitors = user32.GetSystemMetrics(80)  # SM_CMONITORS
        mon_str = f" ({monitors} displays)" if monitors > 1 else ""
        return f"{w}x{h}{mon_str}"
    except Exception:
        return "Unknown"


def get_theme_info() -> str:
    """System theme mode."""
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                apps_dark = winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
                return "Windows Dark Mode" if apps_dark else "Windows Light Mode"
        except Exception:
            pass
    return "Dark Mode"


def get_primary_gpu() -> str:
    """Quick lookup for primary GPU name."""
    if platform.system() == "Windows":
        # Was reading `Control\Class\{4d36e968-...}\0000` directly, which is
        # simply the first display-class key that exists -- not the primary
        # adapter. That directory keeps driver entries for hardware that has
        # been removed, so on a machine that had ever had an NVIDIA card this
        # reported the NVIDIA card indefinitely after it was uninstalled, and
        # on a hybrid laptop it reported whichever adapter enumerated first.
        # Presence now comes from CIM, with the registry used only for VRAM.
        gpu = windows_hw.primary_gpu()
        if gpu:
            return gpu["name"]
    return "Unknown GPU"


def get_primary_disk() -> str:
    """Primary system disk usage."""
    if not psutil:
        return "—"
    try:
        root = "C:\\" if platform.system() == "Windows" else "/"
        usage = psutil.disk_usage(root)
        used_gb = usage.used / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        return f"{root} {used_gb:.1f}/{total_gb:.1f} GiB ({usage.percent}%)"
    except Exception:
        return "—"


def get_primary_ip() -> str:
    """Primary local network IP."""
    if not psutil:
        return "—"
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for iface, if_addrs in addrs.items():
            if iface in stats and stats[iface].isup:
                for addr in if_addrs:
                    if addr.family.name == "AF_INET" and not addr.address.startswith("127."):
                        return f"{addr.address} ({iface})"
    except Exception:
        pass
    return "—"


def get_system_summary() -> dict:
    """
    Returns full Neofetch-level system identity and hardware summary.
    """
    try:
        user = os.getlogin()
    except Exception:
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"

    hostname = platform.node() or "localhost"
    shell = os.environ.get("SHELL") or os.environ.get("COMSPEC") or "cmd.exe"
    shell_name = os.path.basename(shell)

    tz = time.tzname[0] if time.tzname else "UTC"

    return {
        "user_host": f"{user}@{hostname}",
        "OS": get_os_details(),
        "Host": get_host_hardware(),
        "Kernel": f"{platform.system()} {platform.version()}",
        "Uptime": get_formatted_uptime(),
        "Resolution": get_display_resolution(),
        "Theme": get_theme_info(),
        "Shell": f"{shell_name} ({shell})",
        "Terminal": "RootForgeKit Suite Console",
        "CPU": get_cpu_info(),
        "GPU": get_primary_gpu(),
        "Memory": get_memory_info(),
        "Swap": get_swap_info(),
        "Disk": get_primary_disk(),
        "Local IP": get_primary_ip(),
        "Python": f"{sys.version.split()[0]} ({platform.architecture()[0]})",
        "Timezone": tz,
    }
