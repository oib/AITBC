#!/usr/bin/env bash
# =============================================================================
# Test: durable ops-sweep report persistence (PILOT-73)
# =============================================================================
# In Phase 0 (shadow) the cadence ops-sweep executes NOTHING — the report IS its
# only work product. Before PILOT-73 that report lived only in run_spawn_cmd's
# stdout capture under packets/, deleted on the success path (ABS-265), so the
# Phase-0 acceptance ("does the report cover the operator's real interventions?")
# was structurally impossible. This test pins the fix:
#   AC1: the report lands in a durable, inventoried store (NOT packets/).
#   AC2: every sweep leaves ONE greppable runlog line with per-class finding counts.
#   AC3: a sweep that finds nothing (or produced no output) says so EXPLICITLY.
#   AC4: the report survives — a second sweep does not clobber the first.
#
# orchestrator.sh is source-guarded (main runs only when executed directly), so we
# SOURCE it and drive ops_sweep_persist_report directly with fixture spawn stdout.
# Run from repo root: bash tests/test-ops-sweep-report.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
check() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -eq 0 ]; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $2${3:+ (${YELLOW}$3${NC})}"; FAIL=$((FAIL + 1)); fi
}

TMP="$(mktemp -d "${TMPDIR:-/tmp}/ops-sweep-report-XXXXXX")"
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

# Source the runner (functions only; main is source-guarded). set -euo pipefail leaks
# ON from the source; turn pipefail back OFF so a SIGPIPE in a pipe is not a false fail.
export ORCH_STATE_DIR="$TMP/state"
export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"
mkdir -p "$ORCH_STATE_DIR"
# shellcheck source=/dev/null
source "$ORCH" >/dev/null 2>&1
set +o pipefail
# Re-pin after source (top-level init derives its own defaults).
export ORCH_STATE_DIR="$TMP/state"
export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"
export ORCH_OPS_SWEEP_TICKET="ops-sweep"
export ORCH_OPS_SWEEP_ROLE="tdm"

echo -e "${CYAN}=== PILOT-73 durable ops-sweep report ===${NC}\n"

REPORT_DIR="$(ops_sweep_report_dir)"

# --- AC2 + findings: a report with two classes -> per-class runlog counts ------
echo -e "${CYAN}Report with findings${NC}"
: > "$ORCH_RUN_LOG"
findings='{"type":"result","subtype":"success","result":"worktree-hygiene - head=abc,expected=main reset-main-checkout\ndep-release-due PILOT-9 dep=PILOT-8 release-from-blocked\ndep-release-due PILOT-12 dep=PILOT-8 release-from-blocked","session_id":"s1"}'
printf '%s' "$findings" > "$TMP/out1"
ops_sweep_persist_report "$TMP/out1"
line="$(grep 'OPS-SWEEP-REPORT' "$ORCH_RUN_LOG" | head -1)"
check "$([ -n "$line" ]; echo $?)" "AC2: a runlog OPS-SWEEP-REPORT line is emitted"
check "$(printf '%s' "$line" | grep -q 'total=3'; echo $?)" "AC2: total finding count is greppable" "$line"
check "$(printf '%s' "$line" | grep -q 'worktree-hygiene=1'; echo $?)" "AC2: per-class count worktree-hygiene=1" "$line"
check "$(printf '%s' "$line" | grep -q 'dep-release-due=2'; echo $?)" "AC2: per-class count dep-release-due=2" "$line"

# --- AC1: the report file lands in the durable store, NOT under packets/ -------
echo -e "\n${CYAN}Durable store (AC1)${NC}"
rf="$(ls "$REPORT_DIR"/ops-sweep.*.txt 2>/dev/null | head -1)"
check "$([ -n "$rf" ] && [ -s "$rf" ]; echo $?)" "AC1: a non-empty report file exists in the durable store"
check "$(printf '%s' "$REPORT_DIR" | grep -qv '/packets/'; echo $?)" "AC1: store is NOT under the swept packets/ dir" "$REPORT_DIR"
check "$(grep -q 'worktree-hygiene' "$rf" 2>/dev/null; echo $?)" "AC1: the report file carries the decoded findings"

# --- AC3: a clean sweep says so explicitly (silence != did-not-run) -----------
echo -e "\n${CYAN}Clean sweep (AC3)${NC}"
: > "$ORCH_RUN_LOG"
printf '%s' '{"type":"result","subtype":"success","result":"All sensors clean. No findings this cycle.","session_id":"s2"}' > "$TMP/out2"
ops_sweep_persist_report "$TMP/out2"
clean="$(grep 'OPS-SWEEP-REPORT' "$ORCH_RUN_LOG" | head -1)"
check "$(printf '%s' "$clean" | grep -q 'total=0'; echo $?)" "AC3: clean sweep reports total=0" "$clean"
check "$(printf '%s' "$clean" | grep -q 'no-findings'; echo $?)" "AC3: clean sweep states 'no-findings' explicitly" "$clean"

# --- AC3 edge: an empty/crashed seat is distinguished, still leaves a line -----
echo -e "\n${CYAN}Empty output (AC3 edge)${NC}"
: > "$ORCH_RUN_LOG"
: > "$TMP/out3"
ops_sweep_persist_report "$TMP/out3"
empty="$(grep 'OPS-SWEEP-REPORT' "$ORCH_RUN_LOG" | head -1)"
check "$([ -n "$empty" ]; echo $?)" "AC2: even an empty seat leaves a runlog line"
check "$(printf '%s' "$empty" | grep -q 'report-empty'; echo $?)" "AC3: empty output flagged 'report-empty' (not silent)" "$empty"

# --- AC4: a second sweep does not clobber the first report --------------------
echo -e "\n${CYAN}Survival across sweeps (AC4)${NC}"
n_before="$(ls "$REPORT_DIR"/ops-sweep.*.txt 2>/dev/null | wc -l | tr -d ' ')"
sleep 1  # distinct second-resolution timestamp in the filename
printf '%s' '{"type":"result","subtype":"success","result":"stale-lock PILOT-5 age=5000 clear-stale-lock","session_id":"s3"}' > "$TMP/out4"
ops_sweep_persist_report "$TMP/out4"
n_after="$(ls "$REPORT_DIR"/ops-sweep.*.txt 2>/dev/null | wc -l | tr -d ' ')"
check "$([ "$n_after" -gt "$n_before" ]; echo $?)" "AC4: the second sweep ADDS a report, does not overwrite" "before=$n_before after=$n_after"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0; fi
