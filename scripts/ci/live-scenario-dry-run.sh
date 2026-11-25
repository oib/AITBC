#!/bin/bash
# Dry-run the live scenario suite in CI.
# This does not touch live nodes; it exercises the product CLI surface that maps
# to the live-validated economic loop. Fleet workflow scenarios live in the
# separate aitbc-ops repository.

set -euo pipefail

cd "$(dirname "$0")/../.."

PYTHON="${PYTHON:-./venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi

echo "🧪 Live scenario dry-run"

# CLI smoke checks for validated surface
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
