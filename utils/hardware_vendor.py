# =============================================================================
# RootForgeKit — CPU/GPU Vendor Detection
# Best-effort vendor identification so Tech Tools can route driver-install
# buttons correctly (Intel has a real winget-installable auto-detect tool;
# AMD and NVIDIA don't publish one, so those route to the vendor's official
# driver page instead — see RevLog 2026-08-13 "chipset/GPU driver buttons").
# =============================================================================

import platform

from utils.cim_query import cim_query


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
    Best-effort primary GPU vendor via CIM. Windows-only caller.
    Returns 'NVIDIA', 'AMD', 'Intel', or 'Unknown'.

    Was a bare `wmic path win32_videocontroller get Name /format:csv`, which
    swallowed FileNotFoundError and returned 'Unknown'. On current Windows 11
    wmic is gone, so this silently returned 'Unknown' on every new machine --
    which quietly rerouted the driver buttons to the wrong vendor's page (or
    to no Intel auto-install) with nothing on screen to say why.
    """
    names = " ".join(row["Name"] for row in cim_query("Win32_VideoController", ["Name"]))
    output = names.lower()

    if "nvidia" in output:
        return "NVIDIA"
    if "amd" in output or "radeon" in output:
        return "AMD"
    if "intel" in output:
        return "Intel"
    return "Unknown"
