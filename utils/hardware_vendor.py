# =============================================================================
# RootForgeKit — CPU/GPU Vendor Detection
# Best-effort vendor identification so Tech Tools can route driver-install
# buttons correctly (Intel has a real winget-installable auto-detect tool;
# AMD and NVIDIA don't publish one, so those route to the vendor's official
# driver page instead — see RevLog 2026-08-13 "chipset/GPU driver buttons").
# =============================================================================

import platform

from utils.cim_query import cim_query
from utils.windows_hw import gpu_vendors, rank_gpus

# CIM `Win32_Processor.Manufacturer` values that mean "not x86".
_ARM_VENDORS = ("arm", "qualcomm", "mediatek", "apple", "ampere", "microsoft")


def detect_cpu_vendor() -> str:
    """
    Returns 'AMD', 'Intel', 'ARM', or 'Unknown'.

    Reads `Win32_Processor.Manufacturer` rather than `platform.processor()`.
    The latter returns the PROCESSOR_IDENTIFIER string ('AMD64 Family 23 Model
    113 Stepping 0, AuthenticAMD') on Windows, which says nothing on ARM and is
    empty on some builds -- so an ARM machine, and any Snapdragon-based
    Windows-on-Arm laptop, fell through to 'Unknown' before.
    """
    manufacturers = []
    for row in cim_query("Win32_Processor", ["Manufacturer", "Name"]):
        manufacturer = (row.get("Manufacturer") or "").strip()
        if manufacturer:
            manufacturers.append(manufacturer.lower())
        if manufacturers:
            break

    haystack = " ".join(manufacturers)
    if haystack:
        if "amd" in haystack or "authenticamd" in haystack:
            return "AMD"
        if "intel" in haystack:
            return "Intel"
        for arm in _ARM_VENDORS:
            if arm in haystack:
                return "ARM"

    # Fall back to the platform string, which at least carries the vendor on
    # traditional x86 ('AuthenticAMD', 'Intel64 Family 6 ...').
    proc = (platform.processor() or "").lower()
    if "amd" in proc:
        return "AMD"
    if "intel" in proc:
        return "Intel"
    if any(arm in proc for arm in _ARM_VENDORS):
        return "ARM"
    if platform.machine().lower() in ("arm64", "aarch64"):
        return "ARM"
    return "Unknown"


def detect_gpu_vendor() -> str:
    """
    Vendor of the GPU a user most likely wants a driver for.
    Returns 'NVIDIA', 'AMD', 'Intel', 'ARM', or 'Unknown'.

    Was a bare `wmic path win32_videocontroller get Name /format:csv`, which
    swallowed FileNotFoundError and returned 'Unknown'. On current Windows 11
    wmic is gone, so this silently returned 'Unknown' on every new machine --
    which quietly rerouted the driver buttons to the wrong vendor's page with
    nothing on screen to say why.

    The CIM version then joined *every* adapter's name into one string and
    substring-matched it, which cannot work on a hybrid laptop: the joined text
    contains two vendors, so the answer depended on the order adapters happened
    to enumerate in rather than on which one is real. Vendor is now decoded
    per adapter from its PCI vendor id, adapters are ranked by whether they
    have dedicated VRAM, and basic/virtual adapters are ignored.
    """
    ranked = rank_gpus()
    if not ranked:
        return "Unknown"

    vendor = ranked[0].get("vendor") or "Unknown"
    if vendor == "Microsoft":
        # A VM, hypervisor or missing-driver fallback is not a GPU vendor.
        return "Unknown"
    return vendor


def detect_all_gpu_vendors() -> list[str]:
    """
    Every distinct real-GPU vendor on the machine, most significant first.

    A hybrid laptop legitimately has two, and offering both driver routes is
    more useful than silently picking one.
    """
    vendors = gpu_vendors()
    if vendors:
        return vendors
    # Fall back to name matching when PCI vendor ids are unavailable.
    out, seen = [], set()
    for gpu in rank_gpus():
        name = (gpu.get("name") or "").lower()
        for token, mapped in (("nvidia", "NVIDIA"), ("geforce", "NVIDIA"),
                              ("radeon", "AMD"), ("amd", "AMD"),
                              ("intel", "Intel"), ("arc", "Intel")):
            if token in name and mapped not in seen:
                seen.add(mapped)
                out.append(mapped)
                break
    return out
