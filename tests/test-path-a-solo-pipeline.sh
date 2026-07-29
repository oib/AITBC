#!/bin/bash
# =============================================================================
# Test: Path-A parentless-ticket solo pipeline (ABS-105, spec ABS-103 §3/§5)
# =============================================================================
# Proves the five acceptance criteria for the solo pipeline against the REAL
# scripts/orchestrator.sh + the mock task-tracking adapter (scripts/mock-
# tracker.sh) with the STUB spawn (tests/fixtures/stub-spawn.sh) -- no real
# `claude`, no live model. Same deterministic harness idiom as
# tests/e2e-workflow-v3.sh (drive tracker transitions to fabricate the pipeline
# state, run the runner --dry-run/--live, assert the emitted INTENT lines).
#
# ABS-105 forks NO parallel pipeline code (ADR-A-0010): the solo pipeline is the
# existing v3.0 story seat mapping + SKIP-FORWARD, entered by the Path-A triage
# head (the po-agent Backlog seat in single-ticket mode) releasing the ticket to
# `Design`. This suite proves the runner mechanics deliver each AC:
#   AC1 -- a plain parentless bug spawns exactly the solo-pipeline seats (triage
#          head, implement, code review, in test, story acceptance) and
#          SKIP-FORWARDs Design/Security Review/Test Prep/Design Test with an
#          audit comment and ZERO spawns for each.
#   AC2 -- no epic-level status/seat is ever engaged for a parentless ticket
#          (assertable in the transition log + the absence of epic-seat spawns).
#   AC3 -- the JOIN rule never evaluates for a parentless ticket (no JOIN intent).
#   AC4 -- a security-flagged parentless ticket DOES spawn Security Review.
#   AC5 -- the triage+DoR head runs (SPAWN po-agent on Backlog) and its ready
#          outcome routes the ticket onto the story-pipeline head (Design).
#
# Run from repo root: bash tests/test-path-a-solo-pipeline.sh
# =============================================================================

set -e
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
# Deterministic synchronous scheduler (fixed same-cycle spawn counts / sequences),
# matching tests/e2e-workflow-v3.sh.
export ORCH_ASYNC_SPAWNS=0
export ORCH_DEPENDS_GATING=0
export ORCH_SESSION_RESUME=0
export ORCH_WORKTREE_SPAWNS=0

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -40 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | grep -F -- "$expected" | head -10 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"
        FAIL=$((FAIL + 1))
    fi
}

new_env() {
    TEST_DIR="$(mktemp -d /tmp/path-a-solo-test-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    unset ORCH_MAX_CONCURRENT ORCH_MAX_SPAWNS_PER_RUN ORCH_NOTIFY_TICKET
    unset ORCH_RECONCILE_ON_STARTUP ORCH_RECONCILE_EVERY_N_CYCLES STUB_RECORD_FILE
    unset STUB_FAIL STUB_HANG STUB_HANG_SECONDS STUB_NO_HANDOFF STUB_TRANSITION_TO
    unset ORCH_REWORK_LIMIT ORCH_CRASH_LIMIT ORCH_MAX_SPAWNS_PER_DAY ORCH_FOLLOWUP_BUDGET
    export ORCH_MAX_CONCURRENT=10
    export ORCH_SPAWN_CMD="$STUB"
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
}
cleanup_env() { [ -n "${TEST_DIR:-}" ] && rm -rf "$TEST_DIR"; }

tracker() { bash "$TRACKER" "$@"; }
orch()    { bash "$ORCH" "$@"; }

echo -e "${CYAN}=== Path-A parentless-ticket solo pipeline (ABS-105) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}AC5 + AC1(head) — the triage+DoR head spawns and routes into the story pipeline${NC}"
# =============================================================================
# A seeded parentless bug rests in Backlog. On the creation-event poll the runner
# (1) classifies it parentless-ticket -> Path-A head (ABS-104), and (2) maps the
# Backlog entry to SPAWN po-agent -- that spawn IS the Path-A triage + DoR head
# (single-ticket mode). No epic status is engaged by the classification.
new_env
PB=$(tracker create --type ticket --title "Parentless bug" --label orchestrator-ready)
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT INTAKE-CLASSIFY ticket=$PB role=- to=Path-A head note=class=parentless-ticket" \
    "AC5: parentless bug classified to the Path-A head"
assert_contains "$out" "INTENT SPAWN ticket=$PB role=po-agent to=Backlog" \
    "AC5/AC1: the triage+DoR head spawns (po-agent, single-ticket mode) on Backlog"
assert_not_contains "$out" "to=PO Triage" \
    "AC2: classification never routes the parentless ticket into the PO Triage status"

# The ready outcome of the head releases the ticket to the STORY pipeline head
# (Design) -- a legal Backlog->Design transition, never an epic status.
tracker transition "$PB" "Design" --actor po-agent \
    --reason "Path-A triage: ready — released to the story pipeline" >/dev/null
released=$(tracker get "$PB" | grep '^status:' | head -1 | sed 's/^status: //')
assert_eq "$released" "Design" "AC5: the ready head outcome routes Backlog -> Design (story pipeline head)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}AC1 + AC2 + AC3 — plain parentless bug walks the solo pipeline; 4 conditional stages SKIP-FORWARD${NC}"
# =============================================================================
# From the Design head a plain (unflagged) parentless bug walks the reused v3.0
# story pipeline: Design/Security Review/Test Prep/Design Test SKIP-FORWARD with
# a runner audit comment + ZERO spawns; implement/code-review/in-test/acceptance
# spawn their canonical seats. No epic seat spawns; JOIN never evaluates.
new_env
PB=$(tracker create --type ticket --title "Parentless bug (no flags)" --label orchestrator-ready)
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1   # consume creation event
STUB_RECORD_FILE="$TEST_DIR/pb-spawns.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
allout=""

# Head ready outcome -> Design; the runner SKIP-FORWARDs unflagged Design and
# spawns the implementer at Ready for Development.
tracker transition "$PB" "Design" --actor po-agent --reason "Path-A ready" >/dev/null
o=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=6 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SKIP-FORWARD ticket=$PB role=- to=Ready for Development" "AC1: unflagged Design SKIP-FORWARDs"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=be-developer to=Ready for Development" "AC1: implement spawns (be-developer)"

tracker transition "$PB" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$PB" "In Review" --actor be-developer --reason handoff >/dev/null
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=system-architect to=In Review" "AC1: code review spawns (system-architect)"

tracker transition "$PB" "Security Review" --actor system-architect --reason reviewed >/dev/null
o=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=3 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SKIP-FORWARD ticket=$PB role=- to=Test Prep" "AC1: unflagged Security Review SKIP-FORWARDs"
assert_contains "$o" "INTENT SKIP-FORWARD ticket=$PB role=- to=In Test" "AC1: unflagged Test Prep SKIP-FORWARDs"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=qas to=In Test" "AC1: in test spawns (qas)"

tracker transition "$PB" "Design Test" --actor qas --reason passed >/dev/null
o=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=2 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SKIP-FORWARD ticket=$PB role=- to=Story Acceptance" "AC1: unflagged Design Test SKIP-FORWARDs"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=po-agent to=Story Acceptance" "AC1: story acceptance spawns (po-agent)"

# AC1 -- ZERO spawns for each of the four SKIP-FORWARDed conditional stages.
assert_not_contains "$allout" "INTENT SPAWN ticket=$PB role=ui-ux-design" "AC1: Design never spawns a seat (SKIP-FORWARD)"
assert_not_contains "$allout" "INTENT SPAWN ticket=$PB role=security-engineer" "AC1: Security Review never spawns a seat (unflagged)"
assert_not_contains "$allout" "INTENT SPAWN ticket=$PB role=data-provisioning-eng" "AC1: Test Prep never spawns a seat (SKIP-FORWARD)"
assert_not_contains "$allout" "INTENT SPAWN ticket=$PB role=qas-design" "AC1: Design Test never spawns a seat (SKIP-FORWARD)"

# AC2 -- no epic-level SEAT is ever spawned for a parentless ticket.
assert_not_contains "$allout" "INTENT SPAWN ticket=$PB role=bsa" "AC2: no Grooming (bsa) spawn"
assert_not_contains "$allout" "INTENT SPAWN ticket=$PB role=issue-enrichment" "AC2: no Enrichment (issue-enrichment) spawn"
# AC2 -- no epic-level STATUS is ever entered (assertable in the transition log).
pblog=$(tracker get "$PB")
for st in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review" "Epic Integration"; do
    n=$(echo "$pblog" | grep -c -- "-> $st\." || true)
    assert_eq "$n" "0" "AC2: transition log never enters epic status '$st'"
done

# AC3 -- the JOIN rule never evaluates for a parentless ticket (no fan-in check).
assert_not_contains "$allout" "INTENT JOIN" "AC3: JOIN rule never evaluates (no JOIN/JOIN-WAIT/JOIN-EMPTY intent)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}AC4 — a security-flagged parentless ticket DOES spawn Security Review${NC}"
# =============================================================================
new_env
SB=$(tracker create --type ticket --title "Parentless bug (security)" --flag security --label orchestrator-ready)
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT INTAKE-CLASSIFY ticket=$SB role=- to=Path-A head note=class=parentless-ticket" \
    "AC4: security-flagged bug is still classified parentless -> Path-A"
# Head ready -> Design; walk to the Security Review stage.
tracker transition "$SB" "Design" --actor po-agent --reason "Path-A ready" >/dev/null
ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=6 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live >/dev/null 2>&1
tracker transition "$SB" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$SB" "In Review" --actor be-developer --reason handoff >/dev/null
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1
tracker transition "$SB" "Security Review" --actor system-architect --reason reviewed >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$SB role=security-engineer to=Security Review" \
    "AC4: security flag honoured — Security Review spawns security-engineer (no SKIP-FORWARD)"
assert_not_contains "$out" "INTENT SKIP-FORWARD ticket=$SB role=- to=Test Prep" \
    "AC4: a flagged Security Review is NOT skipped"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "Total: $TOTAL  ${GREEN}Pass: $PASS${NC}  ${RED}Fail: $FAIL${NC}"
[ "$FAIL" -eq 0 ] || exit 1
