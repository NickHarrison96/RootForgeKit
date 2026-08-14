# =============================================================================
# NicksFix — OS Logo Resolution & Rendering
#
# Replaces the old ASCII art on the Overview tab. Vector logos live in
# resources/logos/ and are rendered to a crisp QPixmap at the requested size,
# so they stay sharp on HiDPI displays instead of drifting out of alignment
# the way padded monospace art did.
#
# Drop a replacement <key>.svg (or .png) into resources/logos/ to reskin a
# platform — nothing here needs editing.
# =============================================================================

import os
import platform
import subprocess
import sys

from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QPainter, QPixmap, QColor
from PyQt6.QtSvg import QSvgRenderer


LOGO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "logos",
)

# Accent colour per platform — used for the heading and any tinting.
LOGO_ACCENTS = {
    "windows":    "#4E8FD0",
    "macos":      "#E6EDF3",
    "hackintosh": "#C9D1D9",
    "linux":      "#F5B71C",
}

DISPLAY_NAMES = {
    "windows":    "Windows",
    "macos":      "macOS",
    "hackintosh": "Hackintosh",
    "linux":      "Linux",
}

# Genuine Apple hardware reports a model identifier beginning with one of these.
APPLE_MODEL_PREFIXES = (
    "MacBook", "MacBookAir", "MacBookPro", "iMac", "iMacPro",
    "Macmini", "MacPro", "Mac", "Xserve", "ADP",
)


def detect_os_key() -> str:
    """
    Resolve the logo key for the running system.

    Returns one of: "windows", "macos", "hackintosh", "linux".
    """
    system = platform.system()

    if system == "Windows":
        return "windows"

    if system == "Darwin":
        return "hackintosh" if _is_hackintosh() else "macos"

    return "linux"


def _is_hackintosh() -> bool:
    """
    True when macOS appears to be running on non-Apple hardware.

    Genuine Macs report an Apple model identifier from `sysctl hw.model`
    (e.g. "MacBookPro18,3"). Hackintoshes usually report the PC board model.
    A spoofed SMBIOS will read as genuine — this is a best-effort hint, not
    an authoritative check.
    """
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.model"],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return False
        model = (result.stdout or "").strip()
        if not model:
            return False
        return not model.startswith(APPLE_MODEL_PREFIXES)
    except Exception:
        return False


def logo_path(key: str) -> str | None:
    """Return the asset path for a logo key, preferring SVG over raster."""
    for extension in (".svg", ".png", ".jpg", ".jpeg"):
        candidate = os.path.join(LOGO_DIR, f"{key}{extension}")
        if os.path.isfile(candidate):
            return candidate
    return None


def render_logo(key: str, size: int = 150,
                tint: str | None = None) -> QPixmap | None:
    """
    Render a logo to a transparent QPixmap of `size` x `size`.

    Args:
        key:  Logo key from detect_os_key().
        size: Target edge length in logical pixels.
        tint: Optional colour applied to SVGs authored with currentColor
              (the macOS mark), so it reads correctly on a dark background.

    Returns None when no asset exists, letting callers fall back gracefully.
    """
    path = logo_path(key)
    if not path:
        return None

    if path.lower().endswith(".svg"):
        return _render_svg(path, size, tint or LOGO_ACCENTS.get(key))

    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    return pixmap.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _render_svg(path: str, size: int, tint: str | None) -> QPixmap | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            markup = handle.read()
    except Exception:
        return None

    # QSvgRenderer does not resolve `currentColor`, so substitute it directly.
    if "currentColor" in markup and tint:
        markup = markup.replace("currentColor", tint)

    renderer = QSvgRenderer(markup.encode("utf-8"))
    if not renderer.isValid():
        return None

    # Preserve the artwork's aspect ratio inside the square target.
    bounds = renderer.defaultSize()
    if bounds.width() <= 0 or bounds.height() <= 0:
        bounds = QSize(size, size)
    scale = min(size / bounds.width(), size / bounds.height())
    width, height = bounds.width() * scale, bounds.height() * scale

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(
        painter,
        QRectF((size - width) / 2, (size - height) / 2, width, height),
    )
    painter.end()
    return pixmap


def available_logos() -> list[str]:
    """Logo keys that currently have an asset on disk."""
    return [key for key in DISPLAY_NAMES if logo_path(key)]


# =============================================================================
# Host capability model
#
# Single source of truth for "what platform are we on, and may this tool run
# here?" — so OS gating lives in one place instead of scattered
# platform.system() checks.
# =============================================================================

# Logo keys mapped back to the platform.system() family they belong to.
_KEY_TO_FAMILY = {
    "windows":    "Windows",
    "macos":      "Darwin",
    "hackintosh": "Darwin",   # a Hackintosh still runs Darwin tooling
    "linux":      "Linux",
}


class HostProfile:
    """
    Describes the running host and answers whether a tool may execute on it.

    Usage:
        host = get_host_profile()
        if not host.supports("Darwin"):
            ...block, and explain with host.block_reason("Darwin")
    """

    def __init__(self):
        self.key = detect_os_key()                       # windows|macos|hackintosh|linux
        self.family = _KEY_TO_FAMILY.get(self.key, platform.system())
        self.display = DISPLAY_NAMES.get(self.key, self.family)
        self.accent = LOGO_ACCENTS.get(self.key, "#00e5ff")
        self.is_hackintosh = self.key == "hackintosh"
        self.release = platform.release()

    # -- capability queries -------------------------------------------------

    def supports(self, target_family: str) -> bool:
        """True when a tool targeting `target_family` can run on this host."""
        return target_family == self.family

    def block_reason(self, target_family: str) -> str:
        """Human-readable explanation for a blocked tool."""
        target = {"Windows": "Windows", "Darwin": "macOS",
                  "Linux": "Linux"}.get(target_family, target_family)
        return (f"This is a {target} command; this host is {self.display}. "
                f"Shown for reference — run it on a {target} machine.")

    def caveats(self) -> list[str]:
        """Non-fatal warnings worth surfacing about this host."""
        notes = []
        if self.is_hackintosh:
            notes.append(
                "Detected macOS on non-Apple hardware. Apple-signed operations "
                "(activation, DDI personalisation) may behave differently."
            )
        return notes

    def __repr__(self):
        return f"<HostProfile {self.display} ({self.family} {self.release})>"


_host_profile: HostProfile | None = None


def get_host_profile() -> HostProfile:
    """Process-wide host profile (detection runs once)."""
    global _host_profile
    if _host_profile is None:
        _host_profile = HostProfile()
    return _host_profile
