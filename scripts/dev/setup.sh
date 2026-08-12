#!/bin/bash
# AITBC one-command dev setup.
# Creates venv, installs deps, installs pre-commit hooks, runs checks.
#
# Usage:
#   ./scripts/dev/setup.sh          # full setup
#   ./scripts/dev/setup.sh --check  # run checks only (skip install)
#   ./scripts/dev/setup.sh --services # start dev services after setup

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

# The same gates pre-commit runs, so "All checks passed" here means the commit will not
# bounce. ruff + mypy alone did not: the two ratchets below are enforced as hooks, and a
# dev who ran only this script found that out at commit time instead.
run_checks() {
    ./venv/bin/python -m ruff check .
    ./venv/bin/python -m ruff format --check .
    ./venv/bin/python -m mypy --show-error-codes aitbc/
    # apps/ type ratchet — baseline is 0; a new error fails the hook
    bash scripts/ci/mypy-precommit.sh
    # no new float-money declarations
    ./venv/bin/python scripts/lint/no_float_money.py
    ./venv/bin/python -m pytest tests/unit -q -o addopts=""
}

CHECK_ONLY=false
START_SERVICES=false
for arg in "$@"; do
    case "$arg" in
        --check)    CHECK_ONLY=true ;;
        --services) START_SERVICES=true ;;
        --help) echo "Usage: $0 [--check] [--services]"; exit 0 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

if [ "$CHECK_ONLY" = true ]; then
    info "Running checks only"
    run_checks
    ok "All checks passed"
    exit 0
fi

# 1. Create venv
if [ ! -d "venv" ]; then
    info "Creating virtual environment"
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
fi

# 2. Install dependencies
info "Installing dependencies"
if command -v uv &>/dev/null; then
    uv sync --dev
else
    ./venv/bin/pip install -e ".[dev]" 2>/dev/null || ./venv/bin/pip install -e .
fi
ok "Dependencies installed"

# 3. Install pre-commit hooks
info "Installing pre-commit hooks"
if [ -f venv/bin/pre-commit ]; then
    ./venv/bin/pre-commit install
    ok "Pre-commit hooks installed"
else
    warn "pre-commit not found in venv — skipping hook installation"
fi

# 4. Run checks
info "Running checks"
run_checks
ok "All checks passed"

# 5. Optionally start services
if [ "$START_SERVICES" = true ]; then
    info "Starting dev services"
    if [ -f scripts/development/start-aitbc-dev.sh ]; then
        bash scripts/development/start-aitbc-dev.sh
    else
        warn "scripts/development/start-aitbc-dev.sh not found — skipping service startup"
    fi
fi

ok "Setup complete! Run './scripts/dev/setup.sh --check' to re-verify, or '--services' to start services."
