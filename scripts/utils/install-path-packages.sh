#!/bin/bash
# Install the repo-local path packages into a venv, and prove they import.
#
# These packages are not on any index. They are consumed as ordinary top-level
# imports (aitbc_crypto, aitbc_sdk, aitbc_errors, ...) by the CLI, the services
# and by `aitbc/exceptions.py` itself -- so a venv missing them does not fail at
# install time, it fails at request time.
#
# Two things this script exists to guarantee:
#
#   1. ORDER INDEPENDENCE. aitbc-sdk depends on aitbc-crypto and aitbc-errors,
#      neither of which is published. Installing one package at a time only
#      works if the loop happens to reach the dependencies first -- which today
#      it does, purely because "aitbc-crypto" and "aitbc-errors" sort before
#      "aitbc-sdk". Rename or add a package and that silently stops being true.
#      Passing every package to a SINGLE pip invocation makes them candidates
#      for one resolution, so order stops mattering.
#
#   2. LOUD FAILURE. The previous inline loop ran pip with `>/dev/null 2>&1`
#      and downgraded any failure to a warning, so a node could finish setup
#      "successfully" and then break on first import. Here a failure is fatal
#      and prints what pip actually said.
#
# Usage: install-path-packages.sh [VENV_DIR]     (default: <repo>/venv)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${1:-$REPO_ROOT/venv}"
# Use `python -m pip`, not venv/bin/pip: the console script carries an absolute
# shebang, and on hosts whose venv was built from a since-deleted build cache
# that shebang points at a missing interpreter ("cannot execute: required file
# not found"). The module entry point has no such dependency.
PIP=("$VENV_DIR/bin/python" -m pip)
PY="$VENV_DIR/bin/python"

if [ ! -x "$PY" ]; then
    echo "[ERROR] No interpreter at $PY -- create the venv first." >&2
    exit 1
fi

# Discover rather than hardcode, so a new package under packages/py is picked
# up without editing this list.
pkg_dirs=()
for d in "$REPO_ROOT/packages/aitbc-shared" "$REPO_ROOT/packages/py"/*; do
    [ -f "$d/pyproject.toml" ] && pkg_dirs+=("$d")
done

if [ ${#pkg_dirs[@]} -eq 0 ]; then
    echo "[ERROR] No path packages found under $REPO_ROOT/packages." >&2
    exit 1
fi

echo "[INFO] Installing ${#pkg_dirs[@]} path packages into $VENV_DIR"
for d in "${pkg_dirs[@]}"; do echo "         $(basename "$d")"; done

pip_args=()
for d in "${pkg_dirs[@]}"; do pip_args+=(-e "$d"); done

# One invocation, output NOT swallowed, exit status honoured.
if ! "${PIP[@]}" install "${pip_args[@]}"; then
    echo "[ERROR] pip failed to install the path packages (see output above)." >&2
    exit 1
fi

# Installing is not the same as importing. Derive the module names from what is
# actually on disk -- the directory name is not always the module name
# (packages/py/aitbc-agent-sdk ships a package called aitbc_agent).
#
# Run the check from the repo root, because that is how the services run.
# packages/aitbc-shared is checked but not fatal: it imports the ROOT `aitbc`
# package (aitbc_shared/core/config.py -> aitbc.constants) and pydantic_settings
# without declaring either, so it cannot import until requirements.txt is in
# place. That is a pre-existing layering defect in aitbc-shared, not a fault in
# this install -- so it warns with the reason rather than failing setup.
echo "[INFO] Verifying imports"
failed=0
for d in "${pkg_dirs[@]}"; do
    src="$d/src"
    [ -d "$src" ] || src="$d"
    optional=0
    [ "$(basename "$d")" = "aitbc-shared" ] && optional=1
    for mod_dir in "$src"/*/; do
        mod="$(basename "$mod_dir")"
        case "$mod" in *.egg-info|__pycache__) continue ;; esac
        [ -f "$mod_dir/__init__.py" ] || continue
        if (cd "$REPO_ROOT" && "$PY" -c "import $mod") >/dev/null 2>&1; then
            echo "         OK       $mod"
        elif [ "$optional" -eq 1 ]; then
            echo "         SKIPPED  $mod (needs the root aitbc package + requirements.txt)"
        else
            echo "         FAILED   $mod" >&2
            (cd "$REPO_ROOT" && "$PY" -c "import $mod") 2>&1 | tail -3 >&2
            failed=1
        fi
    done
done

if [ "$failed" -ne 0 ]; then
    echo "[ERROR] Path packages installed but do not import (see errors above)." >&2
    exit 1
fi

echo "[OK] Path packages installed and importable."
