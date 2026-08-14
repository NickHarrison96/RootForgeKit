# =============================================================================
# NicksFix — CPU/GPU Vendor Detection
# Best-effort vendor identification so Tech Tools can route driver-install
# buttons correctly (Intel has a real winget-installable auto-detect tool;
# AMD and NVIDIA don't publish one, so those route to the vendor's official
# driver page instead — see RevLog 2026-08-13 "chipset/GPU driver buttons").
# =============================================================================

import platform
import subprocess


def detect_cpu_vendor() -> str:
    """Returns 'AMD', 'Intel', or 'Unknown' based on platform.processor()."""
    proc = (platform.processor() or "").lower()
    if "amd" in proc:
        return "AMD"
    if "intel" in proc:
        return "Intel"
    return "Unknown"


def detect_gpu_vendor() -> str:
    """
    Best-effort primary GPU vendor via WMI. Windows-only caller (matches the
    existing WMI fallback pattern in utils/sys_info.py's _get_gpu_info).
    Returns 'NVIDIA', 'AMD', 'Intel', or 'Unknown'.
    """
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_videocontroller", "get", "Name", "/format:csv"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "Unknown"

    if result.returncode != 0:
        return "Unknown"

    output = result.stdout.lower()
    if "nvidia" in output:
        return "NVIDIA"
    if "amd" in output or "radeon" in output:
        return "AMD"
    if "intel" in output:
        return "Intel"
    return "Unknown"
