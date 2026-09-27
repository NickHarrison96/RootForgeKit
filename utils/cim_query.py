# =============================================================================
# RootForgeKit — WMI/CIM queries
#
# WHY THIS EXISTS
#
# Every WMI query in this codebase used to shell out to `wmic`, which no longer
# exists on a current Windows install:
#
#   2016  deprecated in Windows Server 2012
#   2021  deprecated in Windows 10 21H2
#   2022  made a Feature on Demand (still preinstalled) in Windows 11 22H2
#   2024  DISABLED by default in Windows 11 23H2 / 24H2
#   2025  removed on upgrade to Windows 11 25H2
#   2026  removed outright on Windows 11 24H2+, 25H2, 26H1 -- and no longer
#         available as a Feature on Demand, so it cannot be re-added
#
# So on a brand-new Windows 11 machine `wmic` is simply not on disk, every
# query raises FileNotFoundError, and the affected feature degrades silently
# (empty GPU list, "Unknown" vendor, "N/A" motherboard) or errors outright in
# the Tech Tools console. WMI itself is fine and fully supported -- it is only
# the command-line front-end that Microsoft deleted.
#
# The replacement is PowerShell's Get-CimInstance, which is the sanctioned
# migration path.
#
# Get-CimInstance is tried FIRST and wmic second, which is the opposite of what
# speed alone would suggest. wmic is ~5x faster (57ms vs 309ms measured here),
# but `wmic ... /format:csv` does NOT quote field values that contain a comma,
# so the output is genuinely ambiguous and unrecoverable. On this machine:
#
#   wmic  -> Manufacturer='Micro-Star International Co.'  Product='Ltd.'
#            SerialNumber='MPG x570 Gaming Edge Wifi'
#   CIM   -> Manufacturer='Micro-Star International Co., Ltd.'
#            Product='MPG x570 Gaming Edge Wifi'
#            SerialNumber='To be filled by O.E.M.'
#
# Everything after the comma is shifted by one, with no error. That is the
# live behaviour of the old positional parser, so the app has been showing the
# wrong BIOS version and the wrong board product/serial on any machine whose
# manufacturer name contains a comma -- which MSI and plenty of others do.
# 250ms of background time is a fair price for not reporting a board's product
# name as its serial number.
#
# wmic is kept only as a fallback, for the narrow case of a Windows install
# where PowerShell is unavailable. It is present on Windows 10 and older
# Windows 11, and absent from current Windows 11, so this path is going dormant
# rather than being removed.
# =============================================================================
# WHY THIS RETURNS DICTS, NOT CSV
#
# The old code parsed `wmic ... /format:csv` by POSITION -- parts[1], parts[2].
# That only worked by accident: wmic reorders columns alphabetically regardless
# of the order asked for, so `get Name,AdapterRAM` comes back as
# `Node,AdapterRAM,Name` and parts[1] happened to be the right field. Request
# any pair that is not already alphabetical and the parser reads the wrong
# column with no error at all.
#
# cim_query() keys every result by the field name the caller asked for, so
# column order cannot matter. Callers should never index positionally.
# =============================================================================

import csv
import io
import platform
import subprocess

# wmic's short aliases, for the fast path. Keys are the canonical CIM class
# names, which is what callers pass and what Get-CimInstance wants.
_WMIC_ALIASES = {
    "Win32_BIOS": "bios",
    "Win32_BaseBoard": "baseboard",
    "Win32_ComputerSystem": "csystem",
    "Win32_ComputerSystemProduct": "csproduct",
    "Win32_DiskDrive": "diskdrive",
    "Win32_LogicalDisk": "logicaldisk",
    "Win32_NetworkAdapterConfiguration": "nicconfig",
    "Win32_OperatingSystem": "os",
    "Win32_PhysicalMemory": "physicalmemory",
    "Win32_Processor": "cpu",
    "Win32_VideoController": "path win32_videocontroller",
}


def wmic_available() -> bool:
    """True if the legacy wmic.exe is present. Windows-only."""
    if platform.system() != "Windows":
        return False
    from shutil import which

    return which("wmic") is not None


def _no_window() -> int:
    """subprocess.CREATE_NO_WINDOW where supported, else 0. Keeps consoles hidden."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _parse_csv_table(text: str, fields: list[str]) -> list[dict[str, str]]:
    """
    Parse a CSV table with a header row into one dict per data row, keyed by
    the field names in `fields`.

    Tolerates the differences between the two producers:
      * wmic prefixes every row with a `Node` column and pads with blank lines
      * ConvertTo-Csv quotes every field, wmic quotes only when it must
    Rows with no data are dropped, and any column we did not ask for is
    discarded so callers only ever see the fields they named.
    """
    rows = [line for line in text.splitlines() if line.strip()]
    if len(rows) < 2:
        return []

    reader = csv.reader(io.StringIO("\n".join(rows)))
    try:
        header = next(reader)
    except StopIteration:
        return []
    header = [h.strip() for h in header]

    out: list[dict[str, str]] = []
    for row in reader:
        record = dict(zip(header, (v.strip() for v in row)))
        # Key strictly by requested field name; an absent column yields "".
        out.append({f: (record.get(f) or "").strip() for f in fields})
    return out


def _query_wmic(class_name: str, fields: list[str], timeout: float) -> list[dict[str, str]]:
    alias = _WMIC_ALIASES.get(class_name, class_name)
    result = subprocess.run(
        ["wmic"] + alias.split() + ["get", ",".join(fields), "/format:csv"],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_no_window(),
    )
    if result.returncode != 0:
        return []
    return _parse_csv_table(result.stdout, fields)


def _query_powershell(class_name: str, fields: list[str], timeout: float) -> list[dict[str, str]]:
    # Select-Object emits properties in the order listed, but that is not
    # relied on anywhere -- _parse_csv_table keys by header name.
    script = (
        "$ProgressPreference = 'SilentlyContinue'; "
        f"Get-CimInstance -ClassName {class_name} -ErrorAction SilentlyContinue "
        "| Select-Object -Property " + ",".join(fields) + " "
        "| ConvertTo-Csv -NoTypeInformation"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_no_window(),
    )
    if result.returncode != 0:
        return []
    return _parse_csv_table(result.stdout, fields)


def cim_query(class_name: str, fields: list[str], timeout: float = 5.0) -> list[dict[str, str]]:
    """
    Query a WMI/CIM class and return one dict per instance.

    `class_name` is a canonical CIM class name, e.g. "Win32_BaseBoard".
    `fields` are CIM property names to read back.

    Each returned dict contains exactly the keys in `fields`; a property the
    class does not have comes back as "". An empty list means the query failed
    or the class has no instances -- callers already treat that as "no data".

    Never raises. A missing PowerShell, a missing wmic, a timeout, a non-zero
    exit or unparseable output all degrade to [].
    """
    if platform.system() != "Windows":
        return []

    for query in (_query_powershell, _query_wmic):
        try:
            rows = query(class_name, fields, timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
            continue
        if rows:
            return rows

    return []
