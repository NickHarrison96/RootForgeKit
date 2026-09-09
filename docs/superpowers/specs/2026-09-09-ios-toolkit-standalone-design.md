# Pymobile3-GUI — Standalone Windows App Design

**Date:** 2026-09-09
**Status:** Design — approved 2026-09-09; ready for implementation plan
**Author:** Nick (KushNick420) with Claude

**Product name:** Pymobile3-GUI — a GUI frontend over pymobiledevice3. Display
name / repo / window title use `Pymobile3-GUI`; the dist name is `pymobile3-gui`;
the importable Python package is `pymobile3_gui` (hyphens are invalid in Python
identifiers). The scaffold's current `ios_toolkit` package is renamed to
`pymobile3_gui` in Phase 1. The README must credit pymobiledevice3 (doronz88) as
the upstream engine the name derives from.

## 1. Goal

Extract the iOS device-tooling out of RootForgeKit/NixFix into a **standalone,
Windows-first desktop application** refined for a public/PR release. The bar is
"feels intuitive and refined like an Apple product": custom app chrome, a
translucent glass backdrop, considered typography and iconography, and
operation feedback (progress bars, step checklists, live logs) that replaces
today's raw scrolling terminal.

This is a polish-and-productize effort, not a rewrite. The iOS backend engines
are proven and move over unchanged; the work is a new UI shell around them plus
the packaging to ship them on their own.

## 2. Starting point (what already exists)

Two bodies of code already exist in the NixFix repo and are the raw material:

### 2a. The backend engines (proven, in `utils/ios_core/`, ~855 lines)
- `tunnel_manager.py` — RemoteXPC/RSD tunnel lifecycle (iOS 17+ developer services)
- `backup_engine.py` — `AcquisitionWorker`, `ACQUISITION_MODES`, `DEFAULT_OPTIONS` (logical / logical+ / PRFS backups)
- `file_system.py` — `FileSystemManager`, `AFCException` (AFC file access)

These are verified against physical hardware (iPad on iOS 18.7.9 per RevLog) and
change **only** as needed to sever NixFix imports (see §6).

### 2b. A UI scaffold (`ios_toolkit/`, ~3,531 lines, untracked)
A prior session already scaffolded the standalone app. Its architecture is
sound and is kept:
- `main.py` — `MainWindow` composing title bar + sidebar + `QStackedWidget` of 6 views + operation dock/drawer
- `ui/native_window.py` — custom window shell (Win32 DWM + hit-testing)
- `ui/theme.py` — `Colors` + QSS; deep-dark palette, blue accent, macOS traffic-light colors
- `ui/title_bar.py`, `ui/sidebar.py` — custom chrome + navigation with a device-identity card
- `ui/operation_dock.py` (persistent bottom bar) + `ui/operation_drawer.py` (expandable log) — the progressive-disclosure feedback surface
- `core/task_manager.py` — `TaskManager` singleton; `TaskInfo` model already carries `steps` (pending/running/done/failed), `progress` 0–100, `logs`, `is_cancelled`, `error`, `start_time`
- `core/device_poller.py` — background usbmux device discovery
- `views/` — `device`, `files_apps`, `acquisition`, `developer`, `restore`, `syslog`

**The scaffold currently imports the backend via a `sys.path` hack back into
NixFix's `utils.*`.** That coupling is the main thing standing between it and a
standalone repo.

## 3. Settled decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Chrome | Fully custom, Apple-inspired (custom title bar, no OS title bar) |
| OS floor | Windows 10 **and** 11 |
| Blur | Real Mica on Win11; **graceful flat fallback** on Win10 (Mica does not exist there — Microsoft limitation) |
| Visual language | Frosted-dark: sidebar + device card, floating cards, blue accent — locked against the approved mockup |
| Repo | Brand-new standalone repo (clean history for public release) |
| Name | **Pymobile3-GUI** — import package `pymobile3_gui`, dist `pymobile3-gui`, renamed from the scaffold's `ios_toolkit` in Phase 1 |

## 4. Architecture

```
pymobile3_gui/
├── main.py                  entry point, MainWindow composition
├── ui/
│   ├── native_window.py     custom window shell (DWM backdrop + chrome behavior)
│   ├── title_bar.py         custom caption: device status, window controls
│   ├── sidebar.py           workspace nav + device identity card
│   ├── theme.py             Colors, QSS, font + icon loading
│   ├── operation_dock.py    persistent progress summary (collapsed feedback)
│   ├── operation_drawer.py  expandable raw-log panel (progressive disclosure)
│   └── feedback/            the four operation-feedback widgets (§5)
├── core/
│   ├── task_manager.py      TaskManager singleton + WorkerThread
│   ├── device_poller.py     background device discovery
│   └── backend/             VENDORED iOS engines (§6)
├── views/                   the 6 workspace pages
└── assets/
    ├── fonts/               Inter, JetBrains Mono (bundled)
    └── icons/               Lucide subset (bundled)
```

Data flow: a view starts an operation through `TaskManager.start_task(...)`,
passing the step list and a worker function. `WorkerThread` runs it off the UI
thread and emits `progress_cb / log_cb / is_cancelled_cb`. `TaskManager` folds
those into the `TaskInfo` model and emits `task_progress` / `task_log`; the dock,
drawer, and the active view's feedback widget subscribe. This backbone already
exists and is kept.

## 5. The window shell — the one high-risk decision

The approved chrome is "extend-into-frame like VS Code / Windows Terminal":
**keep the native window frame** (so Aero Snap, edge-resize, drop shadow, Alt+Tab
thumbnails, and multi-monitor DPI all come from the OS for free) and paint custom
content up into the caption area. Research confirmed this coexists with a real
Mica backdrop via `DwmExtendFrameIntoClientArea` + `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE)`.

**The scaffold does NOT currently do this.** `native_window.py` took the
hand-rolled *frameless* path (`Qt.FramelessWindowHint`, `WM_NCCALCSIZE`→0, custom
`WM_NCHITTEST`). That is the highest-risk option identified in research: pure
frameless typically loses Aero Snap and Snap Layouts unless additional Win32
style bits are restored, and the current `paintEvent` fills the client area with
an ~84%-opaque tint (`QColor(10,11,16,215)`) that would largely cancel the very
blur it enables.

**Because the window shell is load-bearing for the whole app and carries the
project's only real technical risk, it is built and validated first, as a spike,
before any view work.** The shell must demonstrably deliver, on both Win10 and
Win11:
1. Custom title bar with working window controls + drag
2. Working Aero Snap (drag-to-edge, Win+Arrow) and edge/corner resize
3. Correct behavior across a DPI change (dragging between monitors of different scale)
4. Mica blur visible through the client area on Win11; clean flat dark surface on Win10
5. No black flash / flicker on resize

Preferred route: true extend-into-frame (native frame retained). **Sanctioned
fallback if client-area blur proves to flicker or the hit-testing fights the
native frame:** adopt the maintained `qframelesswindow` library
(`PySideSix-Frameless-Window`), which already solves frameless snap/resize/shadow
and underpins PyQt-Fluent-Widgets — reskinned to this app's visuals. The current
hand-rolled frameless code is not kept as-is; it is replaced by whichever of
those two the spike validates. The opaque `paintEvent` tint is reduced to a light
scrim (target ~10–20% alpha) so the backdrop reads as glass.

## 6. Vendoring the backend (severing NixFix)

For a standalone repo the app cannot import from NixFix's `utils.*`. The
dependency surface is small and clean (verified — no tangled graph):

Copy into `pymobile3_gui/core/backend/`:
- `utils/ios_core/{tunnel_manager,backup_engine,file_system}.py`
- `utils/process_runner.py` (provides `format_duration`, `StreamingProcessRunner`)
- `utils/elevation.py` (`is_admin`)
- `utils/resource_manager.py` (`safe_run_command`; pulls in `psutil`)
- `utils/paths.py` (`backups_dir`, `config_dir`, `data_dir`, resource resolution)

Then rewrite imports (`from utils.X` → `from pymobile3_gui.core.backend.X`) and
delete the `sys.path` REPO_ROOT hack in `main.py`. The scaffold's own
`ios_toolkit.*` imports are rewritten to `pymobile3_gui.*` in the same Phase-1 pass. These modules are generic
infra with no NixFix-specific logic; copying (rather than sharing) is correct for
a cleanly separable public release. NixFix keeps its own originals untouched.

## 7. Visual system

- **Inter** (SIL OFL 1.1) — primary UI face, bundled under `assets/fonts/`, loaded via `QFontDatabase.addApplicationFont`. Replaces the current stack's reliance on Segoe UI Variable, which is **not** redistributable and absent on Win10; it may remain only as a named fallback, never bundled.
- **JetBrains Mono** (SIL OFL 1.1) — all numeric readouts (byte counts, %, serials, timestamps) and the log/console surfaces, bundled.
- **Lucide** icons (ISC) — replaces the current Unicode-glyph placeholders (`○ ✓ ● ✕`). A curated subset (device, USB, battery, download/upload, terminal, warning, shield, refresh, plug, etc.) bundled as SVG under `assets/icons/` with a small `QIcon` loader that can tint to theme colors. ~1.5px stroke at 16px, ~1.75–2px at 20px, sized to text cap-height.
- **Palette** — keep `theme.py`'s existing deep-dark values (they match the approved mockup): canvas `#0a0b10`, cards `#171b25`, blue accent `#2563eb`, macOS traffic-light close/min/max. Surface opacities are tuned so cards read as frosted over the Win11 backdrop.

## 8. The four feedback patterns

All four are driven by the existing `TaskInfo` model and rendered by dedicated
widgets under `ui/feedback/`. The dock shows the active operation's summary; the
drawer is the shared "Show details" raw-log panel (auto-expands on failure).

| Operation | Pattern | Notes |
|---|---|---|
| Tunnel handshake | Step checklist | Rows (developer mode → mount DDI → start tunnel → verify services); spinner on active, ✓/✗ on resolved; no fake %. Drives from `TaskInfo.steps`. |
| Device backup | Determinate bar + metadata | Real byte %, `X / Y GB`, elapsed, ETA, Cancel. Falls back to indeterminate pulse (never a frozen bar) if the byte signal drops. |
| IPSW restore | Staged stepper + nested bar + caution banner | Per-stage bar where % exists, indeterminate where it doesn't (reboot/wait). Persistent **amber** "keep connected — don't unplug" banner. Cancel hidden past the point of no return; type-to-confirm before start. Failure halts the stepper at the failed stage, shows plain-language error + raw code, distinguishes recoverable / DFU / hardware. |
| Live syslog | Streaming console | Kept as a console (the honest choice for open-ended streams); add pause/resume, filter/search, line count, clear, Stop. |

## 9. Packaging & release

- **PyInstaller onedir** bundle (matches NixFix's proven approach; onedir avoids the onefile temp-unpack startup delay and AV false positives, and satisfies PySide6 LGPL dynamic-linking).
- The `pymobiledevice3` `collect_all` block from NixFix's `.spec` lifts over directly. The `keyring`/`win32ctypes` block is **not** carried (no auth in this app).
- Dependencies: `PySide6`, `pymobiledevice3`, `nest-asyncio`, `psutil`. No `requests`/`keyring`.
- New repo gets its own `README`, `requirements.txt`, `.gitignore`, and `.spec`.
- `console=True` stays for pre-alpha diagnostics until a file-logging crash handler exists (same rationale as NixFix).

## 10. Non-goals

- No Android tooling (this is iOS-only; Android stays in NixFix).
- No auth / server / licensing / tiers (removed from NixFix; never enters this app).
- No macOS/Linux packaging in this phase (Windows-first; the backend is
  cross-platform but the chrome and packaging target Windows).
- No new device features — this productizes existing capability, it does not
  extend it.

## 11. Risks

1. **Window shell (high):** blur-through-client + native snap on both OS versions is the hard part. Mitigated by building it first as a validated spike with `qframelesswindow` as a sanctioned fallback (§5).
2. **Win10 acrylic (accepted):** no real Mica on Win10; flat fallback by design, not a bug.
3. **IPSW restore safety (high consequence):** interrupting can brick a device. The UI must implement the caution banner, hidden-Cancel-at-point-of-no-return, and confirmation exactly as specified; the underlying restore flow is existing/proven.
4. **Icon/font licensing (low):** all chosen assets are OFL/ISC and bundleable; Segoe UI Variable explicitly excluded from bundling.

## 12. Build sequence (phases; detailed tasks come from the plan)

1. **Repo + foundation:** new repo skeleton, rename package `ios_toolkit` → `pymobile3_gui` (imports, dir, window title, AppUserModelID), bundle fonts/icons, port `theme.py` to Inter/JetBrains Mono/Lucide, vendor the backend (§6), get the app importing with zero NixFix references.
2. **Window shell spike (§5):** validate blur + snap + resize + DPI on Win10 and Win11; lock the shell approach.
3. **Views on the validated shell:** wire the 6 views to the vendored backend; confirm device discovery + tunnel.
4. **The four feedback patterns (§8):** build the `ui/feedback/` widgets and route each operation through the right one; wire progressive disclosure.
5. **Packaging & polish:** `.spec`, onedir build, README, icon, first end-to-end run on hardware.

## 13. Verification

- Every phase ends compiling clean and importing with no `utils.*` (NixFix) references remaining.
- Window shell: manual validation matrix (Win10 + Win11 × snap/resize/DPI/blur) — this is inherently a see-it test, not a unit test.
- Backend: exercised via the views against a physical device (the only meaningful test for device I/O); `format_duration` and any pure helpers get unit tests when touched.
- No claim of "done" on any operation without a real run against hardware or a faithful stand-in.
