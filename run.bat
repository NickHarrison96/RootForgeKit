@echo off
REM ===========================================================================
REM  RootForgeKit launcher
REM
REM  Double-click this file. It does the first-run setup for you:
REM    1. finds a usable Python
REM    2. creates an isolated .venv next to this script
REM    3. installs requirements.txt into it
REM    4. starts the app
REM
REM  Safe to run repeatedly -- setup is skipped once it already works, so
REM  launching the app later is just as fast as running main.py directly.
REM
REM  Why this exists: testers receive this project as a GitHub zip, and the
REM  usual first attempt is running main.py straight away. That fails with
REM  "ModuleNotFoundError: No module named 'psutil'" because nothing has been
REM  installed yet. This removes that step entirely.
REM ===========================================================================

setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "STAMP=%VENV_DIR%\.deps-ok"

echo.
echo  RootForgeKit launcher
echo  =====================
echo.

REM ---- 1. Locate a Python to build the environment with --------------------
set "BOOTSTRAP_PY="
where py >nul 2>&1
if not errorlevel 1 set "BOOTSTRAP_PY=py -3"
if defined BOOTSTRAP_PY goto :have_python

where python >nul 2>&1
if not errorlevel 1 set "BOOTSTRAP_PY=python"
if defined BOOTSTRAP_PY goto :have_python

echo  [X] No Python found.
echo.
echo      Python 3.10 or newer is required. Install it from:
echo        https://www.python.org/downloads/
echo.
echo      During setup, TICK "Add python.exe to PATH".
echo      Without that tick the installer cannot be found and this script
echo      cannot continue.
echo.
pause
exit /b 1

:have_python

REM ---- 2. Create the virtual environment once -------------------------------
if exist "%VENV_PY%" goto :have_venv

echo  [1/3] Creating an isolated Python environment ^(first run only^)...
%BOOTSTRAP_PY% -m venv "%VENV_DIR%"
if errorlevel 1 goto :venv_failed
echo      Done.
echo.

:have_venv

REM ---- 3. Install dependencies, but only when they are actually needed -----
REM  Reinstalling on every launch would add ~20s to a cold start and hit the
REM  network for no reason. The check below covers three things at once:
REM    - both packages importable
REM    - requirements.txt unchanged since the last successful install
REM    - a previous install actually completed
"%VENV_PY%" -c "import importlib.util as u, os, sys; ok = all(u.find_spec(m) for m in ('PySide6','psutil')); req = 'requirements.txt'; stamp = r'%STAMP%'; ok = ok and os.path.exists(stamp) and (not os.path.exists(req) or os.path.getmtime(req) <= os.path.getmtime(stamp)); sys.exit(0 if ok else 1)"
if not errorlevel 1 goto :deps_ready

echo  [2/3] Installing dependencies ^(first run only, needs internet^)...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :install_failed

REM  Written only after a clean install, so a failure part-way through does
REM  not leave a stamp that makes the next launch skip the install.
copy /b nul "%STAMP%" >nul
echo      Done.
echo.

:deps_ready
echo  [3/3] Starting RootForgeKit...
echo.

REM ---- 4. Run the app -------------------------------------------------------
"%VENV_PY%" main.py
set "APP_EXIT=%ERRORLEVEL%"

REM  A crash would otherwise scroll past and close the window, which looks
REM  exactly like the app hanging. Keep the console open so the error is
REM  actually readable.
if not "%APP_EXIT%"=="0" (
    echo.
    echo  RootForgeKit exited with code %APP_EXIT%.
    echo  The message above is the reason. Keeping this window open.
    echo.
    pause
)

endlocal & exit /b %APP_EXIT%

REM ---- Failure paths --------------------------------------------------------
:venv_failed
echo.
echo  [X] Could not create the Python environment.
echo      Another program may have .venv locked, or Python may be missing the
echo      "venv" module. Try running:  python -m venv .venv
echo.
pause
exit /b 1

:install_failed
echo.
echo  [X] Dependency installation failed.
echo      Scroll up for the failing package. Common causes:
echo        - no internet connection
echo        - proxy or firewall blocking pypi.org
echo        - Python older than 3.10
echo.
pause
exit /b 1
