# 🚀 NicksFix

**A cross-platform system utility, diagnostics and mobile-forensics suite.**
Windows · macOS · Linux — built with PyQt6.

NicksFix bundles the tools a technician actually reaches for — hardware health, system
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

**🔐 Optional self-hosted auth** — a FastAPI + SQLite licensing server with HWID binding
and OS-keyring session storage. Entirely optional; the app runs without it.

---

## Requirements

- **Python 3.10+**
- A physical device for the mobile features (iOS work needs Apple drivers; Android needs
  USB debugging enabled)
- **Administrator/root** is required only to create the iOS 17+ tunnel interface

## Getting started

```bash
git clone <your-repo-url>
cd NicksFix
```

**Windows**
```bash
start.bat
```

**macOS / Linux**
```bash
./start.sh
```

The launcher checks for Python, creates a `.venv`, syncs dependencies from
`requirements.txt`, and starts the app. To run it manually:

```bash
pip install -r requirements.txt && python main.py
```

### iOS 17+ setup

Developer services on iOS 17 and newer are only reachable through an RSD tunnel. In
**iOS Tools → Developer Setup & DDI**, work down the readiness panel: enable Developer
Mode, auto-mount the DDI, then start the tunnel (this prompts for elevation). When
"Developer services" reads green, the DVT tools are ready.

### Optional auth server

See [`server/README.md`](server/README.md) for running the licensing server and exposing it
via Cloudflare Tunnel. Skip it entirely to use the app in Guest mode.

---

## Recent Revisions

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

**Pre-Alpha v0.01.** Actively developed. iOS features are verified against a physical iPad
on iOS 18.7.9; the macOS and Linux code paths are implemented but have had less hardware
testing than Windows.

## Acknowledgements

iOS device communication is powered by
[pymobiledevice3](https://github.com/doronz88/pymobiledevice3). Android tooling uses
Google's Platform Tools. iOS forensic features were ported from the iForensics Toolkit.
