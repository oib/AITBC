#!/bin/bash
# =============================================================================
# Test: Write-light Path-B enrichment, tolerant of tracker-write denial (ABS-203)
# =============================================================================
# Lineage: ABS-181 (issue-enrichment write-denial crash → catastrophic re-cycle
# loop). Covers the acceptance criteria:
#   AC1  a no-op dedup run (children already exist) is classified write-light and
#        the seat is handed a `write_mode: write-light` packet hint so it emits
#        zero child-creation writes;
#   AC2  a tracker-write denial during such a no-op run does NOT crash / re-cycle
#        — the runner emits the completion signal (Enrichment → Ticket Review)
#        via $TRACKER_CMD (WRITE-LIGHT-COMPLETE), leaving the epic transitioned;
#   AC3  a full-write run (no children yet) is NOT short-circuited — it follows
#        the normal crash path so no children are dropped / no false write-skip.
#
# Two layers:
#   1. UNIT — source scripts/orchestrator.sh (main is source-guarded) and drive
#      enrichment_write_mode / writelight_enrichment_complete against a stub
#      `tracker` (same idiom as tests/test-station-guard.sh).
#   2. INTEGRATION — drive the runner against the mock adapter with a STUB spawn
#      (tests/fixtures/stub-spawn.sh) forced to fail (STUB_FAIL=1 models the
#      seat's writes being denied), and assert the epic's end state.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-enrichment-writelight.sh
# =============================================================================

set -euo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
STUB="$REPO_ROOT/tests/fixtures/stub-spawn.sh"

export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$TRACKER"
# Pin the legacy synchronous scheduling modes so the end-state assertions are
# deterministic (no background spawn races) — same pins tests/test-orchestrator.sh uses.
export ORCH_ASYNC_SPAWNS=0
export ORCH_DEPENDS_GATING=0
export ORCH_SESSION_RESUME=0
export ORCH_WORKTREE_SPAWNS=0

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -12 <<<"$output" | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"; FAIL=$((FAIL + 1)); fi
}

# =============================================================================
# 1. UNIT — detector + runner-side completion helper (sourced functions)
# =============================================================================
# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

echo -e "${CYAN}=== ABS-203 write-light enrichment ===${NC}\n"
echo -e "${CYAN}UNIT — enrichment_write_mode detector${NC}"

# Stub the adapter: child-count is the only signal the detector reads; get/status
# feed ticket_still_in; transition/comment are captured for assertions.
STUB_CHILDCOUNT=0
STUB_STATUS="Enrichment"
STUB_CALLS=""
tracker() {
    case "$1" in
        child-count) printf '%s\n' "$STUB_CHILDCOUNT" ;;
        get)         printf -- '---\nstatus: %s\n---\n' "$STUB_STATUS" ;;
        transition)  shift; printf 'TRANSITION %s\n' "$*" >> "$STUB_CALLS" ;;
        comment)     shift; printf 'COMMENT %s\n' "$*" >> "$STUB_CALLS" ;;
        *)           : ;;
    esac
}

STUB_CHILDCOUNT=3
assert_eq "$(enrichment_write_mode E1)" "write-light" "child-count > 0 → write-light (dedup no-op)"
STUB_CHILDCOUNT=1
assert_eq "$(enrichment_write_mode E1)" "write-light" "child-count == 1 → write-light"
STUB_CHILDCOUNT=0
assert_eq "$(enrichment_write_mode E1)" "full-write" "child-count == 0 → full-write (first enrichment)"
STUB_CHILDCOUNT="garbage"
assert_eq "$(enrichment_write_mode E1)" "full-write" "non-numeric child-count → full-write (fail-safe)"

echo -e "\n${CYAN}UNIT — writelight_enrichment_complete (runner-side completion signal)${NC}"
MODE="live"

# Write-light + still resting in Enrichment → runner transitions to Ticket Review.
STUB_CHILDCOUNT=2; STUB_STATUS="Enrichment"; STUB_CALLS="$(mktemp)"
rc=0; writelight_enrichment_complete E1 "Enrichment" "issue-enrichment" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "write-light no-op → handled (returns 0)"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION E1 Ticket Review" "runner emits the completion signal via the adapter"
rm -f "$STUB_CALLS"

# Full-write (no children yet) → NOT handled, no transition (AC3, no write-skip).
STUB_CHILDCOUNT=0; STUB_STATUS="Enrichment"; STUB_CALLS="$(mktemp)"
rc=0; writelight_enrichment_complete E1 "Enrichment" "issue-enrichment" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "full-write → NOT handled (returns non-zero, falls through to crash path)"
assert_not_contains "$(cat "$STUB_CALLS")" "TRANSITION" "full-write → no runner transition (no false write-skip)"
rm -f "$STUB_CALLS"

# Wrong role / wrong status → never handled.
STUB_CHILDCOUNT=2; STUB_STATUS="Enrichment"
rc=0; writelight_enrichment_complete E1 "Enrichment" "be-developer" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "non-enrichment role → not handled"
rc=0; writelight_enrichment_complete E1 "In Progress" "issue-enrichment" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "non-Enrichment status → not handled"

# Seat already advanced the epic (writes went through) → clean no-op, no double transition.
STUB_CHILDCOUNT=2; STUB_STATUS="Ticket Review"; STUB_CALLS="$(mktemp)"
rc=0; writelight_enrichment_complete E1 "Enrichment" "issue-enrichment" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "seat already moved the epic → handled (clean), returns 0"
assert_not_contains "$(cat "$STUB_CALLS")" "TRANSITION" "seat already advanced → no second transition (idempotent)"
rm -f "$STUB_CALLS"

# Restore the real adapter for the integration layer (subprocess `orch`).
unset -f tracker

# =============================================================================
# 2. INTEGRATION — full runner sweep against the mock adapter + stub spawn
# =============================================================================
tracker() { bash "$TRACKER" "$@"; }
orch()    { bash "$ORCH" "$@"; }

new_env() {
    TEST_DIR="$(mktemp -d /tmp/writelight-test-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    export ORCH_SPAWN_CMD="$STUB"
    export ORCH_MAX_SPAWNS_PER_RUN=50
    export STUB_PACKET_COPY="$TEST_DIR/packets.txt"
    unset ORCH_MAX_CONCURRENT ORCH_NOTIFY_TICKET STUB_RECORD_FILE STUB_HANG \
          STUB_NO_HANDOFF STUB_TRANSITION_TO STUB_HANDOFF_TO
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
}
cleanup_env() { [ -n "${TEST_DIR:-}" ] && rm -rf "$TEST_DIR"; }

# seed_epic_at_enrichment <n-children> — create an epic, n children, and walk the
# epic Backlog → PO Triage → Grooming → Enrichment. Echoes the epic id.
seed_epic_at_enrichment() {
    local n="$1" e i=0
    e=$(tracker create --type epic --title "Path-B epic" --label orchestrator-ready)
    while [ "$i" -lt "$n" ]; do
        i=$((i + 1))
        tracker create --type ticket --parent "$e" --title "child $i" >/dev/null
    done
    tracker transition "$e" "PO Triage" --actor po-agent    --reason seed >/dev/null
    tracker transition "$e" "Grooming"  --actor po-agent    --reason seed >/dev/null
    tracker transition "$e" "Enrichment" --actor bsa        --reason seed >/dev/null
    printf '%s' "$e"
}

echo -e "\n${CYAN}INTEGRATION — write-denial on a no-op Path-B enrichment (AC1 + AC2)${NC}"
new_env
E=$(seed_epic_at_enrichment 2)                 # children already exist → write-light
out=$(STUB_FAIL=1 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)
dump=$(tracker get "$E")

# AC1: the seat is handed the write-light hint (so it emits zero create calls).
assert_contains "$(cat "$STUB_PACKET_COPY" 2>/dev/null || true)" "write_mode: write-light" \
    "AC1: issue-enrichment packet carries the write-light hint"
# AC2: the runner emits the completion signal despite the seat write-denial.
assert_contains "$out" "INTENT WRITE-LIGHT-COMPLETE ticket=$E" \
    "AC2: runner emits the completion signal (WRITE-LIGHT-COMPLETE)"
assert_eq "$(tracker get "$E" | awk -F': ' '/^status:/{print $2; exit}')" "Ticket Review" \
    "AC2: epic is transitioned to Ticket Review (not left resting in Enrichment)"
assert_contains "$dump" "WRITE-LIGHT-COMPLETE status=Enrichment" \
    "AC2: an audit marker records the write-light completion"
assert_not_contains "$dump" "SPAWN-CRASH status=Enrichment" \
    "AC2: no crash marker at Enrichment (denial is non-catastrophic, no re-cycle)"
cleanup_env

echo -e "\n${CYAN}INTEGRATION — full-write first enrichment is NOT short-circuited (AC3)${NC}"
new_env
E=$(seed_epic_at_enrichment 0)                 # no children yet → full-write
out=$(STUB_FAIL=1 ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)
dump=$(tracker get "$E")

assert_contains "$(cat "$STUB_PACKET_COPY" 2>/dev/null || true)" "write_mode: full-write" \
    "AC3: issue-enrichment packet carries full-write (children must be created)"
assert_not_contains "$out" "INTENT WRITE-LIGHT-COMPLETE ticket=$E" \
    "AC3: no write-light short-circuit for a full-write run"
assert_contains "$dump" "SPAWN-CRASH status=Enrichment" \
    "AC3: a genuine crash still follows the normal crash path (no dropped children)"
assert_eq "$(tracker get "$E" | awk -F': ' '/^status:/{print $2; exit}')" "Enrichment" \
    "AC3: full-write crash rests in Enrichment for the sweep (not force-completed)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "Total: $TOTAL  ${GREEN}Pass: $PASS${NC}  ${RED}Fail: $FAIL${NC}"
[ "$FAIL" -eq 0 ] || exit 1
