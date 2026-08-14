#!/usr/bin/env bash
# ============================================================
# NicksFix — Unix Bootstrap Launcher (macOS / Linux)
# Handles: Sudo elevation, Python 3.10+ check, .venv, pip sync
# ============================================================
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[*]${NC} $1"; }
ok()      { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
fail()    { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  NicksFix — System Utility & Diagnostic Suite"
echo "============================================================"
echo ""

# ---- Step 1: Check for root/sudo privileges ----
if [ "$EUID" -ne 0 ]; then
    warn "NicksFix requires elevated privileges for system tools."
    info "Re-launching with sudo..."
    exec sudo bash "$0" "$@"
fi
ok "Running with elevated privileges."

# ---- Step 2: Locate Python 3.10+ ----
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    fail "Python 3.10+ is required but not found.\n       Install from: https://www.python.org/downloads/"
fi

PY_VER=$("$PYTHON_CMD" --version 2>&1)
ok "Found $PY_VER"

# ---- Step 3: Create / Activate Virtual Environment ----
if [ ! -d ".venv" ]; then
    info "Creating virtual environment (.venv)..."
    "$PYTHON_CMD" -m venv .venv || fail "Failed to create virtual environment."
    ok "Virtual environment created."
else
    ok "Virtual environment already exists."
fi

source .venv/bin/activate
ok "Virtual environment activated."

# ---- Step 4: Prompt to install dependencies ----
echo ""
read -rp "[?] Install/update Python dependencies from requirements.txt? [Y/N]: " INSTALL_DEPS
if [[ "$INSTALL_DEPS" =~ ^[Yy]$ ]]; then
    info "Installing dependencies..."
    pip install --upgrade pip > /dev/null 2>&1
    if pip install -r requirements.txt; then
        ok "All dependencies installed successfully."
    else
        warn "Some dependencies may have failed to install."
    fi
else
    info "Skipping dependency installation."
fi

# ---- Step 5: Launch NicksFix ----
echo ""
echo "============================================================"
echo "  Launching NicksFix..."
echo "============================================================"
echo ""
python main.py
