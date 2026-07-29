#!/bin/bash
# =============================================================================
# E2E dry-run scenario: Orchestrator full lifecycle (ABS-36 spec §8.3 / ABS-55)
# =============================================================================
# Drives scripts/orchestrator.sh end-to-end against the mock task-tracking
# adapter with a scratch ticket store and the STUB spawn command
# (tests/fixtures/stub-spawn.sh) — no real `claude`, no live model. This is the
# blueprint v1 definition-of-done scenario: an epic + child tickets walk the
# full canonical lifecycle (Backlog -> ... -> Ready for Human Acceptance),
# with the orchestrator producing the expected SPAWN/NOOP/NOTIFY intents at
# every hop and correct role selection (ticket `role` hint, and the
# be-developer fallback when absent). It also proves the two permanent
# human-only boundaries (Ready for Merge, epic acceptance) never trigger a
# spawn, and exercises the §5.1 concurrency-cap-defer + crash-recovery
# reconciliation path.
#
# Deterministic: uses --once and ORCH_MAX_CYCLES (no timers, no kill-switch
# race). Runs on macOS bash 3.2 (no associative arrays, no `mapfile`).
#
# Run from repo root: bash tests/e2e-orchestrator-dryrun.sh
#
# Evidence captured from a run of this script lives at:
#   docs/agent-outputs/qa-validations/ABS-36-e2e-dry-run.md
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

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -30 | sed 's/^/    /'
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
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -30 | sed 's/^/    /'
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

TEST_DIR="$(mktemp -d /tmp/orchestrator-e2e-XXXXXX)"
export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
export ORCH_SPAWN_CMD="$STUB"
mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
# ABS-526: hermetic target repo. Without ORCH_TARGET_REPO the runner's state
# root is the REAL checkout, so C9 worktree provisioning (ensure_worktree)
# creates DEMO-*-auto branches + tmp/DEMO-*-work worktrees in the developer's
# repository — and because mock ticket ids restart at DEMO-1 every run, stale
# registrations from any earlier run make `git worktree add` fail ("already
# used by worktree") and every child spawn fail-closes as SKIP-NOWORKTREE.
# Point the runner at a scratch git repo (same idiom as test-orchestrator.sh's
# C9 sections) so provisioning is exercised end-to-end without touching the
# real repo. Explicit MOCK_TRACKER_TICKETS_DIR/ORCH_STATE_DIR above still win.
export ORCH_TARGET_REPO="$TEST_DIR/target-repo"
mkdir -p "$ORCH_TARGET_REPO"
git -C "$ORCH_TARGET_REPO" init -q
git -C "$ORCH_TARGET_REPO" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
cleanup() { rm -rf "$TEST_DIR"; }
trap cleanup EXIT

tracker() { bash "$TRACKER" "$@"; }
orch()    { bash "$ORCH" "$@"; }
# Baseline: consume creation events so the first real --once only sees the
# transition we drive. Startup reconciliation is off here (nothing to derive
# from Backlog yet); it is turned back on later, in step 9, on purpose.
baseline() { ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1; }

echo -e "${CYAN}=== E2E dry-run: Orchestrator full lifecycle (ABS-36 spec sec8.3) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}Step 1 — create epic + child tickets (mock tracker)${NC}"
# =============================================================================
EPIC=$(tracker create --type epic --title "E2E epic: orchestrator dry-run")
CHILD_FE=$(tracker create --type ticket --title "FE child" --parent "$EPIC" --role fe-developer)
CHILD_BE=$(tracker create --type ticket --title "BE child (no role hint)" --parent "$EPIC")
echo "  epic=$EPIC child_fe=$CHILD_FE (role=fe-developer) child_be=$CHILD_BE (no role -> fallback)"
baseline

# =============================================================================
echo -e "\n${CYAN}Step 2 — epic assigned to PO-Agent (Backlog status-change event)${NC}"
# =============================================================================
# The epic is already in Backlog (its creation event was drained by baseline).
# "Assigned to the PO-Agent" is realized as a status-change comment + the
# Backlog->Backlog prioritization sweep firing on the next transition we make;
# per statuses.yaml, Backlog's own trigger is "PO prioritization sweep" (SPAWN
# po-agent) and fires on every ticket entering/re-entering Backlog. We record
# the assignment explicitly as an actor-attributed comment (adapter-only,
# ADR-A-0007) so the ticket carries an auditable PO-Agent assignment marker,
# then transition the epic Backlog -> Ready for Development to prove the
# mapping fires for epics exactly like tickets.
tracker comment "$EPIC" --kind decision --actor po-agent \
    --body "Epic assigned to PO-Agent for prioritization sweep (E2E step 2)." >/dev/null
tracker transition "$EPIC" "Ready for Development" --actor po-agent --reason "prioritized" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$EPIC role=be-developer to=Ready for Development" "epic Backlog->Ready for Development spawns implementer (role falls back on the epic itself)"
# Advance the epic out of the SPAWN-mapped "Ready for Development" status (as
# its own coordination work would in reality) so it does not confound the
# later concurrency/reconciliation scenario (step 9), which asserts precise
# spawn counts across the whole ticket store.
tracker transition "$EPIC" "In Progress" --actor po-agent --reason "children in flight" >/dev/null

# =============================================================================
echo -e "\n${CYAN}Step 3 — child tickets: Backlog -> Ready for Development (role selection)${NC}"
# =============================================================================
tracker transition "$CHILD_FE" "Ready for Development" --actor po-agent --reason "prioritized" >/dev/null
tracker transition "$CHILD_BE" "Ready for Development" --actor po-agent --reason "prioritized" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$CHILD_FE role=fe-developer to=Ready for Development" "FE child: role from ticket frontmatter (fe-developer)"
assert_contains "$out" "INTENT SPAWN ticket=$CHILD_BE role=be-developer to=Ready for Development" "BE child: no role frontmatter -> be-developer fallback"
assert_contains "$out" "note=no-role-frontmatter-defaulting-to-be-developer" "BE child fallback records the #PLAN_UNCERTAINTY note"
assert_contains "$out" "INTENT HANDOFF ticket=$CHILD_FE" "FE child --live spawn lands a handoff"
assert_contains "$out" "INTENT HANDOFF ticket=$CHILD_BE" "BE child --live spawn lands a handoff"
fe_handoff=$(tracker get "$CHILD_FE" | grep -c "kind: handoff | actor: orchestrator" || true)
be_handoff=$(tracker get "$CHILD_BE" | grep -c "kind: handoff | actor: orchestrator" || true)
assert_eq "$fe_handoff" "1" "FE child handoff recorded as kind:handoff comment"
assert_eq "$be_handoff" "1" "BE child handoff recorded as kind:handoff comment"
# The stub's canned handoff (§3.3/§6) drives the ticket forward itself in a real
# --live run only when STUB_TRANSITION_TO is set (not here — the orchestrator
# does not auto-advance on a handoff; the implementer subagent would transition
# on its own next turn). Advance explicitly, as the implementer subagent would.
tracker transition "$CHILD_FE" "In Progress" --actor fe-developer --reason "started" >/dev/null
tracker transition "$CHILD_BE" "In Progress" --actor be-developer --reason "started" >/dev/null

# =============================================================================
echo -e "\n${CYAN}Step 4 — In Progress is NOOP (implementer already spawned itself)${NC}"
# =============================================================================
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT NOOP ticket=$CHILD_FE" "FE child In Progress -> NOOP"
assert_contains "$out" "INTENT NOOP ticket=$CHILD_BE" "BE child In Progress -> NOOP"
assert_not_contains "$out" "INTENT SPAWN ticket=$CHILD_FE" "FE child In Progress does not double-spawn"
assert_not_contains "$out" "INTENT SPAWN ticket=$CHILD_BE" "BE child In Progress does not double-spawn"

# =============================================================================
echo -e "\n${CYAN}Step 5 — In Review -> SPAWN system-architect${NC}"
# =============================================================================
tracker transition "$CHILD_FE" "In Review" --actor fe-developer --reason "handoff" >/dev/null
tracker transition "$CHILD_BE" "In Review" --actor be-developer --reason "handoff" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$CHILD_FE role=system-architect to=In Review" "FE child In Review -> SPAWN system-architect"
assert_contains "$out" "INTENT SPAWN ticket=$CHILD_BE role=system-architect to=In Review" "BE child In Review -> SPAWN system-architect"
tracker transition "$CHILD_FE" "In Test" --actor system-architect --reason "reviewed" >/dev/null
tracker transition "$CHILD_BE" "In Test" --actor system-architect --reason "reviewed" >/dev/null

# =============================================================================
echo -e "\n${CYAN}Step 6 — In Test -> SPAWN qas${NC}"
# =============================================================================
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$CHILD_FE role=qas to=In Test" "FE child In Test -> SPAWN qas"
assert_contains "$out" "INTENT SPAWN ticket=$CHILD_BE role=qas to=In Test" "BE child In Test -> SPAWN qas"
tracker transition "$CHILD_FE" "Ready for Human Acceptance" --actor qas --reason "passed" >/dev/null
tracker transition "$CHILD_BE" "Ready for Human Acceptance" --actor qas --reason "passed" >/dev/null

# =============================================================================
echo -e "\n${CYAN}Step 7 — Ready for Human Acceptance -> SPAWN po-agent + NOTIFY${NC}"
# =============================================================================
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$CHILD_FE role=po-agent to=Ready for Human Acceptance" "FE child RHA -> SPAWN po-agent"
assert_contains "$out" "INTENT SPAWN ticket=$CHILD_BE role=po-agent to=Ready for Human Acceptance" "BE child RHA -> SPAWN po-agent"
assert_contains "$out" "INTENT NOTIFY" "RHA -> NOTIFY fires (SPAWN-then-NOTIFY, human epic-acceptance signal)"
notify_count=$(echo "$out" | grep -c "INTENT NOTIFY" || true)
assert_eq "$notify_count" "2" "RHA -> exactly one NOTIFY per child ticket (2 total)"
tracker transition "$CHILD_FE" "Ready for Merge" --actor po-agent --reason "accepted" >/dev/null
tracker transition "$CHILD_BE" "Ready for Merge" --actor po-agent --reason "accepted" >/dev/null

# =============================================================================
echo -e "\n${CYAN}Step 8 — human-only boundary: Ready for Merge is NOOP, never a spawn${NC}"
# =============================================================================
# Ready for Merge is the permanent human merge gate (ADR-A-0004/0005): the
# runner maps it to NOOP (no spawn, no notify — the Release Agent already
# prepared the PR and a human decision is pending outside the loop).
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT NOOP ticket=$CHILD_FE" "FE child Ready for Merge -> NOOP"
assert_contains "$out" "INTENT NOOP ticket=$CHILD_BE" "BE child Ready for Merge -> NOOP"
assert_not_contains "$out" "INTENT SPAWN ticket=$CHILD_FE" "Ready for Merge never spawns (human-only merge boundary)"
assert_not_contains "$out" "INTENT SPAWN ticket=$CHILD_BE" "Ready for Merge never spawns (human-only merge boundary)"
assert_not_contains "$out" "INTENT NOTIFY" "Ready for Merge does not also NOTIFY (NOOP is silent — human already owns this gate)"

# --- audit trail: every hop left a ticket comment; only tracker + orchestrator
#     runtime dirs exist on disk (ADR-A-0007: adapter-only access) -----------
fe_comments=$(tracker get "$CHILD_FE" | grep -c "^### " || true)
be_comments=$(tracker get "$CHILD_BE" | grep -c "^### " || true)
TOTAL=$((TOTAL + 1))
if [ "$fe_comments" -ge 5 ] && [ "$be_comments" -ge 5 ]; then
    echo -e "  ${GREEN}PASS${NC} every lifecycle hop left a ticket comment (FE=$fe_comments, BE=$be_comments blocks)"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} expected >=5 comment blocks per child, got FE=$fe_comments BE=$be_comments"
    FAIL=$((FAIL + 1))
fi
extra_state=$(find "$TEST_DIR/work" -mindepth 1 -maxdepth 1 ! -name tickets ! -name .orchestrator ! -name .events-state 2>/dev/null | wc -l | tr -d ' ')
assert_eq "$extra_state" "0" "no state outside the tracker + orchestrator runtime dirs (ADR-A-0007 adapter-only access)"

# =============================================================================
echo -e "\n${CYAN}Step 9 — concurrency-cap defer + crash-recovery reconciliation (spec sec8.3 item 9)${NC}"
# =============================================================================
# A fresh pair of tickets under the same epic, both entering Ready for
# Development in one poll with ORCH_MAX_CONCURRENT=1: the first spawns, the
# second is deferred into the in-memory pending set (INTENT DEFER-CAP). We
# then simulate the runner crashing before it retries the deferred entry (the
# pending set is in-memory only and does not survive process death) and start
# a FRESH runner process: its startup reconciliation sweep must re-derive the
# still-Ready-for-Development ticket from the tracker and dispatch it exactly
# once — no event loss, no double-spawn.
CAP_A=$(tracker create --type ticket --title "Cap A" --parent "$EPIC")
CAP_B=$(tracker create --type ticket --title "Cap B" --parent "$EPIC")
ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1   # drain creation events

tracker transition "$CAP_A" "Ready for Development" --actor po-agent --reason go >/dev/null
tracker transition "$CAP_B" "Ready for Development" --actor po-agent --reason go >/dev/null

REC_FILE="$TEST_DIR/cap-spawns.txt"; : > "$REC_FILE"
# Single --once pass at cap=1: one ticket spawns (and — like a real implementer
# subagent picking up its handoff — moves itself on to In Progress via the
# stub's STUB_TRANSITION_TO hook), the other is deferred into the in-memory
# pending set. This process then exits (as if it crashed) WITHOUT retrying the
# pending set, so the deferred ticket is stuck in Ready for Development with no
# lock held and no pending-set entry anywhere (the pending set died with it).
out=$(ORCH_MAX_CONCURRENT=1 ORCH_RECONCILE_ON_STARTUP=0 STUB_RECORD_FILE="$REC_FILE" \
      STUB_TRANSITION_TO="In Progress" STUB_TRACKER="$TRACKER" \
      orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT DEFER-CAP" "cap=1: second Ready-for-Development event deferred, not dropped"
spawned_first_pass=$(wc -l < "$REC_FILE" | tr -d ' ')
assert_eq "$spawned_first_pass" "1" "cap=1: exactly one of the two tickets spawns in the crashed process's single pass"
# Whichever ticket spawned is now In Progress (moved on by "its own" subagent);
# the other is still sitting in Ready for Development — the true crash-lost event.
spawned_ticket="$(awk -F'\t' '{print $2}' "$REC_FILE")"
case "$spawned_ticket" in
    "$CAP_A") deferred_ticket="$CAP_B" ;;
    *)        deferred_ticket="$CAP_A" ;;
esac

# "Crash": the pending set lived only in the dead process's memory. A FRESH
# runner starts with startup reconciliation ON (the default) and no
# ORCH_MAX_CONCURRENT cap, so it can pick up the still-pending ticket via a
# tracker `search` scan (§5.1) — not via any persisted queue.
out2=$(ORCH_RECONCILE_ON_STARTUP=1 STUB_RECORD_FILE="$REC_FILE" orch --live --once 2>&1)
assert_contains "$out2" "reconciliation sweep" "fresh runner runs its startup reconciliation sweep"
assert_contains "$out2" "INTENT SPAWN ticket=$deferred_ticket" "reconciliation re-derives and dispatches the crash-lost deferred ticket"
# Total spawns across BOTH processes: exactly one per ticket — the re-read
# guard (already-advanced $spawned_ticket is now In Progress, a NOOP status)
# prevents reconciliation from double-spawning the one that already succeeded.
total_spawns=$(wc -l < "$REC_FILE" | tr -d ' ')
assert_eq "$total_spawns" "2" "crash recovery: both tickets end up spawned exactly once total (no loss, no double-spawn)"
spawned_ticket_count=$(grep -c "	$spawned_ticket$" "$REC_FILE" || true)
deferred_ticket_count=$(grep -c "	$deferred_ticket$" "$REC_FILE" || true)
assert_eq "$spawned_ticket_count" "1" "the already-spawned ticket is NOT re-spawned by reconciliation (re-read guard)"
assert_eq "$deferred_ticket_count" "1" "the crash-lost deferred ticket is spawned exactly once by reconciliation"

# =============================================================================
echo -e "\n${CYAN}Step 10 — reconcile ignores tickets RESTING in entry/terminal states${NC}"
# =============================================================================
# Regression (PR #25 review): the reconciliation sweep must re-derive spawns
# only from *transient* work states. A ticket resting in Backlog (ungroomed) or
# Done (terminal) is a legitimate resting state — the startup sweep must NOT
# mass-spawn a whole backlog, and a periodic sweep must NOT re-spawn Done
# tickets every cadence forever (which would loop tech-writer and burn the
# ADR-A-0009 per-run spawn budget). Guarded by is_reconcilable_status() (§5.1).
REST_BL=$(tracker create --type ticket --title "Resting backlog" --parent "$EPIC")
REST_DN=$(tracker create --type ticket --title "Resting done" --parent "$EPIC")
for s in "Ready for Development" "In Progress" "In Review" "In Test" \
         "Ready for Human Acceptance" "Ready for Merge" "Done"; do
    tracker transition "$REST_DN" "$s" --actor agent --reason walk >/dev/null
done
tracker events >/dev/null 2>&1   # drain creation/transition events
REST_FILE="$TEST_DIR/rest-spawns.txt"; : > "$REST_FILE"
# Force reconciliation to run (startup sweep + every cycle) across two cycles.
out=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=2 ORCH_RECONCILE_EVERY_N_CYCLES=1 \
      STUB_RECORD_FILE="$REST_FILE" orch --live 2>&1)
assert_not_contains "$out" "INTENT SPAWN ticket=$REST_BL" "reconcile does not spawn a ticket resting in Backlog"
assert_not_contains "$out" "INTENT SPAWN ticket=$REST_DN" "reconcile does not spawn a ticket resting in Done"
rest_bl_spawns=$(awk -F'\t' -v t="$REST_BL" '$2==t{c++} END{print c+0}' "$REST_FILE")
rest_dn_spawns=$(awk -F'\t' -v t="$REST_DN" '$2==t{c++} END{print c+0}' "$REST_FILE")
assert_eq "$rest_bl_spawns" "0" "reconcile never invokes the spawn seam for the resting Backlog ticket"
assert_eq "$rest_dn_spawns" "0" "reconcile never invokes the spawn seam for the resting Done ticket"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    exit 1
else
    echo -e "  Failed: 0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
