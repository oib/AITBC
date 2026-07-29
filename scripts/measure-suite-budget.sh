#!/usr/bin/env bash
# =============================================================================
# measure-suite-budget.sh — measure the tentpole suite's runtime + reserve
# -----------------------------------------------------------------------------
# WHY (ABS-603): tests/test-orchestrator.sh is a monolithic tentpole that runs
# against a FIXED per-suite budget (PRE_RELEASE_SUITE_TIMEOUT, default in
# scripts/pre-release-check.sh). Its runtime grows with every epic that adds a
# tests/orchestrator.d fixture, so the reserve (budget − runtime) SHRINKS over
# time. Pilot 8 measured only 12 % reserve (790 s of 900 s) — one parallel seat
# was enough to push the gate over its budget and paint it red on a green suite.
#
# This tool produces the MEASURED numbers ABS-603 AC1 requires (no guessed
# value): runtime ISOLATED and runtime UNDER LOAD (a concurrent competitor
# running the same tentpole, reproducing the incident). Run it at each release
# (AC5) with --record to append a row to the history table in
# docs/release/SUITE-BUDGET.md so the growth curve stays visible.
#
# Usage:
#   bash scripts/measure-suite-budget.sh              # isolated run, print result
#   bash scripts/measure-suite-budget.sh --under-load # + one concurrent competitor
#   bash scripts/measure-suite-budget.sh --both       # isolated THEN under-load, same env
#   bash scripts/measure-suite-budget.sh --both --record   # + append to history table
#
#   --budget N   reserve is computed against N seconds (default: the value
#                pre-release-check.sh would use — $PRE_RELEASE_SUITE_TIMEOUT or 1800).
#   TEST_JOBS    parallelism for the tentpole (default 4 — the proven-safe value;
#                >4 gives spurious shard aborts, see tests/staged-suite.sh header).
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1

TENTPOLE="tests/test-orchestrator.sh"
JOBS="${TEST_JOBS:-4}"
case "$JOBS" in ''|*[!0-9]*) JOBS=4 ;; esac
BUDGET="${PRE_RELEASE_SUITE_TIMEOUT:-1800}"
HISTORY_DOC="docs/release/SUITE-BUDGET.md"
MARK_END="<!-- SUITE-BUDGET-HISTORY:END -->"

MODE_BOTH=0 UNDER_LOAD=0 RECORD=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --both) MODE_BOTH=1 ;;
        --under-load) UNDER_LOAD=1 ;;
        --record) RECORD=1 ;;
        --budget) BUDGET="${2:-1800}"; shift ;;
        -h|--help) sed -n '2,34p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done
case "$BUDGET" in ''|*[!0-9]*) BUDGET=1800 ;; esac

fixtures() { find tests/orchestrator.d -maxdepth 1 -name '*.sh' 2>/dev/null | wc -l | tr -d ' '; }

# Run the tentpole once, print "elapsed asserts" to stdout (nothing else).
run_tentpole() {
    local out; out="$(mktemp "${TMPDIR:-/tmp}/tentpole-XXXXXX")"
    local start end asserts
    start=$(date +%s)
    env -u ORCH_STATE_DIR -u ORCH_TARGET_REPO TEST_JOBS="$JOBS" \
        bash "$TENTPOLE" >"$out" 2>&1
    local rc=$?
    end=$(date +%s)
    # Assertion count from the suite's own summary ("Passed: N"); 0 if it failed.
    asserts=$(grep -Eo 'Passed:[[:space:]]*[0-9]+' "$out" | grep -Eo '[0-9]+' | tail -1 || true)
    [ -n "$asserts" ] || asserts=0
    rm -f "$out"
    printf '%s %s %s\n' "$((end - start))" "$asserts" "$rc"
}

# Measure one mode. Args: mode-label. Echoes a summary line + fills globals.
measure() {
    local mode="$1" competitor_pid=""
    if [ "$mode" = "under-load" ]; then
        echo ">> starting concurrent competitor (a second $TENTPOLE, same box)…" >&2
        ( env -u ORCH_STATE_DIR -u ORCH_TARGET_REPO TEST_JOBS="$JOBS" \
            bash "$TENTPOLE" >/dev/null 2>&1 ) &
        competitor_pid=$!
    fi
    echo ">> measuring '$mode' (TEST_JOBS=$JOBS)…" >&2
    local res; res="$(run_tentpole)"
    local elapsed asserts rc
    elapsed=$(printf '%s' "$res" | cut -d' ' -f1)
    asserts=$(printf '%s' "$res" | cut -d' ' -f2)
    rc=$(printf '%s' "$res" | cut -d' ' -f3)
    if [ -n "$competitor_pid" ]; then
        wait "$competitor_pid" 2>/dev/null || true   # never orphan the competitor (common-rule 5)
    fi
    # reserve% = (budget - elapsed) * 100 / budget  (can go negative)
    local reserve=$(( (BUDGET - elapsed) * 100 / BUDGET ))
    local fx; fx="$(fixtures)"
    local sha; sha="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    local date; date="$(date -u +%Y-%m-%d)"
    printf '%-11s elapsed=%ss budget=%ss reserve=%s%% asserts=%s fixtures=%s rc=%s\n' \
        "$mode" "$elapsed" "$BUDGET" "$reserve" "$asserts" "$fx" "$rc"
    if [ "$RECORD" = "1" ] && [ -f "$HISTORY_DOC" ] && grep -q "$MARK_END" "$HISTORY_DOC"; then
        local row="| $date | \`$sha\` | $mode | ${elapsed}s | ${BUDGET}s | ${reserve}% | $asserts | $fx |"
        local tmp; tmp="$(mktemp)"
        awk -v end="$MARK_END" -v row="$row" '
            $0 ~ end { print row } { print }' "$HISTORY_DOC" > "$tmp" && mv "$tmp" "$HISTORY_DOC"
        echo ">> recorded row in $HISTORY_DOC" >&2
    fi
}

echo "=== ABS-603 suite-budget measurement — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "    tentpole=$TENTPOLE  budget=${BUDGET}s  TEST_JOBS=$JOBS  fixtures=$(fixtures)"
if [ "$MODE_BOTH" = "1" ]; then
    measure isolated
    measure under-load
elif [ "$UNDER_LOAD" = "1" ]; then
    measure under-load
else
    measure isolated
fi
