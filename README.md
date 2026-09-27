# RootForgeKit

**A cross-platform system utility and diagnostics suite, in one dark-themed desktop app.**
Windows · macOS · Linux — built with PySide6 (Qt 6).
By **KushNick420**.

> ⚠️ **Pre-alpha.** This is unfinished software under active development. Expect
> bugs, breaking changes and half-built features. It is **not** production-ready.
> Use it on hardware you can afford to experiment with, and back up anything
> important first. Feedback and issue reports are welcome.

---

## Contents

- [What this is](#what-this-is)
- [Requirements](#requirements)
- [Install and run](#install-and-run) ← **start here**
- [Using the app](#using-the-app)
- [Do I need Administrator?](#do-i-need-administrator)
- [Where the app writes files](#where-the-app-writes-files)
- [Updating](#updating)
- [Starting over / uninstalling](#starting-over--uninstalling)
- [Troubleshooting](#troubleshooting)
- [Building a standalone executable](#building-a-standalone-executable)
- [Project layout](#project-layout)
- [Platform support — the honest version](#platform-support--the-honest-version)
- [Recent revisions](#recent-revisions)
- [Acknowledgements](#acknowledgements)

---

## What this is

RootForgeKit bundles the tools a technician actually reaches for — hardware
health, system diagnostics and repair — into one window, instead of a drawer
full of separate CLIs.

Every tool button runs a **real command** and shows you the **real output and
exit code** in a console pane. Nothing is mocked, and nothing silently
"succeeds": if a command fails, you see that it failed and why.

There is **no account, no login, and no sign-in.** The app opens straight to
the tabs and every tab is available to everyone.

---

## Requirements

| | |
|---|---|
| **Python** | **3.10 or newer.** Verified on 3.12 and 3.13. No C compiler or Visual Studio Build Tools needed — every dependency ships as a prebuilt wheel. |
| **OS** | Windows 10/11 is the verified baseline. macOS and Linux launch, but the tool tabs are largely empty there (see [Platform support](#platform-support--the-honest-version)). |
| **Disk** | ~900 MB, almost all of it PySide6. |
| **Admin** | Not needed to start. Only the handful of tools that say so will prompt. |

Check your Python version:

```bash
python --version
```

If that prints `3.10` or higher, you're good. If it prints something older, or
`Python was not found`, see [Troubleshooting](#troubleshooting).

---

## Install and run

You'll need [Git](https://git-scm.com/downloads) and Python 3.10+.

### 1. Get the code

```bash
git clone https://github.com/NickHarrison96/RootForgeKit.git
cd RootForgeKit
```

### 2. Create a virtual environment

A virtual environment keeps RootForgeKit's packages separate from everything
else on your machine, so you can delete it later without side effects. **Do
this once**, then reuse the same folder every time you come back.

**Windows (PowerShell or Command Prompt):**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
```

Your prompt should change to show `(.venv)` at the front. That means it worked.

> **You'll need to activate the environment every time you open a new terminal
> window.** It's not permanent, by design — it stops packages leaking into your
> system Python.

### 3. Install the dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This installs 5 packages and takes a minute or two, mostly downloading Qt.

> **Watch for `Failed to build wheel`.** If you see that, stop and read
> [Troubleshooting](#troubleshooting) — it means something is compiling, and it
> shouldn't need to. You probably have an old `.venv` folder lying around.

### 4. Run it

```bash
python main.py
```

A dark window titled `RootForgeKit v0.5 (Pre-Alpha)` should open. That's it.

### 5. (Optional) Close the window without losing your packages

You can leave the environment activated, or deactivate it with:

```bash
deactivate
```

Next session: `cd` into the project folder, re-activate, and run `python main.py`.

---

## Using the app

There are four tabs along the top.

### 📊 Overview

Live identity for the machine you're on — OS and kernel, uptime, shell, CPU and
memory — next to a vector OS logo.

Six hardware spec cards on the right: **CPU, GPU, RAM, Storage, Network, and
Motherboard/BIOS.** They're floating sub-windows — drag a title bar to move one,
drag an edge to resize. The arrangement is saved and restored next launch. If
you make a mess, there's a **↺ Reset Layout** button.

### 🩺 Hardware Health

Battery telemetry, partition and storage breakdown, and SMART operational
status.

### 🔧 Tech Tools

Install and update applications, run diagnostics and repairs. Includes:

- **Disk health** — drive status via WMI
- **Network diagnostics** — full config plus listening ports
- **Process monitor** — top 20 processes by CPU usage
- **GPU details** — adapter, driver version, VRAM
- **Flush DNS cache**
- **Temp file cleanup**
- **System File Checker** — `sfc /scannow`
- **Chipset & GPU drivers** — detects your CPU and GPU vendor. Intel chipset
  drivers install directly; AMD and NVIDIA open the vendor's official download
  page, because the actual OEM drivers aren't available as installable packages.
- **Batch install profiles** — one click installs a whole preset via `winget`
  (Windows) or `brew` (macOS): *Gamer Essentials* (DirectX, VC++ runtimes,
  Discord, Steam, 7-Zip, MSI Afterburner) or *Tech & Diagnostic Utilities*
  (7-Zip, Notepad++, Wireshark, VS Code, Git, Python 3.12).

Apps already on the machine report their real state — **installed**, **update
available**, or **missing** — from a single background scan, and each button
relabels itself to match: *Install*, *Update*, or *Launch*.

### 🎮 Gamer Tools

Monitor the hardware, tune power and networking, and install the gaming
software set. Same console, same confirmation and elevation gates.

### The status bar

Always visible along the bottom. Left side shows readiness; the right side
shows your motherboard and host ID, read from SMBIOS on a background thread so
the window appears instantly.

---

## Do I need Administrator?

**No, not to run the app.** RootForgeKit launches unelevated on purpose —
forcing a UAC prompt on every launch, to cover the few tools that need it, was
pure friction.

Only these will ask for elevation, and only when you actually click them:

- System File Checker
- Enable WSL2
- Machine-scope installs (VC++ Redistributable, .NET, DirectX)
- "Upgrade all packages"

Everything else — disk health, network diagnostics, process list, GPU info,
DNS flush, temp cleanup and the Gamer Tools commands — was verified working
unelevated. If the app prompts you for something that isn't on that list, that's
a bug worth reporting.

---

## Where the app writes files

Nothing is written inside the project folder, so you can delete or reinstall
the source tree without losing data.

| What | Windows | macOS / Linux |
|---|---|---|
| Downloaded tooling (`adb`, `fastboot`) | `%LOCALAPPDATA%\RootForgeKit\bin\` | `~/.local/share/RootForgeKit/bin/` |
| Logs | `%LOCALAPPDATA%\RootForgeKit\logs\` | `~/.local/share/RootForgeKit/logs/` |
| Settings | `%APPDATA%\RootForgeKit\` | `~/.config/RootForgeKit/` |
| Backups / device output | `Documents\RootForgeKit\backups\` | `~/Documents/RootForgeKit/backups/` |

Settings go in the *roaming* profile on purpose, so they follow you between
work machines. Bulky downloads and logs go to *local* instead — a 15 MB SDK
shouldn't be synced by a roaming profile.

---

## Updating

```bash
git pull
pip install -r requirements.txt
```

Run the second command even if nothing changed. It's fast when everything is
already up to date, and it picks up new dependencies when the project adds
some.

---

## Starting over / uninstalling

**To reset the app's own data** (saved layouts, downloaded tools, logs):

- Windows: delete `%LOCALAPPDATA%\RootForgeKit` and `%APPDATA%\RootForgeKit`
- macOS / Linux: delete `~/.local/share/RootForgeKit` and `~/.config/RootForgeKit`

**To remove RootForgeKit completely:**

```bash
deactivate
rm -rf .venv          # Windows PowerShell: Remove-Item -Recurse -Force .venv
```

Then delete the project folder. Nothing is left installed on your system —
RootForgeKit only ever writes to the two per-user folders in the table above.

---

## Troubleshooting

### `ERROR: Failed to build wheel for lzfse` or `... for pylzss`

**The single most common install failure**, and it's caused by an **outdated
`.venv` folder, not by your machine.**

Those two packages are C extensions with no prebuilt Windows wheels for Python
3.13+. pip tries to compile them, needs Visual Studio Build Tools, doesn't find
them, and gives up.

They came in through `pymobiledevice3`, a dependency for iOS device support.
**That dependency is no longer used** — the iOS code lives in its own separate
project. So a fresh install shouldn't see these packages at all.

If you hit this, you have a `.venv` from before the fix. Throw it away:

```bash
deactivate
rm -rf .venv
```

Windows PowerShell:

```powershell
deactivate
Remove-Item -Recurse -Force .venv
```

Then start again at [step 2](#2-create-a-virtual-environment). And if you have
a copy of the old `requirements.txt` lying around, update it from the repo
first.

**Still failing after that?** You may have a global `pymobiledevice3` installed
from an earlier attempt. Check with `pip list | findstr pymobile` and, if it's
there, `pip uninstall pymobiledevice3`.

### `python` opens the Microsoft Store instead of running Python

Windows ships a `python.exe` stub that just launches the Store. Turn off the
aliases:

**Settings → Apps → Advanced app settings → App execution aliases** — turn
**both** `python.exe` and `python3.exe` to *Off*.

Then reopen your terminal and check `python --version` again.

### `'python' is not recognized` / `Python was not found`

Python isn't installed, or isn't on your PATH. Install it from
[python.org](https://www.python.org/downloads/) and **tick "Add python.exe to
PATH"** on the first screen of the installer.

If you installed it and it still isn't found, close and reopen your terminal —
the PATH change doesn't reach terminals that were already open.

### `ModuleNotFoundError: No module named 'PySide6'`

You're running the wrong Python — almost always you forgot to activate the
virtual environment. Your prompt should start with `(.venv)`. If it doesn't:

```bash
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # macOS / Linux
```

Then run `python main.py` again. Check with `python -c "import PySide6; print('ok')"`
— it should print `ok`.

### The app opens behind another window, or at the wrong size

It sizes itself to fit your screen but no larger. If it opens off-screen, delete
your saved layout and let it re-tile: `%LOCALAPPDATA%\RootForgeKit` and
`%APPDATA%\RootForgeKit`, then relaunch.

### Antivirus quarantines `RootForgeKit.exe`

Expected for an unsigned pre-alpha build. PyInstaller's output trips heuristic
scanners — a plain folder of DLLs trips them far less often than a single-file
bundle, which is one of the reasons this ships as a folder. If you're running
the packaged build, either allow it in your AV or run from source instead.

### A tool says it needs elevation and I already ran as Administrator

Some Windows services (notably LanmanServer) can be stopped, which breaks
naive "am I admin?" checks. RootForgeKit's admin detection doesn't use those,
so a spurious prompt is a bug — please report it with the tool name.

### PowerShell won't run a `.ps1` script

If you ever need to run one directly, the default execution policy blocks it:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This only affects the current terminal window.

---

## Building a standalone executable

Produces a folder (`dist\RootForgeKit\`) containing `RootForgeKit.exe` that runs
**without Python installed**. Zip that folder and ship the zip — keep the
executable and its DLLs together.

```bash
pip install -r requirements-dev.txt
python -m PyInstaller RootForgeKit.spec --noconfirm
```

This is a **onedir** build, deliberately not a single `.exe`:

- onefile unpacks ~150 MB of Qt to a temp folder on *every* launch — a
  multi-second startup delay with no window on screen
- onefile trips heuristic antivirus far more often
- that temp folder is deleted on exit, so anything written beside the exe is
  lost — which matters, because the app downloads `adb`/`fastboot` at runtime
- onedir is also what keeps the LGPL side of the PySide6 licensing intact, by
  leaving Qt's libraries separate and user-replaceable

The build is Windows-only as written. It's unsigned, so expect AV warnings.

---

## Project layout

```
main.py                 Entry point — builds the window, tabs, status bar
styles.qss              The entire dark theme
RootForgeKit.spec       PyInstaller build definition

tabs/                   One file per tab
  overview.py             System identity + hardware spec cards
  hardware/               Hardware Health tab
  tech_tools.py           Tech Tools
  gamer_tools.py          Gamer Tools
  tool_tab_base.py        Shared tool-card / console plumbing

components/             Reusable widgets
  status_bar.py           Persistent bottom bar
  tool_card.py            The clickable tool tile
  terminal_widget.py      Console output pane + command execution
  collapsible_section.py

utils/                  Platform logic, no UI
  command_builder.py      Tool definitions and the Windows command registry
  batch_installer.py      winget/brew preset profile installer
  elevation.py            UAC helpers
  paths.py                Where shipped files vs. written files live
  hwid.py                 SMBIOS hardware identity
  sys_info.py             OS/kernel/CPU/memory
  hardware_inspector.py   CPU, GPU, RAM, disk, battery
  hardware_vendor.py      CPU/GPU vendor detection for driver links
  os_logo.py              Vector OS logos
  host_inventory.py       Installed-application inventory
  resource_manager.py     Thread pool sizing, global crash handler

resources/              Icons and OS logos
bin/platform-tools/     adb/fastboot (gitignored — downloaded at runtime)
```

---

## Platform support — the honest version

**Windows is the real, tested platform.** Every tool in Tech Tools and Gamer
Tools is a Windows command, and the command registry
(`utils/command_builder.py`) returns **empty** on macOS and Linux.

That's deliberate. The macOS and Linux entries used to be guessed command
equivalents that had never been run on either platform. Shipping untested
guesses as if they were working tools is worse than showing an empty tab, so
they were removed and will be built out for real, one tool at a time, once
there's a way to test them.

The app itself does start on macOS and Linux — the tabs, the Overview cards and
the hardware inventory all work. It's the *tools* that are Windows-only.

---

## Recent revisions

The complete history lives in the internal `RevLog.md`, which is not committed.
Recent entries:

### 2026-09-27 — Tools work on a clean Windows machine again

Two separate things were breaking on a fresh install. Both were invisible on
the development machine, which is why they survived.

**1. The install itself failed.** `pymobiledevice3` was pulling in `pyimg4`,
which needs two C extensions (`lzfse` and `pylzss`) that have no prebuilt
Windows wheels for Python 3.13+. pip fell back to compiling them, had no
compiler available, and the install died. Neither package can be fixed upstream
on 3.13 — `lzfse` is at its final release with no 3.13 wheel, and even the
newest `pylzss` lacks a 64-bit Windows build for it.

- **Removed `pymobiledevice3` and `nest-asyncio` from the dependencies
  entirely.** Neither was imported by a single file in this repository — the
  iOS code moved to its own checkout, which owns its own dependency list. This
  takes the install from **111 packages to 5**, all pure prebuilt wheels, on any
  Python 3.10+. No compiler, no Build Tools, no multi-gigabyte detour.
- `RootForgeKit.spec` now skips its `pymobiledevice3` collection when the
  package isn't installed, instead of failing the whole build.
- `requirements.txt` documents the wheel-availability rule, so the next person
  to add a dependency has a way to check before it breaks the install.

**2. The Tech Tools WMI commands didn't exist any more.** Microsoft has been
retiring `wmic` for years — deprecated in Windows 10 21H2, disabled by default
in Windows 11 23H2/24H2, and **removed outright** as of the August 2026 update,
with no way to add it back. On a current Windows 11 install the executable
simply isn't on disk, so *Disk Health* and *GPU Details* failed with
`'wmic' is not recognized`.

- **Replaced every `wmic` call with PowerShell's `Get-CimInstance`**, the
  migration path Microsoft recommends. All 8 call sites: the two Tech Tools
  commands, the GPU list, the motherboard/BIOS card, the status-bar hardware
  ID, and GPU vendor detection. WMI itself was never the problem — only the
  command-line front-end Microsoft deleted.
- **This also fixed wrong data on machines where `wmic` still worked.**
  `wmic`'s CSV output doesn't quote values containing commas, so any
  motherboard made by MSI (and others) had every field after the first comma
  shifted by one. The status bar read `Micro-Star International Co. Ltd.` as
  the board name and reported the board's *product* name as its *serial
  number*; the BIOS version showed `LLC.` instead of the actual version.
  Results are now keyed by field name, so column order can't matter.

**3. README rewritten** for people who have never seen this project: what it
does, how to install it, what the errors mean, and where it puts your files.

### 2026-09-02 — Removed the auth server, login screen and tier gating

- **The app now opens straight to the tabs.** The login/register/guest splash,
  the self-hosted auth client, the HWID-bound session storage and the
  "Remember me" flow are gone. There is no sign-in and no sign-out.
- **Every tab is available to everyone.** The role gate and the Free/Paid/
  Diamond scaffolding were deleted with it.
- `requests` and `keyring` dropped from the dependencies.

### 2026-08-15 — v0.5: renamed to RootForgeKit, moved to PySide6, app icon

- **The project is now RootForgeKit**, by KushNick420 — "NicksFix"/"NixFix" was
  always a placeholder. Existing local settings and saved layouts read as empty
  after the rename; nothing is deleted, the old data just lives under the
  previous name.
- **Switched from PyQt6 to PySide6.** Same Qt 6, but LGPL instead of GPL, so the
  app can be distributed closed-source. The UI is deliberately unchanged — a
  binding swap, not a redesign.
- **Real app icon** across the taskbar, window, executable and shortcuts,
  replacing the placeholder emoji.
- **The auth server moved to its own private repository**, out of this checkout.

### Earlier

Core architecture, the Overview/Hardware/Tech/Gamer tab set, SMBIOS-based
status bar, hardware spec cards, iOS tool suites, batch package installers, and
the initial iForensics feature ports.

---

## Acknowledgements

The iOS/pymobiledevice3 work this project grew out of now lives in its own
checkout and is maintained separately — see
[pymobiledevice3](https://github.com/doronz88/pymobiledevice3).

iOS forensic features were originally ported from the iForensics Toolkit.
