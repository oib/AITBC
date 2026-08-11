#!/bin/bash
# MyPy pre-commit hook for clean apps
#
# This hook checked nothing at all until 2026-08-11. It passed `apps/ffmpeg` and
# `apps/whisper` to mypy; the only Python file in either is `main.py`, and
# pyproject.toml excludes `^apps/[^/]+/main\.py$`. mypy treats "directory with no
# checkable files" as a hard error and aborts *before* checking any of the other
# twelve. The abort message contains no "error:" substring, the grep below found
# nothing, and the hook printed "✅ MyPy: All clean apps pass" on every commit.
# Removing those two directories from the list surfaced 29 real errors in 11 files.
#
# Two changes keep it honest:
#   1. Only directories that actually have checkable files are passed.
#   2. mypy's exit code is checked, so a future abort fails the hook instead of
#      being read as success. The grep alone could not tell the difference between
#      "no errors" and "never ran".
#
# The 29 pre-existing errors are recorded in mypy-baseline.txt; the hook fails on
# errors not in that file. Same ratchet as scripts/lint/no_float_money.py: the
# backlog does not block commits, a new error does. Shrink it with --update.

set -euo pipefail

cd /opt/aitbc

BASELINE="scripts/ci/mypy-baseline.txt"

# apps/ffmpeg and apps/whisper are deliberately absent: their only .py file is an
# excluded main.py, and naming them makes mypy abort without checking anything.
APPS=(
  apps/coordinator-api
  apps/blockchain-node
  apps/pool-hub
  apps/edge
  apps/wallet
  apps/agent-coordinator
  apps/marketplace
  apps/api-gateway
  apps/blockchain-event-bridge
  apps/blockchain-explorer
  apps/miner
  apps/zk-circuits
)

set +e
OUTPUT=$(./venv/bin/python -m mypy --show-error-codes --ignore-missing-imports "${APPS[@]}" 2>&1)
STATUS=$?
set -e

# mypy exits 0 (no errors) or 1 (errors found). Anything else -- a bad argument, an
# internal crash, a directory it refuses to walk -- means it did not check the code,
# which is the failure mode this hook was blind to for months.
if [ "$STATUS" -gt 1 ]; then
    echo "❌ MyPy did not run (exit $STATUS). It checked nothing; this is not a pass."
    echo "$OUTPUT" | tail -20
    exit 1
fi

# Strip line numbers so the baseline does not churn when unrelated code moves.
normalize() { grep -E "(error:|warning:)" | sed 's/:[0-9]*:\( error:\| warning:\)/:\1/' | sort; }

CURRENT=$(echo "$OUTPUT" | normalize || true)

if [ "${1:-}" = "--update" ]; then
    echo "$CURRENT" > "$BASELINE"
    echo "✅ MyPy baseline updated: $(grep -c . < "$BASELINE") known error(s)"
    exit 0
fi

touch "$BASELINE"
NEW=$(comm -13 "$BASELINE" <(echo "$CURRENT") || true)

if [ -n "$NEW" ]; then
    echo "❌ MyPy: new type errors (not in $BASELINE):"
    echo "$NEW" | head -20
    echo ""
    echo "Fix them, or if one is genuinely pre-existing: bash $0 --update"
    exit 1
fi

FIXED=$(comm -23 "$BASELINE" <(echo "$CURRENT") || true)
if [ -n "$FIXED" ]; then
    echo "ℹ️  $(echo "$FIXED" | grep -c .) baselined error(s) no longer present. Tighten it: bash $0 --update"
fi

echo "✅ MyPy: no new type errors ($(grep -c . < "$BASELINE") known, see $BASELINE)"
exit 0
