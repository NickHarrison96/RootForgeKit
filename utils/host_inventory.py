# =============================================================================
# RootForgeKit — Host inventory: this machine's own Add/Remove Programs list.
#
# winget list is NOT a complete answer to "is this installed?". It only
# reports packages it can resolve, and it skips uninstall entries flagged in
# ways it doesn't like. On this test machine TeamViewer 15.81.6 is present in
# Add/Remove Programs and absent from winget's output entirely, and Discord /
# MSYS2 only appear under an `ARP\` pseudo-id that the old scan filtered away.
#
# The uninstall registry keys are the ground truth for presence, so they are
# read directly here. winget stays in the loop for what it is genuinely good
# at: current version and available upgrade for packages it manages.
# =============================================================================

import platform

if platform.system() == "Windows":
    import winreg
else:
    winreg = None


# The three places Windows records an uninstall entry. Two machine hives
# (native + WOW6432Node for 32-bit installers on 64-bit Windows) and one
# per-user hive.
_UNINSTALL_PATHS = (
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)

_HIVES = {}


def _hive(name: str):
    if not _HIVES and winreg is not None:
        _HIVES["HKLM"] = winreg.HKEY_LOCAL_MACHINE
        _HIVES["HKCU"] = winreg.HKEY_CURRENT_USER
    return _HIVES.get(name)


def _read_entry(sub_key) -> tuple[str, str] | None:
    """(DisplayName, DisplayVersion) from one uninstall key, or None."""
    try:
        name, _ = winreg.QueryValueEx(sub_key, "DisplayName")
    except OSError:
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        version, _ = winreg.QueryValueEx(sub_key, "DisplayVersion")
    except OSError:
        version = ""
    if not isinstance(version, str):
        version = str(version) if version is not None else ""
    return name.strip(), version.strip()


def read_installed_programs() -> list[tuple[str, str]]:
    """Every program Windows says is installed, as (DisplayName, DisplayVersion).

    Deliberately unfiltered: no skipping of SystemComponent or other flags.
    winget already skips entries like that, and skipping them here would
    reproduce the exact false negatives this module exists to fix. We only
    ever match this list against a short list of known cards, so extra
    entries cost a few thousand comparisons and nothing else.

    Returns an empty list on non-Windows hosts.
    """
    if winreg is None:
        return []

    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    for hive_name, path in _UNINSTALL_PATHS:
        hive = _hive(hive_name)
        if hive is None:
            continue
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue

        with root:
            index = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(root, sub_name) as sub:
                        entry = _read_entry(sub)
                except OSError:
                    continue
                if entry is None:
                    continue
                dedupe_key = entry[0].lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                found.append(entry)

    return found
