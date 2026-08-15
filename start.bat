@echo off
setlocal enabledelayedexpansion
:: ============================================================
:: NixFix - Windows Bootstrap Launcher
:: Handles: Python 3.13 check, .venv creation, pip sync, launch
::
:: PREREQUISITES (fresh Windows install):
::   1. Python 3.13  -- from the Microsoft Store or via winget
::      This script will attempt to install it automatically via
::      winget (Step 0b).  If that fails, install manually:
::        Microsoft Store -> search "Python 3.13" (by PSF)
::        OR: winget install Python.Python.3.13
::
::   2. Microsoft C++ Build Tools  (for compiling native wheels)
::      If pip install fails with a compiler error, install from:
::        https://visualstudio.microsoft.com/visual-cpp-build-tools/
::      Select "Desktop development with C++" in the installer.
::
::   3. MSYS2/MINGW64 (build-time only, if a dep needs unix tools)
::      Install from https://www.msys2.org/ if pip mentions it.
::      Not required at app runtime.
::
:: VERBOSE BY DESIGN: every step narrates what it found (paths,
:: versions, candidates tried) so a "it didn't work" report
:: already shows exactly what was tried and why it was rejected.
::
:: ELEVATION: this launcher does NOT request Administrator.
:: NixFix runs unelevated (see utils/elevation.py) -- tools that
:: genuinely need admin relaunch themselves at click time via
:: components/terminal_widget.py.  Do not add a `runas` here.
::
:: NOTE: DELAYED EXPANSION is enabled.  Variables SET and READ
:: inside the same ( ) block must use !VAR! not %VAR%.
:: ============================================================
title NixFix Launcher
color 0A

echo ============================================================
echo   NixFix Launcher
echo ============================================================

cd /d "%~dp0"
echo [i] Working directory: %CD%

set "SENTINEL_IMPORT=PyQt6"

:: ---- Step 0b: Attempt to ensure Python 3.13 is installed via winget ----
:: Best-effort pre-install before the Python probe.  If winget is
:: unavailable or Python is already present this block is a no-op.
echo.
echo [STEP 0b/5] Ensuring Python 3.13 is installed (winget)...
winget --version >nul 2>&1
if errorlevel 1 (
    echo [i] winget not available - skipping auto-install of Python 3.13.
    echo     Install Python 3.13 manually from the Microsoft Store if needed.
) else (
    for /f "tokens=*" %%v in ('winget --version 2^>^&1') do set "WINGET_VER=%%v"
    echo [i] winget !WINGET_VER! found - running: winget install Python.Python.3.13
    winget install --id Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [i] winget install exited non-zero ^(already installed, or transient error^).
        echo     Continuing - Step 2 will probe for a usable interpreter.
    ) else (
        echo [OK] winget reported Python 3.13 installed ^(or already present^).
        :: Refresh PATH so this session can see the newly installed python.exe
        for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%p"
    )
)

:: ---- Step 1: Sanity-check we are in the project folder ----
echo.
echo [STEP 1/5] Checking project folder...
if not exist "main.py" (
    echo [ERROR] main.py not found in "%CD%".
    echo         Keep start.bat inside the NixFix project folder.
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

:: ---- Step 2: Locate a usable Python 3.13 ----
:: Probe order:
::   py -3.13        -- Python Launcher for Windows (covers Store installs)
::   py -3           -- any 3.x via launcher
::   python / python3 -- PATH-based
::   WindowsApps     -- Store Python's real exe location
::   Program Files   -- standard user/system install paths
::
:: The Microsoft Store app execution alias stubs (python.exe /
:: python3.exe in %LOCALAPPDATA%\Microsoft\WindowsApps) look like
:: real executables on PATH but open the Store when run.
:: :try_python catches these by actually running python -c "print(1)"
:: and checking the exit code; the stubs exit non-zero.
echo.
echo [STEP 2/5] Locating Python 3.13+...
set "PYTHON_CMD="
call :try_python "py -3.13"
if not defined PYTHON_CMD call :try_python "py -3"
if not defined PYTHON_CMD call :try_python "python"
if not defined PYTHON_CMD call :try_python "python3"

if not defined PYTHON_CMD (
    echo [i] No usable Python found via PATH or launcher - scanning disk...
    call :find_python_on_disk
)

if not defined PYTHON_CMD (
    echo.
    echo [ERROR] Python 3.13 was not found on this machine.
    echo.
    echo   This app requires Python 3.13 from the Microsoft Store.
    echo.
    echo   HOW TO INSTALL:
    echo     1. Open the Microsoft Store
    echo     2. Search for "Python 3.13"
    echo     3. Install the official app by Python Software Foundation
    echo     4. Re-run start.bat
    echo.
    echo   NOTE: Do NOT install Python from python.org on this machine.
    echo   The Store version is required for compatibility.
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
    echo     Some packages compile native C extensions -- Microsoft C++
    echo     Build Tools are required if any wheel needs to compile.
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
        echo.
        echo   Common causes on a fresh Windows install:
        echo     - C++ Build Tools missing
        echo     - No internet connection
        echo     - Pip tried to compile a wheel without MSYS2/MINGW64
        echo.
        echo   If the error mentions a compiler or cl.exe:
        echo     Install Microsoft C++ Build Tools from:
        echo       https://visualstudio.microsoft.com/visual-cpp-build-tools/
        echo     Select "Desktop development with C++" in the installer.
        echo.
        echo   If the error mentions MSYS2 or a unix tool:
        echo     Install MSYS2 from https://www.msys2.org/
        echo     Then open MSYS2 MINGW64 and run: pacman -Syu
        echo.
        pause
        exit /b 1
    )
    >"!REQ_HASH_FILE!" echo !NEW_HASH!
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

:: ---- Step 5: Launch NixFix (unelevated - see header) ----
echo.
echo [STEP 5/5] Launching NixFix...
echo [i] Command: "!VENV_PY_ABS!" main.py
echo ============================================================
echo   Launching NixFix...
echo ============================================================
echo.
"!VENV_PY!" main.py
set "APP_EXIT=%errorlevel%"
echo.
echo [i] NixFix exited with code !APP_EXIT!.
if not "!APP_EXIT!"=="0" (
    echo [ERROR] NixFix exited with an error.
    pause
)
exit /b 0

:: ============================================================
:: :try_python  "<command>"
:: Sets PYTHON_CMD if the candidate runs AND is version 3.13+.
:: Validates by actually executing -- this is what catches the
:: Microsoft Store alias stubs, Python 2, and broken PATH entries.
:: The Store alias stubs resolve on PATH but exit non-zero when
:: actually run, so the errorlevel check weeds them out.
:: ============================================================
:try_python
set "CANDIDATE=%~1"
echo [i] Trying "!CANDIDATE!" ...
%CANDIDATE% -c "print(1)" >nul 2>&1
if errorlevel 1 (
    echo      not found / not runnable ^(or a Microsoft Store alias stub^).
    exit /b 1
)
for /f "tokens=*" %%v in ('%CANDIDATE% --version 2^>^&1') do set "CANDIDATE_VER=%%v"
%CANDIDATE% -c "import sys; sys.exit(0 if sys.version_info >= (3,13) else 1)" >nul 2>&1
if errorlevel 1 (
    echo      found !CANDIDATE_VER!, but 3.13+ is required - skipping.
    exit /b 1
)
echo      found !CANDIDATE_VER! - using this one.
set "PYTHON_CMD=%~1"
exit /b 0

:: ============================================================
:: :find_python_on_disk
:: Last-resort locator: ignores PATH entirely and scans the
:: known install locations for the MS Store Python and the
:: standard python.org user/system install paths.
::
:: MS Store Python 3.13 real executable locations:
::   %LOCALAPPDATA%\Microsoft\WindowsApps\python3.13.exe
::     -- the "app alias" that actually works (distinct from the
::        stub python.exe / python3.exe in the same folder)
::   %LOCALAPPDATA%\Programs\Python\Python313\python.exe
::     -- where the Store installer copies the real binaries
::
:: The 8.3 short path (%%~sF) is used so the resulting command
:: has no spaces, keeping every later `for /f` and direct
:: invocation free of quoting problems (e.g. C:\Program Files).
:: Keeps the LAST match, so a higher Python3xx folder wins.
:: ============================================================
:find_python_on_disk
set "FOUND_PY="
set "FOUND_DIR="

:: MS Store Python 3.13 -- the named alias exe that actually runs
set "STORE_ALIAS=%LOCALAPPDATA%\Microsoft\WindowsApps\python3.13.exe"
echo [i] Checking MS Store alias: !STORE_ALIAS!
if exist "!STORE_ALIAS!" (
    "!STORE_ALIAS!" -c "print(1)" >nul 2>&1
    if not errorlevel 1 (
        "!STORE_ALIAS!" -c "import sys; sys.exit(0 if sys.version_info >= (3,13) else 1)" >nul 2>&1
        if not errorlevel 1 (
            for %%F in ("!STORE_ALIAS!") do set "FOUND_PY=%%~sF"
            set "FOUND_DIR=%LOCALAPPDATA%\Microsoft\WindowsApps"
            echo      [OK] MS Store python3.13.exe alias is functional.
        )
    ) else (
        echo      MS Store python3.13.exe alias exists but is a non-functional stub.
    )
)

:: Standard user install path (Store and python.org both use this)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python313*") do call :consider_python_dir "%%D"
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*")   do call :consider_python_dir "%%D"
for /d %%D in ("%ProgramFiles%\Python3*")                   do call :consider_python_dir "%%D"
for /d %%D in ("C:\Python3*")                               do call :consider_python_dir "%%D"

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
!CAND_EXE! -c "import sys; sys.exit(0 if sys.version_info >= (3,13) else 1)" >nul 2>&1
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
