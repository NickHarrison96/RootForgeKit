import platform
import sys
import os
import time

try:
    import psutil
except ImportError:
    psutil = None

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
        if days > 0: parts.append(f"{days}d")
        if hours > 0: parts.append(f"{hours}h")
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

def get_cpu_info() -> str:
    try:
        cpu_name = platform.processor() or platform.machine()
        cores = psutil.cpu_count(logical=True) if psutil else None
        core_str = f" ({cores} cores)" if cores else ""
        return f"{cpu_name}{core_str}"
    except Exception:
        return "Unknown CPU"

def get_system_summary() -> dict:
    try:
        user = os.getlogin()
    except Exception:
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
    
    hostname = platform.node() or "localhost"
    os_name = f"{platform.system()} {platform.release()}"
    if platform.system() == "Darwin":
        os_name = f"macOS {platform.mac_ver()[0]}"
    elif platform.system() == "Linux":
        try:
            os_name = platform.freedesktop_os_release().get("PRETTY_NAME", os_name)
        except AttributeError:
            pass

    return {
        "user_host": f"{user}@{hostname}",
        "OS": os_name,
        "Kernel": f"{platform.system()} {platform.version().split()[0]}",
        "Uptime": get_formatted_uptime(),
        "Shell": os.environ.get("SHELL") or os.environ.get("COMSPEC") or "Unknown",
        "Python": f"{sys.version.split()[0]}",
        "CPU": get_cpu_info(),
        "Memory": get_memory_info(),
    }
