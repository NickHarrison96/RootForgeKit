# 🚀 RootForgeKit // PRE ALPHA // 

**A cross-platform system utility, diagnostics and mobile-forensics suite.**
Windows · macOS · Linux — built with PySide6.
By KushNick420.

> ⚠️ **Super early-access, pre-alpha development build.** RootForgeKit is unfinished software under active development — expect bugs, breaking changes, half-built features, and rough edges. It is **not** production-ready. Use it on hardware you can afford to experiment with, back up your devices first, and proceed at your own risk. Feedback and issue reports are welcome.

---
RootForgeKit bundles the tools a technician actually reaches for — hardware health, system
repair, iOS and Android device work — into one dark-themed, 3uTools-inspired desktop app,
instead of a drawer full of separate CLIs.

---

## Features

**📊 Overview** — live OS/kernel/uptime/shell/CPU/memory identity beside a vector OS logo,
with hardware spec cards for CPU, GPU, RAM, storage, network and motherboard/BIOS.

**🩺 Hardware Health** — battery telemetry, partition/storage breakdown, and SMART
operational status reporting.

**⚙️ Prerequisites** — collapsible per-OS requirement checklists that install what's
missing, including auto-downloading Google Platform Tools (`adb`/`fastboot`) into a local
`bin/` and patching `PATH`.

**🔧 Tech Tools / 🎮 Gamer Tools** — disk health, network diagnostics, DNS flush, system
file checker, process monitor, GPU details, and batch silent-install profiles via `winget`
/ `brew`. A Windows/macOS/Linux target selector shows each platform's commands; commands
that can't run on the current host are shown for reference but blocked from executing.

**📱 iOS Tools** — full iOS 17+/18 support over a RemoteXPC **RSD tunnel**:
- Device control and settings over lockdown — restart/shutdown/sleep, device name, date,
  language, locale, battery vitals, Assistive Touch and WiFi toggles, activation status
- **Forensic acquisition** — Logical (mobilebackup2), Logical+ (backup + camera media +
  crash reports + app inventory → `.tar`), and PRFS
- **DVT instruments** — process list, screenshot, system monitor, location simulation,
  app launcher, power assertion
- Crash log explorer, files & apps manager, developer mode + DDI mounting, IPSW restore,
  live syslog streaming

**🤖 Android Tools** — device info, ADB file explorer, APK install, screenshot capture,
logcat streaming, reboot to bootloader/recovery, `adb` backup, and wireless ADB.

---

## Requirements

- **Python 3.10+**
- A physical device for the mobile features (iOS work needs Apple drivers; Android needs
  USB debugging enabled)
- **Administrator/root** is required only to create the iOS 17+ tunnel interface

## Getting started

```bash
git clone <your-repo-url>
cd RootForgeKit
```

```bash
python -m venv .venv
.venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Building a standalone executable (Windows)

`RootForgeKit.spec` produces a onedir PyInstaller bundle (`dist/RootForgeKit/RootForgeKit.exe`) that
doesn't need Python installed to run — see the comments in the spec for why onedir
rather than onefile:

```bash
pip install pyinstaller
python -m PyInstaller RootForgeKit.spec --noconfirm
```

### iOS 17+ setup

Developer services on iOS 17 and newer are only reachable through an RSD tunnel. In
**iOS Tools → Developer Setup & DDI**, work down the readiness panel: enable Developer
Mode, auto-mount the DDI, then start the tunnel (this prompts for elevation). When
"Developer services" reads green, the DVT tools are ready.

---

## Recent Revisions

### 2026-09-02 — Removed the auth server, login screen and tier gating
- **The app now opens straight to the tabs.** The login/register/guest splash, the
  self-hosted auth client (`utils/auth_client.py`), the HWID-bound session storage and
  the "Remember me" flow are gone. There is no sign-in and no sign-out.
- **Every tab is available to everyone.** Tech Tools and Gamer Tools no longer show a
  "Technician authentication required" lock — the role gate and the `utils/tiers.py`
  Free/Paid/Diamond scaffolding were deleted with it.
- **`requests` and `keyring` dropped** from `requirements.txt`, and the `keyring`
  hidden-import block is gone from the PyInstaller spec.
- The auth server in its separate private repository is untouched — it just has no
  client talking to it anymore.

### 2026-08-15 — Live public backend, over ngrok
- **The desktop app has a public backend to talk to again.** The auth server and a tunnel
  in front of it (`https://snore-borough-handball.ngrok-free.dev`) both run continuously
  on their own, restarting automatically at sign-in.
- **Fixed a caching bug** on the registration site where an already-open browser tab could
  keep showing an old version of the page after an update, instead of the current one.
- **Added "Remember me"** to the login screen. Leaving it unchecked now also clears any
  session a previous, checked login had already saved on that machine.

### 2026-08-15 — v0.5: renamed to RootForgeKit, moved to PySide6, app icon
- **The project is now RootForgeKit**, by KushNick420 — "NicksFix"/"NixFix" was always a
  placeholder. The build artefact is `RootForgeKit.exe`. Existing local settings and saved
  sessions read as empty after the rename; nothing is deleted, the old data just lives
  under the previous name.
- **Switched from PyQt6 to PySide6.** Same Qt 6, but LGPL instead of GPL, so the app can be
  distributed closed-source. The UI is deliberately unchanged — this was a binding swap,
  not a redesign. The build stays onedir so Qt's libraries remain separate and replaceable,
  as LGPL requires.
- **Real app icon** across the taskbar, window, executable and login screen, replacing the
  placeholder emoji.
- **The auth server moved to its own private repository.** It was never part of this
  checkout (the directory has always been gitignored); it now has version control of its
  own instead of none.

### 2026-08-11 — Containerised auth server, web registration page
- **Auth server runs as a container on its own host**, separate from the machine running
  the desktop app — registration, HWID binding and sign-in verified client-to-server over
  the network rather than on loopback.
- **Registration website** (`server/web/`) served by the auth server itself at `/web` —
  a dark landing page with a sign-up form, tools showcase and architecture notes. No build
  step and no framework; it ships as static files inside the image.
- **Accounts are created on the web, licences activate in the app.** Registration no longer
  needs a hardware ID; the licence binds to a machine on first desktop sign-in, which was
  already how enforcement worked.

### 2026-08-10 — iOS 17+ tunnel, lockdown control, acquisition modes, UI overhaul
- **iOS 17+ RemoteXPC/RSD tunnel support** — the prerequisite that unblocks every modern
  iOS developer service. Commands route through `tunneld` automatically.
- **Lockdown control panel** moved onto the iOS Tools primary tab — power control, device
  settings, battery vitals, feature toggles and activation in one place.
- **Forensic acquisition modes** — Logical, Logical+, PRFS, with FFS reporting its
  jailbreak/SSH requirement rather than silently degrading.
- **Long-running operations** now stream with live progress, elapsed time and cancel —
  and no fixed timeouts, which previously truncated backups and DDI mounts mid-flight.
- **Self-hosted auth & HWID licensing** — FastAPI + SQLite server, bcrypt + JWT, OS-keyring
  session storage, auto-login. Replaced the temporary debug login bypass.
- **UI density pass** — compact fixed-size tool tiles, resizable output panes, and a
  Windows/macOS/Linux target selector.
- **Vector OS logos** replaced misaligned ASCII art (Windows, macOS, Hackintosh, Linux).

### Earlier
Baseline application: core architecture and role-gated auth, persistent HWID status bar,
Overview/Hardware Health/Prerequisites/Tech/Gamer tabs, iOS and Android tool suites, batch
package installers, and the initial iForensics feature ports.

---

## Project status

**Pre-Alpha v0.5.** Actively developed. iOS features are verified against a physical iPad
on iOS 18.7.9; the macOS and Linux code paths are implemented but have had less hardware
testing than Windows.

## Acknowledgements

iOS device communication is powered by
[pymobiledevice3](https://github.com/doronz88/pymobiledevice3). Android tooling uses
Google's Platform Tools. iOS forensic features were ported from the iForensics Toolkit.
