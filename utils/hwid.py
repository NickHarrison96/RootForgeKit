# =============================================================================
# RootForgeKit — SMBIOS Hardware Identity Engine
# Queries SMBIOS Type 001 (System) & Type 002 (Baseboard) parameters to extract
# Motherboard Vendor, Model, System UUID. Computes a cryptographically unique
# SHA-256 Licensing Host ID hash. Filters OEM placeholder strings.
# =============================================================================

import hashlib
import platform
import subprocess
import re


# OEM placeholder strings that should be filtered out
OEM_PLACEHOLDERS = {
    "to be filled by o.e.m.",
    "to be filled by o.e.m",
    "default string",
    "not specified",
    "not available",
    "system manufacturer",
    "system product name",
    "base board manufacturer",
    "base board product name",
    "none",
    "n/a",
    "unknown",
    "",
}


def _clean_value(value: str) -> str:
    """Strip whitespace and filter OEM placeholder strings."""
    cleaned = value.strip()
    if cleaned.lower() in OEM_PLACEHOLDERS:
        return ""
    return cleaned


def get_smbios_info() -> dict:
    """
    Query SMBIOS Type 001 (System) and Type 002 (Baseboard) data.

    Returns a dict with keys:
        - system_manufacturer: System vendor name
        - system_product:      System product/model name
        - system_uuid:         System UUID (Type 001)
        - board_manufacturer:  Baseboard/motherboard vendor
        - board_product:       Baseboard/motherboard model
        - board_serial:        Baseboard serial number (if accessible)
    """
    system = platform.system()
    info = {
        "system_manufacturer": "",
        "system_product": "",
        "system_uuid": "",
        "board_manufacturer": "",
        "board_product": "",
        "board_serial": "",
    }

    if system == "Windows":
        info = _query_windows_smbios()
    elif system == "Linux":
        info = _query_linux_smbios()
    elif system == "Darwin":
        info = _query_macos_smbios()

    # Clean all values through OEM placeholder filter
    return {k: _clean_value(v) for k, v in info.items()}


def _query_windows_smbios() -> dict:
    """Extract SMBIOS data on Windows via WMIC / PowerShell."""
    info = {
        "system_manufacturer": "",
        "system_product": "",
        "system_uuid": "",
        "board_manufacturer": "",
        "board_product": "",
        "board_serial": "",
    }

    # ---- WMIC queries (works on most Windows versions) ----
    queries = {
        # Type 001: System Information
        "system": {
            "cmd": ["wmic", "csproduct", "get", "Vendor,Name,UUID", "/format:csv"],
            "fields": {"Vendor": "system_manufacturer", "Name": "system_product", "UUID": "system_uuid"},
        },
        # Type 002: Baseboard Information
        "baseboard": {
            "cmd": ["wmic", "baseboard", "get", "Manufacturer,Product,SerialNumber", "/format:csv"],
            "fields": {"Manufacturer": "board_manufacturer", "Product": "board_product",
                       "SerialNumber": "board_serial"},
        },
    }

    for qkey, qdef in queries.items():
        try:
            result = subprocess.run(
                qdef["cmd"], capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                if len(lines) >= 2:
                    headers = [h.strip() for h in lines[0].split(",")]
                    values = [v.strip() for v in lines[1].split(",")]
                    row = dict(zip(headers, values))
                    for csv_key, info_key in qdef["fields"].items():
                        if csv_key in row:
                            info[info_key] = row[csv_key]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    # ---- PowerShell fallback for UUID if WMIC failed ----
    if not info["system_uuid"]:
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if result.returncode == 0 and result.stdout.strip():
                info["system_uuid"] = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    return info


def _query_linux_smbios() -> dict:
    """Extract SMBIOS data on Linux via /sys/devices/virtual/dmi/id/."""
    info = {
        "system_manufacturer": "",
        "system_product": "",
        "system_uuid": "",
        "board_manufacturer": "",
        "board_product": "",
        "board_serial": "",
    }

    dmi_base = "/sys/devices/virtual/dmi/id"
    file_map = {
        "sys_vendor": "system_manufacturer",
        "product_name": "system_product",
        "product_uuid": "system_uuid",
        "board_vendor": "board_manufacturer",
        "board_name": "board_product",
        "board_serial": "board_serial",
    }

    for filename, key in file_map.items():
        try:
            with open(f"{dmi_base}/{filename}", "r") as f:
                info[key] = f.read().strip()
        except (FileNotFoundError, PermissionError, OSError):
            pass

    # Fallback: try dmidecode if /sys files are inaccessible
    if not info["board_manufacturer"]:
        try:
            result = subprocess.run(
                ["sudo", "dmidecode", "-t", "2"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("Manufacturer:"):
                        info["board_manufacturer"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Product Name:"):
                        info["board_product"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Serial Number:"):
                        info["board_serial"] = line.split(":", 1)[1].strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    return info


def _query_macos_smbios() -> dict:
    """Extract hardware identity on macOS via system_profiler & ioreg."""
    info = {
        "system_manufacturer": "Apple",
        "system_product": "",
        "system_uuid": "",
        "board_manufacturer": "Apple",
        "board_product": "",
        "board_serial": "",
    }

    # system_profiler for model info
    try:
        result = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                line = line.strip()
                if "Model Name:" in line:
                    info["system_product"] = line.split(":", 1)[1].strip()
                    info["board_product"] = info["system_product"]
                elif "Model Identifier:" in line:
                    # Use as fallback board product
                    if not info["board_product"]:
                        info["board_product"] = line.split(":", 1)[1].strip()
                elif "Serial Number" in line:
                    info["board_serial"] = line.split(":", 1)[1].strip()
                elif "Hardware UUID:" in line:
                    info["system_uuid"] = line.split(":", 1)[1].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # ioreg fallback for UUID
    if not info["system_uuid"]:
        try:
            result = subprocess.run(
                ["ioreg", "-d2", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
                if match:
                    info["system_uuid"] = match.group(1)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    return info


def compute_host_id(smbios_data: dict | None = None) -> str:
    """
    Compute a SHA-256 Licensing Host ID from SMBIOS data.

    The hash is derived from:
        board_manufacturer + board_product + system_uuid

    This creates a stable, unique identifier tied to the physical hardware.

    Returns:
        A 64-character lowercase hex SHA-256 hash string,
        or "UNKNOWN-HWID" if insufficient data is available.
    """
    if smbios_data is None:
        smbios_data = get_smbios_info()

    components = [
        smbios_data.get("board_manufacturer", ""),
        smbios_data.get("board_product", ""),
        smbios_data.get("system_uuid", ""),
    ]

    # Need at least one meaningful component to produce a valid hash
    meaningful = [c for c in components if c]
    if not meaningful:
        return "UNKNOWN-HWID"

    # Build deterministic input string
    hash_input = "|".join(components).encode("utf-8")
    return hashlib.sha256(hash_input).hexdigest()


def get_display_summary(smbios_data: dict | None = None) -> dict:
    """
    Return a display-friendly summary of the SMBIOS identity.

    Returns dict with:
        - board_label:  "Manufacturer Model" (e.g., "ASUS ROG STRIX B550-F")
        - host_id:      SHA-256 hash (first 16 chars for display)
        - host_id_full: Full SHA-256 hash
        - system_uuid:  Raw system UUID
    """
    if smbios_data is None:
        smbios_data = get_smbios_info()

    board_parts = []
    if smbios_data.get("board_manufacturer"):
        board_parts.append(smbios_data["board_manufacturer"])
    if smbios_data.get("board_product"):
        board_parts.append(smbios_data["board_product"])

    board_label = " ".join(board_parts) if board_parts else "Unknown Motherboard"
    host_id_full = compute_host_id(smbios_data)
    host_id_short = host_id_full[:16] if host_id_full != "UNKNOWN-HWID" else "UNKNOWN"

    return {
        "board_label": board_label,
        "host_id": host_id_short,
        "host_id_full": host_id_full,
        "system_uuid": smbios_data.get("system_uuid", "N/A"),
    }
