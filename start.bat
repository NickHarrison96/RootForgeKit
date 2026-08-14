@echo off
:: ============================================================
:: NicksFix — Windows Bootstrap Launcher
:: Handles: Admin elevation, Python 3.10+ check, .venv, pip sync
:: ============================================================
title NicksFix Launcher
color 0A

:: ---- Step 1: Check for Administrator privileges ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] NicksFix requires Administrator privileges.
    echo [*] Requesting elevation...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)
echo [OK] Running as Administrator.

:: ---- Step 2: Locate Python 3.10+ ----
set PYTHON_CMD=
where py >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python 3 not found. Please install Python 3.10 or newer.
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Verify version >= 3.10
%PYTHON_CMD% -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.10+ is required. Current version:
    %PYTHON_CMD% --version
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set PY_VER=%%v
echo [OK] Found %PY_VER%

:: ---- Step 3: Create / Activate Virtual Environment ----
if not exist ".venv" (
    echo [*] Creating virtual environment .venv...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

call .venv\Scripts\activate.bat
echo [OK] Virtual environment activated.

:: ---- Step 4: Install dependencies only if requirements.txt actually changed ----
:: Hash-gated so this stops asking every single launch once deps are already
:: satisfied -- only prompts when requirements.txt differs from the last
:: successful install (tracked via a hash file inside .venv).
set "REQ_HASH_FILE=.venv\requirements.hash"
set "NEW_HASH="
for /f "delims=" %%h in ('certutil -hashfile requirements.txt SHA256 ^| findstr /v "hash"') do set "NEW_HASH=%%h"

set "OLD_HASH="
if exist "%REQ_HASH_FILE%" set /p OLD_HASH=<"%REQ_HASH_FILE%"

set "DEPS_UP_TO_DATE=0"
if not "%NEW_HASH%"=="" if "%NEW_HASH%"=="%OLD_HASH%" set "DEPS_UP_TO_DATE=1"

if "%DEPS_UP_TO_DATE%"=="1" (
    echo [OK] Dependencies already up to date, skipping install.
) else (
    echo.
    echo [?] Install/update Python dependencies from requirements.txt?
    set /p INSTALL_DEPS="    Type Y to install, N to skip [Y/N]: "
    if /i "%INSTALL_DEPS%"=="Y" (
        echo [*] Installing dependencies...
        pip install --upgrade pip >nul 2>&1
        pip install -r requirements.txt
        if %errorlevel% neq 0 (
            echo [WARNING] Some dependencies may have failed to install.
        ) else (
            echo [OK] All dependencies installed successfully.
            >"%REQ_HASH_FILE%" echo %NEW_HASH%
        )
    ) else (
        echo [*] Skipping dependency installation.
    )
)

:: ---- Step 5: Launch NicksFix ----
echo.
echo ============================================================
echo   Launching NicksFix...
echo ============================================================
echo.
python main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] NicksFix exited with an error.
    pause
)
