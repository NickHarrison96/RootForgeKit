# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# RootForgeKit — PyInstaller build spec (Windows)
#
# Build:
#     .venv\Scripts\python.exe -m PyInstaller RootForgeKit.spec --noconfirm
#
# Produces dist\RootForgeKit\ — a ONEDIR bundle (a folder with RootForgeKit.exe in it),
# deliberately not a single .exe:
#
#   * onefile unpacks ~150 MB of Qt into a temp folder on EVERY launch, which
#     is a multi-second startup delay the user watches with no window on screen
#   * onefile bundles trip heuristic antivirus far more often than a plain
#     folder of DLLs
#   * that temp folder is deleted on exit, so nothing written beside the exe
#     survives — see utils/paths.py for why that matters here
#
# Ship it as a zip for now. A proper installer (Inno Setup) is the next step
# once the contents stop changing.
#
# NOT ELEVATED: uac_admin is deliberately left off. RootForgeKit runs unelevated by
# design (utils/elevation.py) and the handful of admin-only tools relaunch
# themselves at click time. Setting uac_admin here would re-break that.
# =============================================================================

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("styles.qss", "."),
    ("resources", "resources"),
]
binaries = []
hiddenimports = []

# --- Android platform-tools ------------------------------------------------
# Shipped inside the bundle so adb/fastboot work on first launch with no
# download. utils/paths.find_platform_tool() looks here first. Skipped
# silently when absent (the directory is gitignored, so a fresh clone has
# no copy) — the app can still download it to %LOCALAPPDATA% at runtime.
_platform_tools = os.path.join(SPECPATH, "bin", "platform-tools")
if os.path.isdir(_platform_tools):
    datas.append((_platform_tools, os.path.join("bin", "platform-tools")))

# --- pymobiledevice3 -------------------------------------------------------
# Resolves service classes by name at runtime, so static analysis cannot see
# most of them. collect_all also picks up its bundled resources (device
# support files, plist templates) which are NOT importable code and would
# otherwise be left behind.
_pmd_datas, _pmd_binaries, _pmd_hidden = collect_all("pymobiledevice3")
datas += _pmd_datas
binaries += _pmd_binaries
hiddenimports += _pmd_hidden

# --- our own packages ------------------------------------------------------
# Most of these are reached by ordinary imports from main.py, but dialogs are
# imported lazily in a few places. Collecting the packages wholesale costs a
# little size and removes a whole class of "only crashes when you click that
# one button" packaging bug.
for _pkg in ("tabs", "components", "utils"):
    hiddenimports += collect_submodules(_pkg)


a = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # PyQt6 is excluded deliberately, not just because it is unused: this app
    # ships under PySide6's LGPL precisely so it can be distributed
    # closed-source. Letting a stray GPL PyQt6 install get swept into the
    # bundle would undo that. The exclude makes the build fail loudly rather
    # than quietly shipping both.
    excludes=["PyQt6", "tkinter"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RootForgeKit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX compression is a reliable way to get flagged by AV
    console=True,       # see note below
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Embedded in the .exe itself, which is what Explorer and the taskbar read
    # before the app is even running. The in-app QIcon (main.app_icon) is a
    # separate mechanism and both are needed.
    icon=os.path.join(SPECPATH, "resources", "app.ico"),
)

# console=True is a PRE-ALPHA choice, not an oversight. The app narrates real
# diagnostics to stdout ([HWID], stylesheet load, tool exit codes) and
# utils/resource_manager.py's crash handler writes tracebacks to stderr. With
# console=False all of that goes nowhere and a tester's bug report becomes
# "it closed". Flip this to False once the crash handler also writes to
# utils.paths.logs_dir().

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RootForgeKit",
)
