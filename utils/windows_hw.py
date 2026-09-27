# =============================================================================
# RootForgeKit — Windows Hardware & OS Identification Quirks
#
# One place for the things that are correct on a developer desktop and wrong on
# somebody else's machine. Every helper here degrades to None/[] off-Windows or
# on failure, so callers stay cross-platform.
#
# Why this module exists, rather than letting each caller shell out:
#
#   1. GPU enumeration. `Win32_VideoController` is the only trustworthy source
#      for *which adapters exist right now*, but its `AdapterRAM` is a uint32,
#      so it cannot report more than ~4 GiB -- every GPU with 4 GB or more
#      reads back as 4095 MB. The true figure lives in the display-class
#      registry as a QWORD (`HardwareInformation.qwMemorySize`). Neither source
#      is usable alone:
#        - registry alone lists *ghost* entries for hardware that has been
#          removed (a machine with one AMD card still had an NVIDIA driver
#          entry sitting in the class key),
#        - CIM alone truncates VRAM at 4 GiB.
#      So enumerate CIM for presence and the registry for size, joined on the
#      PCI device id.
#
#   2. OEM firmware placeholders. Consumer laptops and prebuilt desktops fill
#      BaseBoardProduct with "Default string", "To be filled by O.E.M.",
#      "Not Specified", or a bare board id like "0CD9V2M". Those are not
#      errors to be shown to a user as if they were a motherboard name.
#
#   3. Windows version. The `ProductName` registry value is not a reliable
#      10-vs-11 discriminator, and `CurrentMajorVersionNumber` reads 10 even on
#      Windows 11. The build number is the authority.
# =============================================================================

import ctypes
import platform

from utils.cim_query import cim_query

_IS_WINDOWS = platform.system().lower() == "windows"

# Firmware strings that mean "the OEM didn't fill this in".
_PLACEHOLDERS = frozenset({
    "", "-", "n/a", "na", "none", "null", "nil", "unknown", "default string",
    "default", "oem", "oem string", "to be filled by o.e.m.", "to be filled by oem",
    "not specified", "not available", "not applicable", "system manufacturer",
    "system product name", "system version", "base board", "baseboard",
    " motherboard", "unknown manufacturer", "unknown product",
    "invalid", "empty", "blank", "test", "prototype", "engineering sample",
    "chassis manufacturer", "chassis version",
})

# Display adapters that are not real user-facing GPUs, or are a fallback driver.
# Their names are matched loosely because every vendor spells them differently.
_NON_GPU_PATTERNS = (
    "microsoft basic display",
    "basic render",
    "remote display",
    "indirect display",
    "basic display adapter",
    "hyper-v",
    "vmware svga", "vmware 3d", "virtualbox graphics",
    "qemu", "bochs", "cirrus logic",
    "parsec virtual", "spacedesk", "idd virtual",
)

# PCI vendor IDs. Authoritative, unlike substring-matching adapter names.
_VENDOR_IDS = {
    "10DE": "NVIDIA",   # NVIDIA
    "1002": "AMD",       # AMD/ATI
    "1022": "AMD",       # AMD
    "8086": "Intel",     # Intel, including Arc
    "1414": "Microsoft", # Microsoft basic display
    "5353": "Microsoft", # Microsoft Hyper-V
    "15AD": "VMware",
    "1AF4": "VirtualBox",
    "1B36": "QEMU/Bochs",
}

# Vendor ids that are never a real user-facing GPU.
_NON_GPU_VENDOR_IDS = frozenset({"1414", "5353", "15AD", "1AF4", "1B36"})

_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def _is_windows() -> bool:
    return _IS_WINDOWS


# -----------------------------------------------------------------------------
# Firmware placeholder sanitising
# -----------------------------------------------------------------------------

def sanitize_firmware_value(value: str | None) -> str:
    """
    Normalise a firmware/SMBIOS string, returning "" when it carries no
    information.

    Strips surrounding whitespace and quotes, collapses internal runs of
    whitespace, and maps known placeholder text to "". `value` of None or a
    non-string yields "".
    """
    if not value or not isinstance(value, str):
        return ""
    text = " ".join(value.split()).strip().strip('"').strip("'").strip()
    if text.lower() in _PLACEHOLDERS:
        return ""
    return text


def sanitize_pair(first: str | None, second: str | None, sep: str = " ") -> str:
    """Join two sanitised firmware values, skipping the empty ones."""
    parts = [p for p in (sanitize_firmware_value(first),
                         sanitize_firmware_value(second)) if p]
    return sep.join(parts)


# -----------------------------------------------------------------------------
# GPU enumeration
# -----------------------------------------------------------------------------

def _pnp_vendor_id(pnp_device_id: str) -> str:
    """
    Extract the PCI vendor id from a PNP device id. '' if there isn't one.

    The id is a `VEN_xxxx` token: four hex digits, so the whole token is eight
    characters. (An earlier version of this checked for seven, which silently
    matched nothing at all.)
    """
    if not pnp_device_id:
        return ""
    for token in pnp_device_id.replace("\\", " ").replace("&", " ").split():
        key = token.upper()
        if key.startswith("VEN_") and len(key) == 8:
            digits = key[4:]
            if all(char in "0123456789ABCDEF" for char in digits):
                return digits
    return ""


def vendor_from_device_id(pnp_device_id: str) -> str:
    """'NVIDIA' / 'AMD' / 'Intel' / 'Microsoft' / 'Unknown' from a PNP device id."""
    return _VENDOR_IDS.get(_pnp_vendor_id(pnp_device_id), "Unknown")


def is_non_gpu(name: str, pnp_device_id: str = "") -> bool:
    """
    True for basic-display, remote/virtual and hypervisor adapters, which must
    not be reported as the machine's GPU.

    Checks the PCI vendor id first (hypervisors and virtual adapters are
    identifiable that way) and falls back to the adapter name.
    """
    vendor_id = _pnp_vendor_id(pnp_device_id)
    if vendor_id and vendor_id in _NON_GPU_VENDOR_IDS:
        return True
    lowered = (name or "").lower()
    return any(pattern in lowered for pattern in _NON_GPU_PATTERNS)


def _read_display_class_registry() -> list[dict]:
    """
    Read every display-class key in the registry.

    Returns one dict per adapter with `desc`, `device_id` and `vram_bytes`
    (`None` when the adapter has no dedicated memory). Includes entries for
    hardware that is no longer installed -- callers must reconcile against CIM
    before trusting this list.
    """
    if not _is_windows():
        return []
    try:
        import winreg
    except ImportError:
        return []

    adapters = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS)
    except OSError:
        return []

    index = 0
    while True:
        try:
            subkey = f"{index:04d}"
            with winreg.OpenKey(root, subkey) as key:
                def _read(name):
                    try:
                        return winreg.QueryValueEx(key, name)[0]
                    except OSError:
                        return None

                desc = _read("DriverDesc")
                if not desc:
                    index += 1
                    continue
                qword = _read("HardwareInformation.qwMemorySize")
                vram = int(qword) if isinstance(qword, (int, float)) and qword > 0 else None
                adapters.append({
                    "key": subkey,
                    "desc": sanitize_firmware_value(desc),
                    "device_id": (_read("MatchingDeviceId") or ""),
                    "vram_bytes": vram,
                })
        except OSError:
            pass
        index += 1
        if index > 64:  # hard stop; real machines have a handful
            break
    return adapters


def enumerate_gpus(include_ghost_free_only: bool = True) -> list[dict]:
    """
    List the display adapters currently present, best-effort.

    Each dict has: `name`, `vendor`, `pnp_device_id`, `vram_bytes` (int, or
    None when only the truncated WMI figure is available), `vram_truncated`
    (True when `vram_bytes` came from the uint32 `AdapterRAM` and may be
    clamped at 4 GiB), and `is_basic`.

    Presence comes from `Win32_VideoController`, so adapters that are only
    left in the registry as driver leftovers are excluded. The registry is
    joined on the PCI device id purely to recover true VRAM.
    """
    if not _is_windows():
        return []

    rows = cim_query(
        "Win32_VideoController",
        ["Name", "PNPDeviceID", "AdapterRAM", "AdapterCompatibility", "VideoModeDescription"],
    )
    registry = _read_display_class_registry()

    # Index registry entries by the VEN_xxxx&DEV_xxxx pair, which is unique per
    # model and stable regardless of which adapter enumerated first.
    def _reg_key(device_id: str) -> str:
        upper = (device_id or "").upper()
        parts = [t for t in upper.replace("\\", " ").replace("&", " ").split()
                 if t.startswith("VEN_") or t.startswith("DEV_")]
        return " ".join(sorted(parts))

    reg_index = {}
    for entry in registry:
        key = _reg_key(entry["device_id"])
        if key:
            reg_index.setdefault(key, entry)

    gpus = []
    for row in rows:
        name = sanitize_firmware_value(row.get("Name")) or "Unknown GPU"
        pnp = row.get("PNPDeviceID") or ""
        vendor = vendor_from_device_id(pnp)
        if vendor == "Unknown":
            compat = (row.get("AdapterCompatibility") or "").lower()
            for token, mapped in (("nvidia", "NVIDIA"), ("amd", "AMD"),
                                  ("ati", "AMD"), ("intel", "Intel")):
                if token in compat:
                    vendor = mapped
                    break

        basic = is_non_gpu(row.get("Name"), pnp)

        vram_bytes = None
        truncated = False
        reg = reg_index.get(_reg_key(pnp))
        if reg and reg["vram_bytes"]:
            vram_bytes = reg["vram_bytes"]
        else:
            raw = (row.get("AdapterRAM") or "").strip()
            if raw.isdigit() and int(raw) > 0:
                vram_bytes = int(raw)
                # AdapterRAM is a uint32; anything at/over the ceiling is a
                # clamped reading of a larger card, not a real 4 GiB figure.
                truncated = int(raw) >= (2 ** 32 - 4096)

        gpus.append({
            "name": name,
            "vendor": vendor,
            "pnp_device_id": pnp,
            "vram_bytes": vram_bytes,
            "vram_truncated": truncated,
            "is_basic": basic,
            "drives_display": bool(sanitize_firmware_value(row.get("VideoModeDescription"))),
        })

    return gpus


def real_gpus() -> list[dict]:
    """Adapters that are actual user-facing GPUs (no basic/remote/virtual)."""
    return [g for g in enumerate_gpus() if not g["is_basic"]]


def rank_gpus(gpus: list[dict] | None = None) -> list[dict]:
    """
    Order adapters most- to least-likely-to-be-the-one-a-user-wants.

    Rationale, because "primary GPU" is genuinely ambiguous on a hybrid laptop:
    the integrated GPU usually drives the internal panel, but a user asking for
    a *driver* almost always wants the discrete card -- and integrated adapters
    report no dedicated VRAM while discrete ones report their real capacity.
    So: adapters with true dedicated VRAM sort first (largest first), then
    adapters without it.

    Basic/remote/virtual adapters are always dropped. A machine showing only
    "Microsoft Basic Display Adapter" has no GPU to report or install a driver
    for, so returning an empty list is the honest answer -- naming a vendor
    there would put a dead driver button in front of the user.
    """
    gpus = real_gpus() if gpus is None else gpus
    gpus = [g for g in gpus if not g.get("is_basic")]

    def _key(g):
        has_vram = 0 if g.get("vram_bytes") else 1
        return (has_vram, -(g.get("vram_bytes") or 0))

    return sorted(gpus, key=_key)


def primary_gpu() -> dict | None:
    """Best single adapter, or None when none is identifiable."""
    ranked = rank_gpus()
    return ranked[0] if ranked else None


def gpu_vendors(gpus: list[dict] | None = None) -> list[str]:
    """Every distinct real-GPU vendor present, most significant first."""
    seen, out = set(), []
    for gpu in rank_gpus(gpus):
        vendor = gpu.get("vendor", "Unknown")
        if vendor != "Unknown" and vendor not in seen:
            seen.add(vendor)
            out.append(vendor)
    return out


# -----------------------------------------------------------------------------
# Baseboard / system identity
# -----------------------------------------------------------------------------

def baseboard_info() -> dict:
    """
    Motherboard identity with OEM placeholders removed.

    On a laptop the baseboard fields are frequently a board id or a placeholder
    rather than anything a person recognises, so when the sanitised result is
    empty the *system* model is used instead ("XPS 15 9530" beats "0CD9V2M").
    Returns keys `manufacturer`, `product`, `is_baseboard` (False when the
    values came from the system model), and `serial`.
    """
    if not _is_windows():
        return {}

    manufacturer = product = serial = ""
    for row in cim_query("Win32_BaseBoard",
                         ["Manufacturer", "Product", "SerialNumber"]):
        manufacturer = sanitize_firmware_value(row.get("Manufacturer"))
        product = sanitize_firmware_value(row.get("Product"))
        serial = sanitize_firmware_value(row.get("SerialNumber"))
        break

    if not manufacturer and not product:
        for row in cim_query("Win32_ComputerSystemProduct", ["Vendor", "Name", "Version"]):
            manufacturer = sanitize_firmware_value(row.get("Vendor"))
            product = sanitize_firmware_value(row.get("Name"))
            serial = sanitize_firmware_value(row.get("Version"))
            break

    is_baseboard = bool(manufacturer or product)
    if not is_baseboard:
        return {}

    # A vendor name plus a marketing model is what a user recognises; a bare
    # board id on its own is not, so prefer the system model in that case.
    if not product or _looks_like_board_id(product):
        system_model = system_model_name()
        if system_model:
            manufacturer = manufacturer or sanitize_firmware_value(system_model)
            product = system_model
            is_baseboard = False

    return {
        "manufacturer": manufacturer,
        "product": product,
        "serial": serial,
        "is_baseboard": is_baseboard,
    }


def _looks_like_board_id(value: str) -> bool:
    """
    True for strings that are an OEM board identifier rather than a model name.

    Laptop baseboards are commonly labelled with a short alphanumeric code
    ("0CD9V2M", "DA0Z0F") and carry no useful meaning outside the OEM.
    """
    if not value or " " in value:
        return False
    if len(value) > 12:
        return False
    if not any(ch.isdigit() for ch in value):
        return False
    # A bare model number with no vendor name attached.
    return sum(ch.isalnum() for ch in value) == len(value)


def system_model_name() -> str:
    """Marketing model of the machine, e.g. 'XPS 15 9530'. '' if unknown."""
    if not _is_windows():
        return ""
    for row in cim_query("Win32_ComputerSystem", ["Manufacturer", "Model"]):
        model = sanitize_firmware_value(row.get("Model"))
        if model:
            return model
    return ""


def baseboard_label() -> str:
    """Single-line human-readable board/system label. Never raises."""
    try:
        info = baseboard_info()
    except Exception:
        return ""
    return sanitize_pair(info.get("manufacturer"), info.get("product")) or system_model_name()


# -----------------------------------------------------------------------------
# OS version
# -----------------------------------------------------------------------------

def windows_version_label() -> str:
    """
    'Windows 11 Pro (24H2, build 26100.1)'-style string.

    The edition comes from `EditionID` and the 10-vs-11 split from
    `CurrentBuildNumber`, because neither `ProductName` nor
    `CurrentMajorVersionNumber` can be trusted: Microsoft has left `ProductName`
    reading "Windows 10 ..." on Windows 11 machines, and
    `CurrentMajorVersionNumber` is 10 on Windows 11 regardless.
    """
    if not _is_windows():
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
            def _read(name, default=""):
                try:
                    return winreg.QueryValueEx(key, name)[0]
                except OSError:
                    return default

            edition = str(_read("EditionID", "")).strip()
            display = str(_read("DisplayVersion", "")).strip()
            build = str(_read("CurrentBuildNumber", "")).strip()
            ubr = str(_read("UBR", "")).strip()
    except (ImportError, OSError):
        return ""

    try:
        build_num = int(build)
    except (TypeError, ValueError):
        build_num = 0

    if build_num >= 22000:
        product = "Windows 11"
    elif build_num >= 10240:
        product = "Windows 10"
    elif build_num >= 9600:
        product = "Windows 8.1"
    elif build_num >= 7600:
        product = "Windows 8"
    elif build_num >= 6000:
        product = "Windows Vista"
    elif build_num >= 2600:
        product = "Windows XP"
    else:
        product = "Windows"

    if edition and edition.lower() not in ("", "core", "professionalevaluation"):
        # DisplayVersion is a marketing label; map the odd legacy ids.
        friendly = {
            "enterprise": "Enterprise",
            "enterpriseeval": "Enterprise Evaluation",
            "enterpriseevaluations": "Enterprise Evaluation",
            "professional": "Pro",
            "professionalworkstation": "Pro for Workstations",
            "professionaleval": "Pro Evaluation",
            "home": "Home",
            "homepremium": "Home Premium",
            "core": "Home",
            "ultimate": "Ultimate",
            "standard": "Standard",
            "education": "Education",
            "educationn": "Education N",
            "student": "Student",
        }.get(edition.lower(), edition)
        product = f"{product} {friendly}"

    parts = [p for p in (display,) if p]
    if build:
        parts.append(f"build {build}.{ubr}" if ubr else f"build {build}")
    return " ".join([product] + parts) if parts else product


# -----------------------------------------------------------------------------
# Display
# -----------------------------------------------------------------------------

def display_resolution() -> tuple[int, int] | None:
    """
    (width, height) of the primary display in *physical* pixels.

    `GetSystemMetrics` is subject to DPI virtualisation, so on a scaled display
    it can report a shrunken figure (a 2560x1600 panel at 150% reports about
    1706x1067) depending on the process's DPI awareness. `EnumDisplaySettings`
    reads the mode straight from the display driver and is unaffected.
    """
    if not _is_windows():
        return None

    class DEVMODE(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", ctypes.c_wchar * 32),
            ("dmSpecVersion", ctypes.c_ushort),
            ("dmDriverVersion", ctypes.c_ushort),
            ("dmSize", ctypes.c_ushort),
            ("dmDriverExtra", ctypes.c_ushort),
            ("dmFields", ctypes.c_ulong),
            ("dmPositionX", ctypes.c_long),
            ("dmPositionY", ctypes.c_long),
            ("dmDisplayOrientation", ctypes.c_ulong),
            ("dmDisplayFixedOutput", ctypes.c_ulong),
            ("dmColor", ctypes.c_short),
            ("dmDuplex", ctypes.c_short),
            ("dmYResolution", ctypes.c_short),
            ("dmTTOption", ctypes.c_short),
            ("dmCollate", ctypes.c_short),
            ("dmFormName", ctypes.c_wchar * 32),
            ("dmLogPixels", ctypes.c_ushort),
            ("dmBitsPerPel", ctypes.c_ulong),
            ("dmPelsWidth", ctypes.c_ulong),
            ("dmPelsHeight", ctypes.c_ulong),
            ("dmDisplayFlags", ctypes.c_ulong),
            ("dmDisplayFrequency", ctypes.c_ulong),
            ("dmICMMethod", ctypes.c_ulong),
            ("dmICMIntent", ctypes.c_ulong),
            ("dmMediaType", ctypes.c_ulong),
            ("dmDitherType", ctypes.c_ulong),
            ("dmReserved1", ctypes.c_ulong),
            ("dmReserved2", ctypes.c_ulong),
            ("dmPanningWidth", ctypes.c_ulong),
            ("dmPanningHeight", ctypes.c_ulong),
        ]

    try:
        mode = DEVMODE()
        mode.dmSize = ctypes.sizeof(DEVMODE)
        # ENUM_CURRENT_SETTINGS = -1
        if not ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(mode)):
            return None
        width, height = int(mode.dmPelsWidth), int(mode.dmPelsHeight)
        return (width, height) if width > 0 and height > 0 else None
    except Exception:
        return None


def display_count() -> int:
    """Number of attached displays, or 0 if it cannot be determined."""
    if not _is_windows():
        return 0
    try:
        count = int(ctypes.windll.user32.GetSystemMetrics(80) or 0)  # SM_CMONITORS
        if count > 0:
            return count
    except Exception:
        pass
    try:
        user32 = ctypes.windll.user32
        if not user32.SetProcessDPIAware():
            return 0
        return int(user32.GetSystemMetrics(80) or 0)
    except Exception:
        return 0
