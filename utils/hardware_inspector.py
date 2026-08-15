# =============================================================================
# RootForgeKit — Hardware Telemetry & Health Inspector
# Extracts battery, disk partitions, and SMART status via PowerShell/psutil
# =============================================================================

import os
import json
import platform

try:
    import psutil
except ImportError:
    psutil = None

from utils.resource_manager import safe_run_command


def get_battery_telemetry() -> dict:
    """Extract battery status, percentage, power plugged state, and estimated time."""
    if not psutil:
        return {"available": False, "percent": 0, "plugged": False, "time_left": "N/A", "status": "psutil missing"}

    try:
        batt = psutil.sensors_battery()
        if not batt:
            return {"available": False, "percent": 0, "plugged": True, "time_left": "Desktop (AC Power)", "status": "No Battery Detected"}

        percent = round(batt.percent, 1)
        plugged = batt.power_plugged
        secs = batt.secsleft

        if secs == psutil.POWER_TIME_UNLIMITED or secs < 0:
            time_str = "AC Power / Fully Charged" if plugged else "Calculating..."
        else:
            mins = secs // 60
            hrs, mins = divmod(mins, 60)
            time_str = f"{hrs}h {mins}m remaining"

        status_str = "Charging" if plugged and percent < 100 else ("Fully Charged" if plugged else "Discharging")

        return {
            "available": True,
            "percent": percent,
            "plugged": plugged,
            "time_left": time_str,
            "status": status_str
        }
    except Exception as e:
        return {"available": False, "percent": 0, "plugged": False, "time_left": "Error", "status": str(e)}


def get_disk_health_metrics() -> list[dict]:
    """Iterate disk partitions and return mountpoint, fstype, total, used, free, percent."""
    disks = []
    if not psutil:
        return disks

    try:
        partitions = psutil.disk_partitions(all=False)
        for part in partitions:
            # Ignore optical or loop drives if unreadable
            if 'cdrom' in part.opts or part.fstype == '':
                continue

            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_gb = round(usage.total / (1024 ** 3), 1)
                used_gb = round(usage.used / (1024 ** 3), 1)
                free_gb = round(usage.free / (1024 ** 3), 1)
                percent = usage.percent

                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype or "NTFS/FAT",
                    "total_gb": total_gb,
                    "used_gb": used_gb,
                    "free_gb": free_gb,
                    "percent": percent
                })
            except Exception:
                continue
    except Exception:
        pass

    return disks


def query_smart_data_windows() -> list[dict]:
    """
    Run PowerShell 'Get-PhysicalDisk' to extract hardware SMART status,
    operational status, media type (SSD/HDD), model name, and size.
    """
    if platform.system().lower() != "windows":
        return [{"device_id": "N/A", "model": "Non-Windows OS", "status": "SMART PowerShell query requires Windows", "health": "N/A"}]

    ps_cmd = [
        "powershell", "-NoProfile", "-Command",
        "Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, OperationalStatus, HealthStatus, MediaType, Size | ConvertTo-Json"
    ]

    ok, out = safe_run_command(ps_cmd, timeout=8)
    if not ok or not out:
        return [{"device_id": "0", "model": "Unknown Drive", "status": "PowerShell SMART Query Failed", "health": "Warning"}]

    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]

        results = []
        for disk in data:
            size_raw = disk.get("Size", 0) or 0
            size_gb = round(size_raw / (1024 ** 3), 1) if size_raw else 0
            results.append({
                "device_id": str(disk.get("DeviceId", "0")),
                "model": disk.get("FriendlyName", "Generic Storage"),
                "media_type": disk.get("MediaType", "Unspecified"),
                "status": str(disk.get("OperationalStatus", "OK")),
                "health": str(disk.get("HealthStatus", "Healthy")),
                "size_gb": size_gb
            })
        return results
    except Exception as e:
        return [{"device_id": "0", "model": "Storage Drive", "status": f"JSON Parse Error: {e}", "health": "Unknown"}]
