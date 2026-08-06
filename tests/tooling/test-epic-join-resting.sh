#!/bin/bash
# =============================================================================
# Test: legal JOIN-rest for a decomposed epic resting in Backlog (ABS-214)
# =============================================================================
# Lineage: recurring HANDOFF-NOMOVE loop on decomposed epics — ABS-190 (3
# incidents 2026-07-10/11), ABS-181, ABS-153, ABS-152, ABS-138. The po-agent
# decomposes a bare epic, releases its children (Ready for Development) and
# leaves the epic resting in Backlog; on the next sweep the Backlog seat
# re-spawns the po-agent on that decomposed epic, but Backlog had no legal edge
# into the epic's correct JOIN rest-state (Stories In Flight), so the clean
# handoff recorded a HANDOFF-NOMOVE run after run until an operator hand-moved
# it. Covers the acceptance criteria:
#   AC1  the Backlog -> Stories In Flight edge is legal, and a decomposed epic
#        can be rested there declaratively (seat-declared `to:`) OR by the
#        runner completion epic_join_rest_complete (analog to the ABS-203
#        write-light completion).
#   AC2  no HANDOFF-NOMOVE for the standard case (epic groomed, children
#        released): a clean po-agent handoff that declares no target rests the
#        epic in Stories In Flight instead of looping in Backlog.
#   AC3  scoping — a plain (childless) Backlog ticket is NOT short-circuited: it
#        still records a HANDOFF-NOMOVE, so no ticket is falsely JOIN-rested.
#
# ABS-309 / ABS-271 addendum. The JOIN-rest lands the epic in Stories In Flight,
# but that landing skips the mandatory DoR gate (Ticket Review). On the next
# sweep the STATION-GUARD (ABS-271) redirects a decomposed/pre-filled epic from
# Stories In Flight back to its owed Ticket Review gate — the landing was a
# repair, not a happy path (see profiles/neutral/adapters/statuses.yaml, the
# "v3 PRE-FILLED epic" header and Stories In Flight.next). So the JOIN-rest edge
# is the INTERMEDIATE landing; Ticket Review is the epic's TRUE resting state.
# The integration cases below therefore run two sweeps and pin BOTH the JOIN-rest
# edge (unchanged ABS-214 coverage) AND the STATION-GUARD redirect (net gain).
# Pre-ABS-271 they asserted Stories In Flight as the end state and only passed
# because --once froze that transient state before the guard fired (ABS-309).
#
# Two layers, same idiom as tests/test-enrichment-writelight.sh:
#   1. UNIT — source scripts/orchestrator.sh (main is source-guarded) and drive
#      epic_join_rest_complete against a stub `tracker`.
#   2. INTEGRATION — drive the runner against the mock adapter with a STUB spawn
#      (tests/fixtures/stub-spawn.sh) and assert the epic's end state.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-epic-join-resting.sh
# =============================================================================

set -euo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
STUB="$REPO_ROOT/tests/fixtures/stub-spawn.sh"

export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$TRACKER"
# Pin the legacy synchronous scheduling modes so the end-state assertions are
# deterministic (no background spawn races) — same pins the sibling tests use.
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
# 1. UNIT — runner-side JOIN-rest completion helper (sourced function)
# =============================================================================
# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

echo -e "${CYAN}=== ABS-214 epic JOIN-rest completion ===${NC}\n"
echo -e "${CYAN}UNIT — epic_join_rest_complete (Backlog -> Stories In Flight)${NC}"
MODE="live"

# Stub the adapter: child-count is the decomposition signal; get/status feed
# ticket_still_in; transition/comment are captured for assertions.
STUB_CHILDCOUNT=0
STUB_STATUS="Backlog"
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

# Decomposed epic still resting in Backlog → runner rests it to Stories In Flight.
STUB_CHILDCOUNT=3; STUB_STATUS="Backlog"; STUB_CALLS="$(mktemp)"
rc=0; epic_join_rest_complete E1 "Backlog" "po-agent" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "decomposed epic (children>0) in Backlog → handled (returns 0)"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION E1 Stories In Flight" \
    "runner emits the JOIN-rest transition via the adapter"
rm -f "$STUB_CALLS"

# Childless ticket (undecomposed epic / plain ticket) → NOT handled, no move (AC3).
STUB_CHILDCOUNT=0; STUB_STATUS="Backlog"; STUB_CALLS="$(mktemp)"
rc=0; epic_join_rest_complete E1 "Backlog" "po-agent" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "childless ticket → NOT handled (returns non-zero, falls through to no-move)"
assert_not_contains "$(cat "$STUB_CALLS")" "TRANSITION" "childless ticket → no runner transition (no false JOIN-rest)"
rm -f "$STUB_CALLS"

# Non-numeric child-count → fail-safe to 0 → not handled.
STUB_CHILDCOUNT="garbage"; STUB_STATUS="Backlog"
rc=0; epic_join_rest_complete E1 "Backlog" "po-agent" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "non-numeric child-count → not handled (fail-safe)"

# Wrong role / wrong status → never handled.
STUB_CHILDCOUNT=3; STUB_STATUS="Backlog"
rc=0; epic_join_rest_complete E1 "Backlog" "issue-enrichment" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "non-po-agent role → not handled"
rc=0; epic_join_rest_complete E1 "Grooming" "po-agent" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "non-Backlog status → not handled"

# Seat already advanced the epic (its own transition went through) → clean no-op.
STUB_CHILDCOUNT=3; STUB_STATUS="Stories In Flight"; STUB_CALLS="$(mktemp)"
rc=0; epic_join_rest_complete E1 "Backlog" "po-agent" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "seat already moved the epic → handled (clean), returns 0"
assert_not_contains "$(cat "$STUB_CALLS")" "TRANSITION" "seat already advanced → no second transition (idempotent)"
rm -f "$STUB_CALLS"

# Restore the real adapter for the integration layer (subprocess `orch`).
unset -f tracker

# =============================================================================
# 2. LEGALITY — the Backlog -> Stories In Flight edge is legal in the adapter
# =============================================================================
tracker() { bash "$TRACKER" "$@"; }

echo -e "\n${CYAN}LEGALITY — mock adapter enforces the new transition table${NC}"
LEG_DIR="$(mktemp -d /tmp/joinrest-leg-XXXXXX)"
export MOCK_TRACKER_TICKETS_DIR="$LEG_DIR/work/tickets"; mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
LE=$(tracker create --type epic --title "legality epic" --label orchestrator-ready)
if tracker transition "$LE" "Stories In Flight" --actor po-agent --reason "AC1 legality" >/dev/null 2>&1; then
    assert_eq "$(tracker get "$LE" | awk -F': ' '/^status:/{print $2; exit}')" "Stories In Flight" \
        "AC1: Backlog -> Stories In Flight is now a legal transition"
else
    assert_eq "rejected" "legal" "AC1: Backlog -> Stories In Flight is now a legal transition"
fi
rm -rf "$LEG_DIR"

# =============================================================================
# 3. INTEGRATION — full runner sweep against the mock adapter + stub spawn
# =============================================================================
orch() { bash "$ORCH" "$@"; }

new_env() {
    TEST_DIR="$(mktemp -d /tmp/joinrest-test-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    export ORCH_SPAWN_CMD="$STUB"
    export ORCH_MAX_SPAWNS_PER_RUN=50
    export STUB_PACKET_COPY="$TEST_DIR/packets.txt"
    unset ORCH_MAX_CONCURRENT ORCH_NOTIFY_TICKET STUB_RECORD_FILE STUB_HANG \
          STUB_NO_HANDOFF STUB_TRANSITION_TO STUB_HANDOFF_TO STUB_FAIL
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
}
cleanup_env() { [ -n "${TEST_DIR:-}" ] && rm -rf "$TEST_DIR"; }

# seed_decomposed_epic <n-children> — an epic with n children released to Ready
# for Development, the epic itself left resting in Backlog (the exact state the
# po-agent Branch B leaves behind). Echoes the epic id.
seed_decomposed_epic() {
    local n="$1" e i=0 c
    e=$(tracker create --type epic --title "decomposed epic" --label orchestrator-ready)
    while [ "$i" -lt "$n" ]; do
        i=$((i + 1))
        c=$(tracker create --type ticket --parent "$e" --title "child $i")
        # Release the child onto the story pipeline and let it rest working, so
        # the sweep does not re-derive a child spawn that clutters the run.
        tracker transition "$c" "Ready for Development" --actor po-agent --reason seed >/dev/null
        tracker transition "$c" "In Progress"          --actor be-developer --reason seed >/dev/null
    done
    printf '%s' "$e"
}

echo -e "\n${CYAN}INTEGRATION — clean po-agent handoff, no declared target: JOIN-rest then STATION-GUARD (AC2)${NC}"
new_env
E=$(seed_decomposed_epic 2)                    # decomposed epic resting in Backlog
# Sweep 1 — the runner completes the JOIN-rest (Backlog -> Stories In Flight).
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)
# Sweep 2 — the ABS-271 STATION-GUARD redirects the landing that skipped the
# mandatory DoR gate (Stories In Flight -> Ticket Review), the epic's true rest.
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1 || true
dump=$(tracker get "$E")

# ABS-214 JOIN-rest coverage stays pinned — the edge still fires:
assert_contains "$out" "INTENT EPIC-JOIN-REST ticket=$E" \
    "AC2: runner emits the JOIN-rest completion (EPIC-JOIN-REST)"
assert_contains "$dump" "EPIC-JOIN-REST status=Backlog" \
    "AC2: an audit marker records the JOIN-rest completion"
assert_contains "$dump" "Backlog -> Stories In Flight" \
    "AC2: the JOIN-rest edge (Backlog -> Stories In Flight) is recorded"
# ABS-271 STATION-GUARD redirect — net-new coverage (ABS-309):
assert_contains "$dump" "STATION-GUARD: transition 'Backlog' -> 'Stories In Flight' skipped 'Ticket Review'" \
    "AC2: STATION-GUARD redirects the DoR-gate-skipping landing (ABS-271)"
assert_eq "$(tracker get "$E" | awk -F': ' '/^status:/{print $2; exit}')" "Ticket Review" \
    "AC2: epic rests at its owed DoR gate Ticket Review after the redirect (ABS-271; was Stories In Flight pre-ABS-271)"
assert_not_contains "$dump" "HANDOFF-NOMOVE status=Backlog" \
    "AC2: no HANDOFF-NOMOVE for the standard 'epic groomed, children released' case"
cleanup_env

echo -e "\n${CYAN}INTEGRATION — seat DECLARES the target: runner applies it, then STATION-GUARD redirects (AC1)${NC}"
new_env
E=$(seed_decomposed_epic 2)
# Sweep 1 — the seat declares Stories In Flight; the runner applies it, and the
# ABS-271 STATION-GUARD redirect fires WITHIN THE SAME --once cycle (the poll
# processes the just-applied Backlog -> Stories In Flight transition and
# redirects it to the owed DoR gate). So a single cycle already lands the epic at
# its true rest, Ticket Review (v2.25.2 integration: ABS-309's original two-sweep
# framing over-counted — apply and STATION-GUARD redirect collapse into one cycle
# on the epic-278 orchestrator; the redirected end state is unchanged and wanted).
out=$(STUB_HANDOFF_TO="Stories In Flight" ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)
assert_eq "$(tracker get "$E" | awk -F': ' '/^status:/{print $2; exit}')" "Ticket Review" \
    "AC1: declarative seat target is applied and STATION-GUARD redirects it to Ticket Review within the first cycle (ABS-271)"
assert_not_contains "$out" "INTENT EPIC-JOIN-REST ticket=$E" \
    "AC1: seat already moved it → runner completion is a no-op (no double transition)"
# Sweep 2 — idempotency: re-running the cycle keeps the epic at its owed DoR gate.
STUB_HANDOFF_TO="Stories In Flight" ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1 || true
dump=$(tracker get "$E")

assert_eq "$(tracker get "$E" | awk -F': ' '/^status:/{print $2; exit}')" "Ticket Review" \
    "AC1: STATION-GUARD redirects the declarative landing to Ticket Review (ABS-271)"
assert_contains "$dump" "STATION-GUARD: transition 'Backlog' -> 'Stories In Flight' skipped 'Ticket Review'" \
    "AC1: STATION-GUARD marker recorded on the declarative path (ABS-271)"
assert_not_contains "$dump" "HANDOFF-NOMOVE status=Backlog" \
    "AC1: no HANDOFF-NOMOVE on the declarative path"
cleanup_env

echo -e "\n${CYAN}INTEGRATION — a plain (childless) Backlog ticket is NOT JOIN-rested (AC3)${NC}"
new_env
T=$(tracker create --type ticket --title "plain backlog ticket" --label orchestrator-ready)
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)
dump=$(tracker get "$T")

assert_not_contains "$out" "INTENT EPIC-JOIN-REST ticket=$T" \
    "AC3: childless ticket → no JOIN-rest short-circuit"
assert_not_contains "$dump" "EPIC-JOIN-REST status=Backlog" \
    "AC3: no JOIN-rest marker on a plain ticket"
assert_eq "$(tracker get "$T" | awk -F': ' '/^status:/{print $2; exit}')" "Backlog" \
    "AC3: plain ticket rests in Backlog (unchanged no-move behavior)"
assert_contains "$dump" "HANDOFF-NOMOVE status=Backlog" \
    "AC3: plain ticket still records HANDOFF-NOMOVE (scoping preserved)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "Total: $TOTAL  ${GREEN}Pass: $PASS${NC}  ${RED}Fail: $FAIL${NC}"
[ "$FAIL" -eq 0 ] || exit 1
