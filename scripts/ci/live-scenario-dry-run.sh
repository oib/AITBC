#!/bin/bash
# Dry-run the live scenario suite in CI.
# This does not touch live nodes; it validates shell script syntax and exercises
# the CLI surface that maps to the live-validated economic loop.

set -euo pipefail

cd "$(dirname "$0")/../.."

PYTHON="${PYTHON:-./venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi

echo "🧪 Live scenario dry-run"

# 1. Shell script syntax validation for the workflow scenarios
for script in dev/testing/tests/*.sh scripts/workflow/*.sh; do
    if [ -f "$script" ]; then
        bash -n "$script"
        echo "✅ $script"
    fi
done

# 2. CLI smoke checks for validated surface
echo "
🔎 CLI smoke checks"
$PYTHON -m aitbc_cli --help >/dev/null
$PYTHON -m aitbc_cli ai --help >/dev/null
$PYTHON -m aitbc_cli wallet --help >/dev/null
$PYTHON -m aitbc_cli market --help >/dev/null
$PYTHON -m aitbc_cli bond --help >/dev/null
$PYTHON -m aitbc_cli transactions --help >/dev/null
$PYTHON -m aitbc_cli version >/dev/null

echo "✅ Live scenario dry-run complete"
