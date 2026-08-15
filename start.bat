@echo off
setlocal enabledelayedexpansion
:: ============================================================
:: NicksFix - Windows Bootstrap Launcher
:: Handles: Python 3.10+ check, .venv, pip sync, launch
::
:: VERBOSE BY DESIGN: every step below narrates what it's doing and
:: what it found (paths, versions, hashes, candidates tried) instead
:: of only speaking up on failure. This is deliberate -- a tester
:: reporting "it didn't work" is far more useful to debug when the
:: window in front of them already shows exactly which Python was
:: picked, which venv path was used, and what the hash comparison
:: decided, rather than nothing but silence until an [ERROR] line.
::
:: ELEVATION: this launcher does NOT request Administrator, on
:: purpose. NicksFix runs unelevated (see utils/elevation.py) so
:: it doesn't fire a UAC prompt on every single launch -- the
:: ~90% of sessions that never touch an admin-only tool shouldn't
:: pay for the few that do. The handful of tools that genuinely
:: need admin (SFC, DISM, machine-scope winget, Windows
:: activation) offer to relaunch elevated at the moment they're
:: clicked, via components/terminal_widget.py. Do not "helpfully"
:: add a `runas` relaunch here -- it re-breaks that whole design
:: and brings back the UAC-on-every-launch friction.
::
:: NOTE: this script runs with DELAYED EXPANSION enabled, so any
:: variable that is both SET and READ inside the same ( ) block
:: must use !VAR! and not %VAR%. Batch expands %VAR% once, when it
:: parses the whole block -- so a %VAR% read inside a block sees
:: the value from BEFORE the block ran. That exact mistake made
:: this script silently skip installing dependencies no matter
:: what the user typed. Do not "simplify" !VAR! back to %VAR%.
:: ============================================================
title NicksFix Launcher
color 0A

echo ============================================================
echo   NicksFix Launcher
echo ============================================================

:: Always operate on the folder this script lives in, never the
:: caller's current directory, so every relative path below is
:: resolved against the project folder regardless of how the
:: script was started.
cd /d "%~dp0"
echo [i] Working directory: %CD%

:: Sentinel module used to prove dependencies are actually usable,
:: not just that pip reported success at some point in the past.
set "SENTINEL_IMPORT=PyQt6"

:: ---- Step 1: Sanity-check we are actually in the project folder ----
echo.
echo [STEP 1/5] Checking project folder...
if not exist "main.py" (
    echo [ERROR] main.py not found in "%CD%".
    echo         Keep start.bat inside the NicksFix project folder.
    pause
    exit /b 1
)
echo [i] Found main.py
if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found in "%CD%".
    echo         The download looks incomplete - re-extract the project.
    pause
    exit /b 1
)
echo [i] Found requirements.txt
echo [OK] Project folder looks correct.

:: ---- Step 2: Locate a usable Python 3.10+ ----
:: Each candidate is VALIDATED by actually running it, rather than
:: trusting `where`. On a fresh Windows install `where python`
:: succeeds even with no Python installed, because Windows ships an
:: App Execution Alias stub that just opens the Microsoft Store --
:: it resolves on PATH, then fails to execute anything.
echo.
echo [STEP 2/5] Locating Python 3.10+...
set "PYTHON_CMD="
call :try_python "py -3"
if not defined PYTHON_CMD call :try_python "python"
if not defined PYTHON_CMD call :try_python "python3"

:: On a genuinely fresh machine (no Python at all) this is what makes the
:: whole thing "just work" in one launch instead of sending the user to a
:: browser: Windows 11 ships winget in-box, so use it to install Python
:: silently and pick straight back up, rather than stopping here.
if not defined PYTHON_CMD (
    echo [i] No usable Python found on PATH.
    call :try_auto_install_python
)

if not defined PYTHON_CMD (
    echo.
    echo [ERROR] No working Python 3.10+ installation was found, and automatic
    echo         setup could not install one.
    echo.
    echo   Install Python from:  https://www.python.org/downloads/
    echo   IMPORTANT: tick "Add python.exe to PATH" in the installer.
    echo.
    echo   If you installed Python from the Microsoft Store and still
    echo   see this, open Settings ^> Apps ^> Advanced app settings ^>
    echo   App execution aliases and turn OFF the python.exe aliases,
    echo   then install from python.org instead.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('!PYTHON_CMD! --version 2^>^&1') do set "PY_VER=%%v"
for /f "tokens=*" %%p in ('!PYTHON_CMD! -c "import sys; print(sys.executable)" 2^>^&1') do set "PY_PATH=%%p"
echo [OK] Selected interpreter: "!PYTHON_CMD!"
echo      Version: !PY_VER!
echo      Path:    !PY_PATH!

:: ---- Step 3: Create / verify the virtual environment ----
:: Check for the interpreter itself, not just the .venv folder -- an
:: interrupted first run leaves a .venv directory that exists but has
:: no Python in it, which the old folder-only check happily accepted.
echo.
echo [STEP 3/5] Preparing virtual environment...
set "VENV_PY=.venv\Scripts\python.exe"
for %%P in ("!VENV_PY!") do set "VENV_PY_ABS=%%~fP"
echo [i] venv interpreter path: !VENV_PY_ABS!

if not exist "!VENV_PY!" (
    if exist ".venv" (
        echo [*] Existing .venv looks incomplete ^(missing python.exe^) - rebuilding it...
        rmdir /s /q ".venv"
        echo [i] Removed old .venv directory.
    ) else (
        echo [i] No .venv directory yet.
    )
    echo [*] Creating virtual environment with "!PYTHON_CMD! -m venv .venv" ...
    !PYTHON_CMD! -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
    echo [i] venv creation command exited 0.
) else (
    echo [i] .venv already has a python.exe - reusing it.
)

if not exist "!VENV_PY!" (
    echo [ERROR] Virtual environment created but "!VENV_PY!" is missing.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('"!VENV_PY!" --version 2^>^&1') do set "VENV_PY_VER=%%v"
echo [OK] Virtual environment ready. ^(!VENV_PY_VER!^)

:: ---- Step 4: Install dependencies when they are actually needed ----
:: Two independent triggers, because either alone is not enough:
::   1. requirements.txt changed since the last successful install
::   2. the sentinel package does not import (fresh venv, failed or
::      partial install, someone deleted site-packages, etc.)
:: No Y/N prompt: a tester answering "n" -- or just pressing Enter --
:: previously produced an app that launches straight into an
:: ImportError. Installing is the only correct action when deps are
:: missing, so it is not phrased as a question.
echo.
echo [STEP 4/5] Checking dependencies...
set "REQ_HASH_FILE=.venv\requirements.hash"

set "NEW_HASH="
for /f "delims=" %%h in ('certutil -hashfile requirements.txt SHA256 ^| findstr /v "hash"') do (
    if not defined NEW_HASH set "NEW_HASH=%%h"
)

set "OLD_HASH="
if exist "!REQ_HASH_FILE!" (
    set /p OLD_HASH=<"!REQ_HASH_FILE!"
) else (
    echo [i] No previous install-hash on record ^(first run, or .venv was rebuilt^).
)

echo [i] requirements.txt hash ^(current^):  !NEW_HASH!
echo [i] requirements.txt hash ^(recorded^): !OLD_HASH!

set "DEPS_OK=0"
if defined NEW_HASH if "!NEW_HASH!"=="!OLD_HASH!" set "DEPS_OK=1"
if "!DEPS_OK!"=="1" (
    echo [i] Hash matches - requirements.txt has not changed since the last install.
) else (
    echo [i] Hash differs - requirements.txt changed, or this is a fresh venv.
)

"!VENV_PY!" -c "import !SENTINEL_IMPORT!" >nul 2>&1
if errorlevel 1 (
    set "DEPS_OK=0"
    echo [i] Sentinel check: !SENTINEL_IMPORT! is NOT importable in this venv.
) else (
    echo [i] Sentinel check: !SENTINEL_IMPORT! imports fine in this venv.
)

if "!DEPS_OK!"=="1" (
    echo [OK] Dependencies already up to date - skipping install.
) else (
    echo.
    echo [*] Installing Python dependencies...
    echo     First run downloads ~100 MB and can take several minutes.
    echo     Leave this window open until it finishes.
    echo.
    "!VENV_PY!" -m pip install --upgrade pip
    for /f "tokens=*" %%v in ('"!VENV_PY!" -m pip --version 2^>^&1') do set "PIP_VER=%%v"
    echo [i] !PIP_VER!
    echo.
    echo [*] Running: pip install -r requirements.txt
    "!VENV_PY!" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Dependency installation failed.
        echo         Check your internet connection and run start.bat again.
        pause
        exit /b 1
    )
    > "!REQ_HASH_FILE!" echo !NEW_HASH!
    echo [i] Recorded new requirements hash to "!REQ_HASH_FILE!".
    echo [OK] Dependencies installed.
    echo.
    echo [i] Installed packages:
    "!VENV_PY!" -m pip list
)

:: ---- Step 4b: Prove the app can actually import its dependencies ----
:: pip exiting 0 is not the same thing as the app being runnable.
echo.
echo [i] Verifying !SENTINEL_IMPORT! actually imports post-install...
"!VENV_PY!" -c "import !SENTINEL_IMPORT!" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] !SENTINEL_IMPORT! still cannot be imported after installing.
    echo         Full error:
    "!VENV_PY!" -c "import !SENTINEL_IMPORT!"
    pause
    exit /b 1
)
echo [OK] !SENTINEL_IMPORT! import verified.

:: ---- Step 5: Launch NicksFix (unelevated - see header) ----
echo.
echo [STEP 5/5] Launching NicksFix...
echo [i] Command: "!VENV_PY_ABS!" main.py
echo ============================================================
echo   Launching NicksFix...
echo ============================================================
echo.
"!VENV_PY!" main.py
set "APP_EXIT=%errorlevel%"
echo.
echo [i] NicksFix exited with code !APP_EXIT!.
if not "!APP_EXIT!"=="0" (
    echo [ERROR] NicksFix exited with an error.
    pause
)
exit /b 0

:: ============================================================
:: :try_python  "<command>"
:: Sets PYTHON_CMD if the candidate runs AND is version 3.10+.
:: Validating by execution is what catches the Microsoft Store
:: alias stub, Python 2, and broken PATH entries. Narrates every
:: candidate it tries and why it was accepted or rejected.
:: ============================================================
:try_python
set "CANDIDATE=%~1"
echo [i] Trying "!CANDIDATE!" ...
%CANDIDATE% -c "print(1)" >nul 2>&1
if errorlevel 1 (
    echo      not found / not runnable ^(likely missing, or a Microsoft Store alias stub^).
    exit /b 1
)
for /f "tokens=*" %%v in ('%CANDIDATE% --version 2^>^&1') do set "CANDIDATE_VER=%%v"
%CANDIDATE% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo      found !CANDIDATE_VER!, but 3.10+ is required - skipping.
    exit /b 1
)
echo      found !CANDIDATE_VER! - using this one.
set "PYTHON_CMD=%~1"
exit /b 0

:: ============================================================
:: :try_auto_install_python
:: Fresh-machine bootstrap: no usable Python was found, so install
:: one and keep going -- no "go download Python and re-run me".
::
:: WHY PrependPath=1 IS NOT OPTIONAL: the python.org installer does
:: NOT put python.exe on PATH unless explicitly told to, and the
:: winget manifest for Python.Python.3.12 declares no installer
:: switches of its own (confirmed with `winget show`). So a plain
:: `winget install Python.Python.3.12` genuinely succeeds and still
:: leaves PATH untouched -- which is exactly the failure seen on a
:: fresh Win11 VM: "[OK] installed via winget" immediately followed
:: by "still cannot be found". Passing the installer arguments
:: through --custom is what actually makes it land on PATH.
::
:: THREE INDEPENDENT LAYERS, because any one of them can fail on a
:: machine we can't see:
::   1. install with PrependPath=1 (fixes PATH at the source)
::   2. re-read PATH from the registry, since an installer cannot
::      update THIS already-running process's environment block
::   3. if it's still not on PATH, look for python.exe directly in
::      the standard install folders, then persist that folder to
::      the user PATH ourselves
:: Layer 3 is the one that makes this robust: it does not care
:: whether the installer, winget, or the registry cooperated.
::
:: If winget is missing or fails outright, fall back to downloading
:: the official installer from python.org and running it with the
:: same flags. Old Win11 images ship winget 1.2, which is why we
:: stick to long-supported flags (-e, --silent, --custom,
:: --accept-*) and never assume a modern winget.
::
:: Never sets PYTHON_CMD on failure -- the caller's manual-install
:: error message stays the last resort, so a machine that already
:: has Python is completely unaffected by any of this.
:: ============================================================
:try_auto_install_python
set "PY_SERIES=3.12"
set "PY_FULL=3.12.10"

winget --version >nul 2>&1
if errorlevel 1 (
    echo [i] winget is not available on this machine.
    goto :py_direct_download
)
for /f "tokens=*" %%v in ('winget --version 2^>^&1') do set "WINGET_VER=%%v"
echo [*] winget !WINGET_VER! found - installing Python !PY_SERIES! automatically...
echo     One-time setup on a fresh machine; may take a minute or two.
echo.
winget install --id Python.Python.!PY_SERIES! -e --silent --accept-package-agreements --accept-source-agreements --custom "InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1"
if errorlevel 1 (
    echo [i] winget could not install Python - falling back to a direct download.
    goto :py_direct_download
)
echo [OK] winget reported Python !PY_SERIES! installed.
goto :py_after_install

:py_direct_download
echo.
echo [*] Downloading the official Python !PY_FULL! installer from python.org...
set "PY_DL=%TEMP%\nicksfix-python-setup.exe"
set "PY_DL_URL=https://www.python.org/ftp/python/!PY_FULL!/python-!PY_FULL!-amd64.exe"
:: TLS 1.2 is forced because Windows PowerShell 5.1 does not always
:: negotiate it by default, and python.org refuses anything older.
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri $env:PY_DL_URL -OutFile $env:PY_DL"
if not exist "!PY_DL!" (
    echo [i] Could not download the Python installer ^(no internet connection?^).
    exit /b 1
)
echo [*] Running the Python installer silently ^(this adds it to PATH^)...
"!PY_DL!" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
echo [i] Python installer exited with code !errorlevel!.
del "!PY_DL!" >nul 2>&1

:py_after_install
echo [*] Refreshing this session's PATH so the new install is visible...
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%p"

call :try_python "py -3"
if not defined PYTHON_CMD call :try_python "python"
if not defined PYTHON_CMD call :try_python "python3"
if defined PYTHON_CMD exit /b 0

echo [i] Still not on PATH - searching the standard install folders directly...
call :find_python_on_disk
if not defined PYTHON_CMD (
    echo [i] Python still could not be located after installing.
    exit /b 1
)
exit /b 0

:: ============================================================
:: :find_python_on_disk
:: Last-resort locator: ignore PATH entirely and look where the
:: python.org installer actually puts things. This is what saves the
:: run when an installer silently declines to touch PATH.
:: Sets PYTHON_CMD (and persists the folder to the user PATH).
:: ============================================================
:find_python_on_disk
set "FOUND_PY="
set "FOUND_DIR="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :consider_python_dir "%%D"
for /d %%D in ("%ProgramFiles%\Python3*")                 do call :consider_python_dir "%%D"
for /d %%D in ("C:\Python3*")                             do call :consider_python_dir "%%D"
if not defined FOUND_PY exit /b 1
set "PYTHON_CMD=!FOUND_PY!"
echo [OK] Located Python at: !FOUND_DIR!
call :persist_python_path "!FOUND_DIR!"
exit /b 0

:: ------------------------------------------------------------
:: :consider_python_dir "<dir>"  -- validate one candidate folder.
:: The 8.3 short path (%%~sF) is used so the resulting command has
:: no spaces in it, which keeps every later `for /f` and direct
:: invocation free of quoting problems (e.g. C:\Program Files\...).
:: Keeps the LAST match, so a higher Python3xx folder wins.
:: ------------------------------------------------------------
:consider_python_dir
set "CAND_DIR=%~1"
if not exist "!CAND_DIR!\python.exe" exit /b 0
for %%F in ("!CAND_DIR!\python.exe") do set "CAND_EXE=%%~sF"
!CAND_EXE! -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
for /f "tokens=*" %%v in ('!CAND_EXE! --version 2^>^&1') do set "CAND_VER=%%v"
echo      candidate: !CAND_DIR!  ^(!CAND_VER!^)
set "FOUND_PY=!CAND_EXE!"
set "FOUND_DIR=!CAND_DIR!"
exit /b 0

:: ------------------------------------------------------------
:: :persist_python_path "<dir>"
:: Adds the Python folder (and its Scripts folder) to the user's
:: PATH permanently, so the next launch -- and every other program
:: the user opens -- can find Python too. Written via .NET rather
:: than `setx`, because setx silently TRUNCATES PATH at 1024
:: characters, which would corrupt the user's environment.
:: Also updates this process's PATH so the rest of this run works.
:: ------------------------------------------------------------
:persist_python_path
set "NEWPYDIR=%~1"
echo [*] Adding Python to your PATH for future sessions...
:: Entries are compared case-insensitively and with trailing slashes
:: trimmed -- Windows writes these paths inconsistently (the python.org
:: installer adds a trailing backslash), and a naive compare would
:: append a duplicate PATH entry on every single run.
powershell -NoProfile -Command "$d=$env:NEWPYDIR.TrimEnd('\'); $p=[Environment]::GetEnvironmentVariable('Path','User'); if(-not $p){$p=''}; $has=$false; foreach($e in $p.Split(';')){ if($e.Trim().TrimEnd('\') -ieq $d){$has=$true} }; if(-not $has){ $new=($p.TrimEnd(';')+';'+$d+';'+$d+'\Scripts').TrimStart(';'); [Environment]::SetEnvironmentVariable('Path',$new,'User'); Write-Host '     [OK] Added to your user PATH.' } else { Write-Host '     [i] Already present on your user PATH.' }"
set "PATH=!NEWPYDIR!;!NEWPYDIR!\Scripts;!PATH!"
exit /b 0
