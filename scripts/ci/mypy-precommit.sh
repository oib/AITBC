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
# The 29 pre-existing errors were recorded in mypy-baseline.txt; the hook fails on
# errors not in that file. Same ratchet as scripts/lint/no_float_money.py: the
# backlog does not block commits, a new error does. Shrink it with --update.
#
# V23-46: the baseline is now empty, so this is a plain gate again. It started at 29
# and five of those were runtime TypeErrors -- calls to PaymentService.create_payment
# and release_payment missing a required argument, on paths that could therefore never
# have completed. Two annotations accounted for most of the rest: pool-hub's services
# declared `db: Session` while every call site passes an AsyncSession (23 `type: ignore`
# comments existed to cover for that one word), and apps/edge's two clients had an
# unannotated `__aenter__`, so `async with Client() as c` bound c as Any and every
# result off it was Any too.
#
# Keep it empty. A baseline that grows back is a baseline nobody reads.
#
# 2026-08-23: cli/ was never in APPS, so 154 source files went unchecked. Its
# errors still leaked into the output whenever an app's import graph happened to
# reach them, which made the gate non-deterministic: hub reported one cli error on
# a warm cache and three on a cold one, aitbc3 reported none at all. Adding cli to
# APPS makes the coverage explicit and the result reproducible.
#
# The errors that surfaced are recorded here rather than fixed, so the ratchet is
# non-empty again. This is a debt, not a decision to live with: the paragraph above
# still applies. Shrink it with --update as the entries are fixed.
#
# Generate the baseline on a host with the full dependency set. Where torch,
# tenseal or opentelemetry are missing, mypy degrades those imports to Any and the
# 'type: ignore' comments covering them are reported as unused -- roughly 17 bogus
# errors that would otherwise be baselined as real.

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
  cli
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
