# Pymobile3-GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing `ios_toolkit/` scaffold into a standalone, Windows-first PySide6 app (Pymobile3-GUI) that ships independently of NixFix.

**Architecture:** The scaffold already has the right shape — `MainWindow` composing a custom titlebar + sidebar + `QStackedWidget` of 6 views + a persistent `OperationDock`/`OperationDrawer`, all fed by a `TaskManager` singleton. Work is: (1) rename package + vendor the backend engines so nothing imports `utils.*`, (2) swap the window shell from hand-rolled frameless to extend-into-frame, (3) apply the approved visual system (Inter / JetBrains Mono / Lucide), (4) finish the four feedback widgets, (5) package.

**Tech Stack:** Python 3.12, PySide6, pymobiledevice3, nest-asyncio, psutil, PyInstaller (onedir), ctypes (Win32 DWM).

**Spec:** `docs/superpowers/specs/2026-09-09-ios-toolkit-standalone-design.md`

## Global Constraints

- Product name **Pymobile3-GUI**; import package `pymobile3_gui`; dist `pymobile3-gui`; window title `Pymobile3-GUI`; AppUserModelID `Pymobile3GUI.Windows.v1`.
- Windows 10 **and** 11. Real Mica only on Win11 (build ≥ 22000); Win10 gets a flat opaque dark surface — by design, not a bug.
- Zero imports from NixFix `utils.*` / `tabs.*` / `components.*` after Task 2. Backend lives at `pymobile3_gui/core/backend/`.
- No auth / server / licensing / tiers. No Android. No macOS/Linux packaging this phase.
- Fonts/icons bundled under `pymobile3_gui/assets/`; **do not bundle Segoe UI Variable** (named fallback only).
- Deps: `PySide6`, `pymobiledevice3`, `nest-asyncio`, `psutil`. Nothing else.
- Palette values in `theme.py` (`Colors`) are kept as-is (they match the approved mockup).
- All user-facing strings say "Pymobile3-GUI", never "RootForgeKit" / "iOS Toolkit" / "NixFix".
- README credits pymobiledevice3 (doronz88) as the upstream engine.
- Every task ends: compiles clean (`python -m compileall`), app imports (`python -c "import pymobile3_gui.main"`), commit.
- Work on branch `ios-toolkit-standalone` (already created). The new repo split happens at the end (Task 12), not now — build/verify in place first.

---

### Task 1: Rename package `ios_toolkit` → `pymobile3_gui`

**Files:**
- Rename dir: `ios_toolkit/` → `pymobile3_gui/`
- Modify: every `.py` under it (imports `from ios_toolkit.` → `from pymobile3_gui.`)
- Modify: `pymobile3_gui/main.py` (APP_USER_MODEL_ID, window title, docstring)

**Interfaces:**
- Produces: importable package `pymobile3_gui` with submodules `main`, `ui.*`, `core.*`, `views.*`.

- [ ] **Step 1:** `git mv ios_toolkit pymobile3_gui`
- [ ] **Step 2:** Rewrite imports:
```bash
grep -rl 'ios_toolkit' pymobile3_gui --include='*.py' | xargs sed -i 's/\bios_toolkit\b/pymobile3_gui/g'
```
- [ ] **Step 3:** In `pymobile3_gui/main.py` set `APP_USER_MODEL_ID = "Pymobile3GUI.Windows.v1"`, `setWindowTitle("Pymobile3-GUI")`, update module docstring first line to `Pymobile3-GUI - Main Application Entry Point`.
- [ ] **Step 4:** Verify no stragglers: `grep -rn 'ios_toolkit\|AppleToolkit\|iOS Toolkit' pymobile3_gui` → expect no output.
- [ ] **Step 5:** `python -m compileall pymobile3_gui` → clean.
- [ ] **Step 6:** Commit: `git add -A && git commit -m "Rename ios_toolkit package to pymobile3_gui"`

---

### Task 2: Vendor the backend, sever `utils.*`

**Files:**
- Create dir: `pymobile3_gui/core/backend/` with `__init__.py`
- Copy in (from repo root): `utils/ios_core/tunnel_manager.py`, `utils/ios_core/backup_engine.py`, `utils/ios_core/file_system.py`, `utils/process_runner.py`, `utils/elevation.py`, `utils/resource_manager.py`, `utils/paths.py`
- Modify: those copies' internal imports + strings
- Modify: `pymobile3_gui/main.py` (delete `sys.path` REPO_ROOT hack, lines ~18-21)
- Modify: `pymobile3_gui/views/*.py`, `pymobile3_gui/core/*.py` — rewrite `from utils.` → `from pymobile3_gui.core.backend.`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `pymobile3_gui.core.backend.tunnel_manager`: `TunneldManager`, `get_tunnel_manager()`, `run_developer_command(args, timeout=20, udid=None, require_tunnel=True) -> (bool, str)`, `needs_tunnel(v) -> bool`, `is_admin()`; `TunneldManager.preflight(product_version=None) -> list[{name,ok,detail,fix}]`, `.start(wait_seconds=25) -> (bool,str)`, `.stop() -> (bool,str)`, `.is_running() -> bool`, `.tunnel_env(udid=None) -> dict`
  - `...backend.backup_engine`: `AcquisitionWorker(mode: str, output_dir: str, options: dict|None)` — QThread, signals `progress(int)`, `status(str)`, `output(str)`, `finished(bool, str)`, method `.cancel()`; consts `ACQUISITION_MODES: dict`, `DEFAULT_OPTIONS: dict`
  - `...backend.file_system`: `FileSystemManager(lockdown_provider=None)` with `list_dir(path="/")`, `read_file`, `write_file`, `make_dir`, `remove`, `download_file(remote,local)`, `upload_file(local,remote)`; `AFCException`
  - `...backend.process_runner`: `format_duration(seconds: float) -> str`, `StreamingProcessRunner`
  - `...backend.resource_manager`: `safe_run_command(cmd, timeout=..., env=None) -> (bool, str)`
  - `...backend.elevation`: `is_admin() -> bool`
  - `...backend.paths`: `backups_dir()`, `config_dir()`, `data_dir()`, `resource_path(*parts)`

- [ ] **Step 1:** Create backend dir + `__init__.py`:
```bash
mkdir -p pymobile3_gui/core/backend && touch pymobile3_gui/core/backend/__init__.py
cp utils/ios_core/tunnel_manager.py utils/ios_core/backup_engine.py utils/ios_core/file_system.py utils/process_runner.py utils/elevation.py utils/resource_manager.py utils/paths.py pymobile3_gui/core/backend/
```
- [ ] **Step 2:** In `pymobile3_gui/core/backend/`, rewrite cross-module imports:
```bash
cd pymobile3_gui/core/backend
sed -i 's/from utils\.process_runner/from pymobile3_gui.core.backend.process_runner/; s/from utils\.elevation/from pymobile3_gui.core.backend.elevation/; s/from utils\.resource_manager/from pymobile3_gui.core.backend.resource_manager/; s/from utils\.paths/from pymobile3_gui.core.backend.paths/; s/from utils\.hwid/from pymobile3_gui.core.backend.paths/' *.py
cd -
```
- [ ] **Step 3:** Replace RootForgeKit-isms in the backend copies:
```bash
sed -i 's/RootForgeKit/Pymobile3-GUI/g; s/Restart RootForgeKit as Administrator/Restart Pymobile3-GUI as Administrator/g' pymobile3_gui/core/backend/*.py
sed -i "s#iOS Tools → Developer Setup & DDI#the Developer view#g; s#Open  iOS Tools → Developer Setup & DDI  and press#Open the Developer view and press#g" pymobile3_gui/core/backend/*.py
```
Then read `pymobile3_gui/core/backend/tunnel_manager.py` `TUNNEL_HINT` + `preflight()` and hand-fix any remaining "iOS Tools" phrasing to "the Developer view".
- [ ] **Step 4:** Check `paths.py` for a `hwid`/`get_smbios_info` dependency; if `paths.py` imports anything else from `utils`, copy that too and repeat step 2's sed for it. (`hwid.py` is NOT needed by this app — if `paths.py` imports it, delete that import and any function that uses it; `config_dir`/`data_dir`/`backups_dir`/`resource_path` don't need it.)
- [ ] **Step 5:** In app code, rewrite `utils` imports:
```bash
grep -rl 'from utils\.' pymobile3_gui --include='*.py' | grep -v '/backend/' | xargs sed -i \
 -e 's#from utils\.ios_core\.tunnel_manager#from pymobile3_gui.core.backend.tunnel_manager#g' \
 -e 's#from utils\.ios_core\.backup_engine#from pymobile3_gui.core.backend.backup_engine#g' \
 -e 's#from utils\.ios_core\.file_system#from pymobile3_gui.core.backend.file_system#g' \
 -e 's#from utils\.resource_manager#from pymobile3_gui.core.backend.resource_manager#g' \
 -e 's#from utils\.process_runner#from pymobile3_gui.core.backend.process_runner#g' \
 -e 's#from utils\.paths#from pymobile3_gui.core.backend.paths#g' \
 -e 's#from utils\.elevation#from pymobile3_gui.core.backend.elevation#g'
```
- [ ] **Step 6:** In `pymobile3_gui/main.py` delete the 4-line `REPO_ROOT` / `sys.path.insert` block.
- [ ] **Step 7:** `grep -rn 'from utils\.\|import utils\|from tabs\.\|from components\.\|REPO_ROOT' pymobile3_gui` → expect no output.
- [ ] **Step 8:** `python -m compileall pymobile3_gui` → clean. Then `python -c "import pymobile3_gui.main"` from repo root → no ImportError (a Qt "no display" error is fine; ImportError is not).
- [ ] **Step 9:** Commit: `git add -A && git commit -m "Vendor ios_core backend into pymobile3_gui, sever utils imports"`

---

### Task 3: Window shell spike — extend-into-frame

**Files:**
- Modify: `pymobile3_gui/ui/native_window.py` (replace the frameless approach)

**Interfaces:**
- Consumes: nothing.
- Produces: `NativeFramelessWindow(QMainWindow)` with `.set_title_bar(widget)`, unchanged constructor signature. Keeps `showEvent` applying the DWM backdrop.

Approach: keep the native frame (do NOT set `Qt.FramelessWindowHint`). Extend the frame into the client area and paint the custom titlebar on top. This preserves Aero Snap / resize / shadow / DPI natively.

- [ ] **Step 1:** Rewrite `native_window.py`:
```python
"""Pymobile3-GUI - Native window shell: native frame kept, frame extended into client area for a custom titlebar + DWM backdrop."""
import sys, ctypes
from ctypes import c_int, byref, sizeof, Structure
from PySide6.QtWidgets import QMainWindow, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_MAINWINDOW = 2
WM_NCCALCSIZE = 0x0083

class MARGINS(Structure):
    _fields_ = [("cxLeftWidth", c_int), ("cxRightWidth", c_int),
                ("cyTopHeight", c_int), ("cyBottomHeight", c_int)]

def _win_build() -> int:
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0

def apply_windows_glass(hwnd: int) -> bool:
    """True when a real Mica backdrop was applied (Win11 22000+)."""
    if sys.platform != "win32":
        return False
    try:
        dwm = ctypes.windll.dwmapi
        dark = c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(dark), sizeof(dark))
        dwm.DwmExtendFrameIntoClientArea(hwnd, byref(MARGINS(-1, -1, -1, -1)))
        if _win_build() >= 22000:
            bd = c_int(DWMSBT_MAINWINDOW)
            hr = dwm.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, byref(bd), sizeof(bd))
            return hr == 0
        return False
    except Exception:
        return False

class NativeFramelessWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title_bar_widget = None
        self._is_glass_active = False
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_title_bar(self, widget: QWidget):
        self.title_bar_widget = widget

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and not self._is_glass_active:
            self._is_glass_active = apply_windows_glass(int(self.winId()))
            self.update()

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG" and sys.platform == "win32":
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                return True, 0
        return super().nativeEvent(eventType, message)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._is_glass_active:
            p.fillRect(self.rect(), QColor(10, 11, 16, 40))
        else:
            p.fillRect(self.rect(), QColor(10, 11, 16, 255))
```
- [ ] **Step 2:** `python -m compileall pymobile3_gui/ui/native_window.py` → clean.
- [ ] **Step 3:** Manual check (Windows box, `python -m pymobile3_gui.main`), record PASS/FAIL for each: (a) window has rounded corners + shadow; (b) drag titlebar moves window; (c) drag to screen edge → Aero Snap; (d) drag bottom-right corner → resize; (e) Win11: blur visible behind sidebar/cards; Win10: clean opaque dark, no black flash on resize; (f) move between two monitors at different scale → no layout break.
- [ ] **Step 4:** If (c)/(d) fail (native non-client area got fully eaten): change `WM_NCCALCSIZE` handler to return `super().nativeEvent(...)` (i.e. let DWM keep the resize border) and instead offset the titlebar widget down by the caption height. Re-test.
- [ ] **Step 5:** If blur still cannot show through client area without flicker after step 4: STOP, report to controller — fallback is adopting `PySideSix-Frameless-Window` (spec §5), which is a plan change requiring a ruling.
- [ ] **Step 6:** Commit: `git add pymobile3_gui/ui/native_window.py && git commit -m "Window shell: extend-into-frame, native frame retained"`

---

### Task 4: Bundle fonts + icons

**Files:**
- Create: `pymobile3_gui/assets/fonts/` — `Inter-Regular.ttf`, `Inter-Medium.ttf`, `Inter-SemiBold.ttf`, `JetBrainsMono-Regular.ttf`
- Create: `pymobile3_gui/assets/icons/` — Lucide SVGs (subset below)
- Create: `pymobile3_gui/ui/assets.py` — loader

**Interfaces:**
- Produces: `pymobile3_gui.ui.assets`: `load_fonts() -> None` (call once after `QApplication`), `icon(name: str, color: str = "#f6f7fb", size: int = 18) -> QIcon`, `ICON_DIR: Path`.

- [ ] **Step 1:** Download fonts (OFL) into `assets/fonts/`:
```bash
mkdir -p pymobile3_gui/assets/fonts pymobile3_gui/assets/icons
curl -L -o pymobile3_gui/assets/fonts/Inter-Regular.ttf https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Regular.ttf
curl -L -o pymobile3_gui/assets/fonts/Inter-Medium.ttf https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Medium.ttf
curl -L -o pymobile3_gui/assets/fonts/Inter-SemiBold.ttf https://github.com/rsms/inter/raw/master/docs/font-files/Inter-SemiBold.ttf
curl -L -o pymobile3_gui/assets/fonts/JetBrainsMono-Regular.ttf https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Regular.ttf
```
(If a URL 404s, get the file from the project's latest release zip; commit the .ttf regardless.)
- [ ] **Step 2:** Download Lucide SVGs (ISC) into `assets/icons/` — names: `smartphone, usb, battery, battery-charging, hard-drive, download, upload, cpu, terminal, plug, unplug, refresh-cw, triangle-alert, shield-check, circle-check, circle-x, loader, folder, file, x, minus, square, chevron-right, activity, wifi`:
```bash
for n in smartphone usb battery battery-charging hard-drive download upload cpu terminal plug unplug refresh-cw triangle-alert shield-check circle-check circle-x loader folder file x minus square chevron-right activity wifi; do
  curl -L -o "pymobile3_gui/assets/icons/$n.svg" "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/$n.svg"
done
```
- [ ] **Step 3:** Write `pymobile3_gui/ui/assets.py`:
```python
from pathlib import Path
from PySide6.QtGui import QFontDatabase, QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtSvg import QSvgRenderer

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
FONT_DIR = ASSET_DIR / "fonts"
ICON_DIR = ASSET_DIR / "icons"

def load_fonts() -> None:
    for ttf in FONT_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(ttf))

def icon(name: str, color: str = "#f6f7fb", size: int = 18) -> QIcon:
    path = ICON_DIR / f"{name}.svg"
    if not path.exists():
        return QIcon()
    svg = path.read_text(encoding="utf-8").replace('stroke="currentColor"', f'stroke="{color}"')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return QIcon(pm)
```
- [ ] **Step 4:** `python -c "from PySide6.QtSvg import QSvgRenderer"` — if it fails, add `PySide6` covers it (QtSvg ships with PySide6-Essentials; no new dep).
- [ ] **Step 5:** `python -m compileall pymobile3_gui/ui/assets.py` → clean.
- [ ] **Step 6:** Commit: `git add pymobile3_gui/assets pymobile3_gui/ui/assets.py && git commit -m "Bundle Inter + JetBrains Mono + Lucide icon subset"`

---

### Task 5: Point theme at bundled fonts + call the loader

**Files:**
- Modify: `pymobile3_gui/ui/theme.py:62` (font-family line)
- Modify: `pymobile3_gui/main.py` (`main()` — call `load_fonts()` before `setStyleSheet`)
- Modify: `pymobile3_gui/ui/operation_drawer.py:158` (log console font → JetBrains Mono)

**Interfaces:**
- Consumes: `pymobile3_gui.ui.assets.load_fonts`.

- [ ] **Step 1:** In `theme.py`, change the `QWidget` `font-family` to `'Inter', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;`
- [ ] **Step 2:** In `theme.py` add, inside `get_application_stylesheet()`'s returned QSS, a rule: `QPlainTextEdit, QTextEdit { font-family: 'JetBrains Mono', 'Consolas', monospace; }` (append before closing `"""`).
- [ ] **Step 3:** In `operation_drawer.py` the `log_console` stylesheet `font-family` → `'JetBrains Mono', 'Consolas', monospace`.
- [ ] **Step 4:** In `main.py` `main()`: `from pymobile3_gui.ui.assets import load_fonts` and call `load_fonts()` right after `app = QApplication(sys.argv)`.
- [ ] **Step 5:** `python -m compileall pymobile3_gui` → clean; `python -c "import pymobile3_gui.main"` → ok.
- [ ] **Step 6:** Commit: `git add -A && git commit -m "Wire theme to bundled Inter + JetBrains Mono"`

---

### Task 6: Replace Unicode-glyph step icons with Lucide

**Files:**
- Modify: `pymobile3_gui/ui/operation_drawer.py` (`StepBadge.set_state` — glyphs → `assets.icon`)
- Modify: `pymobile3_gui/ui/operation_dock.py` (pulse dot stays; no icon change needed)

**Interfaces:**
- Consumes: `pymobile3_gui.ui.assets.icon`.

- [ ] **Step 1:** In `operation_drawer.py`, `StepBadge.__init__`: replace `self.lbl_icon = QLabel("○", self)` with a 16px `QLabel` that shows a pixmap; add helper `self._set_icon(name, color)` doing `self.lbl_icon.setPixmap(icon(name, color, 16).pixmap(16,16))`.
- [ ] **Step 2:** In `set_state`: `done`→`_set_icon("circle-check", Colors.SUCCESS)`, `running`→`_set_icon("loader", "#60a5fa")`, `failed`→`_set_icon("circle-x", Colors.DANGER)`, `pending`→`_set_icon("chevron-right", Colors.TEXT_MUTED)`. Keep the existing frame background styling per state.
- [ ] **Step 3:** `python -m compileall pymobile3_gui` → clean.
- [ ] **Step 4:** Commit: `git add -A && git commit -m "Step badges use Lucide icons"`

---

### Task 7: Backend-signal → TaskManager adapter

**Files:**
- Create: `pymobile3_gui/core/task_bridge.py`
- Modify: `pymobile3_gui/views/acquisition_view.py` (use the bridge instead of the inline lambda bridge at ~line 276)

**Interfaces:**
- Consumes: `pymobile3_gui.core.task_manager.TaskManager`; a QThread worker exposing signals `progress(int)`, `status(str)`, `output(str)`, `finished(bool, str)` and method `.cancel()` (matches `AcquisitionWorker`).
- Produces: `pymobile3_gui.core.task_bridge`: `run_worker(task_id: str, title: str, subtitle: str, steps: list[str], worker) -> None` — starts `worker`, registers a `TaskInfo` with `TaskManager`, forwards `worker.progress→TaskInfo.progress`, `worker.status→current_step/status_text`, `worker.output→task_log`, `worker.finished→task_finished`; wires `TaskManager.cancel_active_task` to `worker.cancel()`.

- [ ] **Step 1:** Write `task_bridge.py`:
```python
"""Adapt a signal-style QThread worker (progress/status/output/finished) onto TaskManager."""
import time, uuid
from pymobile3_gui.core.task_manager import TaskManager, TaskInfo, TaskStep

def run_worker(task_id, title, subtitle, steps, worker):
    tm = TaskManager.instance()
    info = TaskInfo(task_id=task_id, title=title, subtitle=subtitle,
                    steps=[TaskStep(name=s) for s in steps],
                    current_step=steps[0] if steps else "",
                    status_text="Starting…", is_running=True, start_time=time.time())
    tm.tasks[task_id] = info
    tm.active_task_id = task_id
    tm._current_worker_cancel = worker.cancel

    def on_progress(pct):
        info.progress = max(0, min(100, int(pct)))
        tm.task_progress.emit(info)
    def on_status(text):
        info.status_text = text
        for s in info.steps:
            if s.name == text:
                s.status = "running"
        info.current_step = text
        tm.task_progress.emit(info)
    def on_output(line):
        info.logs.append(line)
        tm.task_log.emit(task_id, line)
    def on_finished(ok, msg):
        info.is_running = False
        info.progress = 100 if ok else info.progress
        info.status_text = "Completed" if ok else "Failed"
        if not ok:
            info.error = msg
            for s in info.steps:
                if s.status == "running":
                    s.status = "failed"
        else:
            for s in info.steps:
                s.status = "done"
        if tm.active_task_id == task_id:
            tm.active_task_id = None
        tm.task_finished.emit(info)

    worker.progress.connect(on_progress)
    worker.status.connect(on_status)
    worker.output.connect(on_output)
    worker.finished.connect(on_finished)
    worker.start()
    tm.task_started.emit(info)
```
- [ ] **Step 2:** In `task_manager.py` `cancel_active_task`: after the existing body, add `cb = getattr(self, "_current_worker_cancel", None)` and `if cb: cb()` so signal-style workers also get cancelled.
- [ ] **Step 3:** In `acquisition_view.py`, replace the inline signal-bridging block with `from pymobile3_gui.core.task_bridge import run_worker` and one `run_worker("acq-"+uuid, mode_label, "Forensic acquisition", step_names, self.worker)` call. Keep `self.worker = AcquisitionWorker(...)` construction.
- [ ] **Step 4:** `python -m compileall pymobile3_gui` → clean; `python -c "import pymobile3_gui.main"` → ok.
- [ ] **Step 5:** Commit: `git add -A && git commit -m "Add backend-signal to TaskManager bridge; use it in acquisition view"`

---

### Task 8: Tunnel handshake feedback — step checklist from preflight

**Files:**
- Modify: `pymobile3_gui/views/developer_view.py` (the "Start Tunnel" flow)

**Interfaces:**
- Consumes: `TunneldManager.preflight(product_version) -> list[{name,ok,detail,fix}]`, `.start()`, `run_worker` (Task 7), `assets.icon`.

- [ ] **Step 1:** Read `developer_view.py` around the tunnel-start button + `DvtProcessWorker`. Identify where `get_tunnel_manager().start()` is called.
- [ ] **Step 2:** Wrap the tunnel start in a tiny QThread `TunnelStartWorker(QThread)` with signals `progress(int)`, `status(str)`, `output(str)`, `finished(bool,str)`, `.cancel()` (no-op). Its `run()`: call `tm.preflight(v)`; for each check emit `status(check["name"])` + `output(check["detail"])` + (fail → `output("  fix: "+check["fix"])`); then `tm.start()`; emit `finished(ok, msg)`.
- [ ] **Step 3:** On button click: `steps = [c["name"] for c in tm.preflight(product_version)] + ["Start tunnel"]`, then `run_worker("tunnel", "Developer tunnel", "iOS 17+ RSD", steps, TunnelStartWorker(...))`. The dock+drawer render the checklist automatically (no fake %).
- [ ] **Step 4:** `python -m compileall pymobile3_gui` → clean.
- [ ] **Step 5:** Commit: `git add -A && git commit -m "Tunnel handshake shows a step checklist driven by preflight"`

---

### Task 9: IPSW restore — caution banner + guarded cancel

**Files:**
- Modify: `pymobile3_gui/views/restore_view.py`

**Interfaces:**
- Consumes: `safe_run_command` (backend), `run_worker` (Task 7), `assets.icon`, `Colors.WARNING*`.

- [ ] **Step 1:** Read `restore_view.py` — find the restore trigger (`safe_run_command(cmd, timeout=1200)` at ~237) and the confirm dialog if any.
- [ ] **Step 2:** Before start: require a typed confirmation — `QInputDialog.getText(self, "Confirm restore", 'This erases the device and installs iOS. Type "restore" to proceed.')`; bail unless text == `"restore"`.
- [ ] **Step 3:** Add a persistent amber banner widget at the top of the view, hidden by default, shown while a restore task is active: `triangle-alert` icon + "Keep the device connected and this app open. Do not unplug or restart the device." Style with `Colors.WARNING_BG` / `Colors.WARNING_BORDER` / `Colors.WARNING`.
- [ ] **Step 4:** Wrap the restore call in a `RestoreWorker(QThread)` (signal-style, `.cancel()` sets a flag checked between stages). Stages list: `["Verify image", "Extract", "Flash", "Reboot", "Wait for device"]`. Emit `status(stage)` as it advances; emit `progress` where the tool prints `%` (reuse `AcquisitionWorker._parse_percent` logic — copy the staticmethod), else leave indeterminate (emit `progress(-1)`... dock shows 0; acceptable for v1).
- [ ] **Step 5:** In the dock, when `task_id` starts with `"restore-"` and step index ≥ 2 ("Flash"), hide the Cancel button. Simplest: in `operation_dock.update_task`, `self.btn_cancel.setVisible(not (task.task_id.startswith("restore-") and task.current_step in ("Flash", "Reboot", "Wait for device")))`.
- [ ] **Step 6:** On `finished(False, msg)`: banner turns red, text = plain message + raw tail; leave device-state text visible. (No auto-DFU logic this phase — just don't dead-end: show msg + "Retry" button that re-opens the confirm flow.)
- [ ] **Step 7:** `python -m compileall pymobile3_gui` → clean.
- [ ] **Step 8:** Commit: `git add -A && git commit -m "IPSW restore: typed confirm, caution banner, cancel hidden past point of no return"`

---

### Task 10: Live syslog — console controls

**Files:**
- Modify: `pymobile3_gui/views/syslog_view.py`

**Interfaces:**
- Consumes: `assets.icon`.

- [ ] **Step 1:** Read `syslog_view.py` — it spawns `pymobiledevice3 syslog live` and appends lines to a console.
- [ ] **Step 2:** Add a toolbar row above the console: Stop (was likely "Cancel" — relabel), Pause/Resume toggle (buffers lines while paused, flushes on resume), a `QLineEdit` filter (case-insensitive substring; non-matching lines hidden), Clear, and a right-aligned line-count label.
- [ ] **Step 3:** Autoscroll: only scroll to bottom if the scrollbar was already at max before append (so scrolling up to read pauses follow).
- [ ] **Step 4:** `python -m compileall pymobile3_gui` → clean.
- [ ] **Step 5:** Commit: `git add -A && git commit -m "Syslog view: pause, filter, clear, line count, sticky autoscroll"`

---

### Task 11: PyInstaller spec + requirements + README

**Files:**
- Create: `Pymobile3-GUI.spec`, `requirements.txt`, `README.md`, `.gitignore`
- Create: `pymobile3_gui/__main__.py`

**Interfaces:** none.

- [ ] **Step 1:** `pymobile3_gui/__main__.py`:
```python
from pymobile3_gui.main import main
if __name__ == "__main__":
    main()
```
- [ ] **Step 2:** `requirements.txt`:
```
PySide6==6.11.1
pymobiledevice3==10.7.4
nest-asyncio==1.6.0
psutil==7.2.2
```
- [ ] **Step 3:** `Pymobile3-GUI.spec` — copy NixFix's `RootForgeKit.spec`, then: entry `["pymobile3_gui/__main__.py"]`, name `Pymobile3-GUI`, drop the `keyring`/`win32ctypes` block, keep the `pymobiledevice3` `collect_all` block, `datas += [("pymobile3_gui/assets", "pymobile3_gui/assets")]`, `hiddenimports += collect_submodules("pymobile3_gui")`, drop `bin/platform-tools` block (Android only).
- [ ] **Step 4:** `.gitignore`: `.venv/`, `__pycache__/`, `build/`, `dist/`, `*.spec~`.
- [ ] **Step 5:** `README.md`: what it is (a PySide6 GUI over pymobiledevice3), Windows 10/11, features (device info, backup/acquisition, developer tunnel + DVT, IPSW restore, live syslog, AFC file browser), install (`pip install -r requirements.txt`, `python -m pymobile3_gui`), build (`pyinstaller Pymobile3-GUI.spec`), and a **Credits** section: "Device communication is powered by [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) by doronz88. This project is an independent GUI frontend."
- [ ] **Step 6:** `python -m pymobile3_gui` imports/starts (or Qt-no-display error). Commit: `git add -A && git commit -m "Add packaging spec, requirements, README"`

---

### Task 12: Split into standalone repo

**Files:** repo-level.

**Interfaces:** none.

- [ ] **Step 1:** From repo root: `mkdir ../pymobile3-gui && cp -r pymobile3_gui Pymobile3-GUI.spec requirements.txt README.md .gitignore ../pymobile3-gui/`
- [ ] **Step 2:** `cd ../pymobile3-gui && git init && git add -A && git commit -m "Initial commit: Pymobile3-GUI extracted from RootForgeKit"`
- [ ] **Step 3:** `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/python -m pymobile3_gui` → app launches.
- [ ] **Step 4:** In the NixFix repo, on branch `ios-toolkit-standalone`: `git rm -r pymobile3_gui` (the scaffold now lives in its own repo), keep `docs/superpowers/`. Commit: `git commit -m "Move iOS toolkit to standalone pymobile3-gui repo"`.
- [ ] **Step 5:** Report the new repo path to the user; they create the GitHub remote and push (not done here — pushing to a new public remote is theirs to do).

---

## Self-Review

**Spec coverage:**
- §2a backend / §6 vendoring → Task 2. §2b scaffold kept → Tasks 1,5-10 build on it. §3 custom chrome / §5 window shell → Task 3. §3 Win10 fallback → Task 3 step 1 (`_win_build() >= 22000` gate). §7 Inter/JBMono/Lucide → Tasks 4-6. §8 four feedback patterns → tunnel (Task 8), backup (Task 7 — bridge; the determinate bar already exists in the dock), IPSW (Task 9), syslog (Task 10). §9 packaging → Task 11. Repo → Task 12. Non-goals respected (no auth/Android/mac). ✔
- Gap: §8 backup "ETA / X of Y GB" text — the dock shows `%` only. Accepted for v1: `AcquisitionWorker.status` already emits human detail lines into the drawer; a dedicated ETA readout is polish, not in a task. Noted as deferred.

**Placeholder scan:** Task 4 icon list + font URLs are concrete. Task 9 indeterminate handling explicitly deferred (stated). No "TBD"/"handle edge cases". ✔

**Type consistency:** `run_worker(task_id, title, subtitle, steps, worker)` — same signature Tasks 7/8/9 call. `assets.icon(name, color, size)` — consistent Tasks 4/6/8/9. `TaskInfo` fields (`progress`, `steps`, `current_step`, `status_text`, `logs`, `error`, `is_running`) match `task_manager.py` as read. ✔
