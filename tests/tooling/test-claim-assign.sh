#!/bin/bash
# =============================================================================
# Test: optional ORCH_CLAIM_ASSIGN human-visibility layer (ABS-186, spec §3/§6)
# =============================================================================
# After a WON remote claim, dispatch OPTIONALLY stamps the ticket assignee so the
# ticket visibly shows which operator/machine is working it — COSMETIC ONLY: the
# claim comment stays the claim of record and the assignee is NEVER read back to
# decide ownership. This suite drives the REAL spawn_dispatch (sourced, no poll
# loop), stubs the out-of-scope acquire_remote_claim (ABS-184) with a controllable
# win/loss, and stubs `tracker` so the assign adapter call is counted directly:
#   - ORCH_CLAIM_ASSIGN=0 (default): NO assign call / intent after a won claim
#   - ORCH_CLAIM_ASSIGN=1 + won:     assigns to ORCH_ASSIGNEE (intent + adapter)
#   - failed assign:                 logs a warning, dispatch stays rc 0 (non-fatal)
#   - ownership is never read back:   a LOST claim never assigns (assign follows the
#                                     claim, never the reverse); mode=off never assigns
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-claim-assign.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Isolated state dir: LOCKS_DIR / run.log / ledger are all derived from it at
# source time, so it MUST be exported before sourcing.
TEST_DIR="$(mktemp -d /tmp/claim-assign-test-XXXXXX)"
export ORCH_STATE_DIR="$TEST_DIR/.orchestrator"
mkdir -p "$ORCH_STATE_DIR"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1
# Relax the runner's `set -euo pipefail` so assertions + rc capture below are robust.
set +e +u +o pipefail

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1))
    fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        head -10 <<<"$output" | sed 's/^/    /'; FAIL=$((FAIL + 1))
    fi
}
assert_not_contains() {
    local output="$1" unexpected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$unexpected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $unexpected)"
        head -10 <<<"$output" | sed 's/^/    /'; FAIL=$((FAIL + 1))
    fi
}

# --- Stubs for out-of-scope collaborators ------------------------------------
# acquire_remote_claim is ABS-184 (out of scope here): controllable win/loss.
CLAIM_RESULT=0        # 0 = win, 1 = loss
acquire_remote_claim() { return "$CLAIM_RESULT"; }
# Neutralize the dry-run spawn tail (model resolution) and the live spawn seam so
# no real spawn is launched — this suite only asserts the claim-assign layer.
resolve_spawn_model() { :; }
live_spawn() { :; }
# ensure_worktree is out-of-scope here (same class as live_spawn): the live
# scenarios drive spawn_dispatch with MODE=live + ORCH_WORKTREE_SPAWNS=1, which
# hits the real PILOT-66 provisioning gate. Unstubbed it ran `git worktree add -b
# <ticket>-auto`, leaking worktrees/branches into the SHARED .git that no teardown
# removed; a second run then collided on the stale T-*-auto branches (PILOT-66
# epic-integration bounce). Success no-op keeps the suite hermetic — the assign
# layer only needs provisioning to succeed, never inspects the worktree.
ensure_worktree() { :; }
# `tracker` is stubbed so the assign adapter call is counted (and can be forced to
# fail). Everything else the dispatch path might route through tracker succeeds.
ASSIGN_CALLS=0; ASSIGN_ARGS=""; TRACKER_ASSIGN_RC=0
tracker() {
    if [ "$1" = "assign" ]; then
        ASSIGN_CALLS=$((ASSIGN_CALLS + 1)); ASSIGN_ARGS="$2 $3"; return "$TRACKER_ASSIGN_RC"
    fi
    return 0
}

# Fresh admission state before each scenario: empty lock dir, full budget, one
# free concurrency slot, legacy (synchronous) cap path for deterministic counts.
reset_state() {
    rm -rf "$LOCKS_DIR"; mkdir -p "$LOCKS_DIR"
    LIVE_SPAWNS=0
    SPAWN_BUDGET=50
    CLAIM_RESULT=0
    ASSIGN_CALLS=0; ASSIGN_ARGS=""; TRACKER_ASSIGN_RC=0
    MODE="dry-run"
    ORCH_ASYNC_SPAWNS=0
    ORCH_MAX_CONCURRENT=3
    ORCH_CLAIM_MODE=on
    ORCH_CLAIM_ASSIGN=0
    ORCH_ASSIGNEE="acct-machine-A"
    unset ORCH_ASSIGNEE_BE_DEVELOPER
    rm -f "$ORCH_STATE_DIR/spawn-ledger-"* 2>/dev/null || true
}

# run_dispatch <ticket> — capture spawn_dispatch stdout (INTENT lines) + rc.
run_dispatch() {
    local out_file="$TEST_DIR/dispatch-out.txt"
    spawn_dispatch "$1" "Ready for Development" be-developer SPAWN "note" >"$out_file" 2>/dev/null
    RC=$?
    OUT="$(cat "$out_file")"
}

echo -e "${CYAN}=== Optional ORCH_CLAIM_ASSIGN human-visibility layer (ABS-186) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}AC: ORCH_CLAIM_ASSIGN=0 (default) — no assign call after a claim${NC}"
# =============================================================================
reset_state
ORCH_CLAIM_ASSIGN=0
run_dispatch T-off
assert_eq "$RC" "0"                                    "flag off: dispatch proceeds (rc 0)"
assert_eq "$ASSIGN_CALLS" "0"                          "flag off: tracker assign NEVER called"
assert_not_contains "$OUT" "CLAIM-ASSIGN"              "flag off: no CLAIM-ASSIGN intent"

# unset ORCH_CLAIM_ASSIGN must behave identically to "0" (default-off guard).
reset_state
unset ORCH_CLAIM_ASSIGN
ORCH_CLAIM_ASSIGN="${ORCH_CLAIM_ASSIGN:-0}"            # mirror the runner's config default
run_dispatch T-unset
assert_eq "$ASSIGN_CALLS" "0"                          "unset flag defaults to 0 (no assign)"

# =============================================================================
echo -e "\n${CYAN}AC: ORCH_CLAIM_ASSIGN=1 + won claim — assigns to ORCH_ASSIGNEE${NC}"
# =============================================================================
reset_state
ORCH_CLAIM_ASSIGN=1; CLAIM_RESULT=0; MODE="live"
run_dispatch T-won
assert_eq "$RC" "0"                                    "flag on/won: dispatch proceeds (rc 0)"
assert_eq "$ASSIGN_CALLS" "1"                          "flag on/won: tracker assign called exactly once"
assert_eq "$ASSIGN_ARGS" "T-won acct-machine-A"        "flag on/won: assigned to ORCH_ASSIGNEE"
assert_contains "$OUT" "INTENT CLAIM-ASSIGN ticket=T-won" "flag on/won: CLAIM-ASSIGN intent with context"

# Per-role override (ABS-126 mechanism) beats ORCH_ASSIGNEE.
reset_state
ORCH_CLAIM_ASSIGN=1; CLAIM_RESULT=0; MODE="live"
ORCH_ASSIGNEE_BE_DEVELOPER="acct-be-seat"
run_dispatch T-role
assert_eq "$ASSIGN_ARGS" "T-role acct-be-seat"         "flag on/won: ORCH_ASSIGNEE_<ROLE> override wins"

# dry-run logs the intent but performs NO real adapter write.
reset_state
ORCH_CLAIM_ASSIGN=1; CLAIM_RESULT=0; MODE="dry-run"
run_dispatch T-dry
assert_contains "$OUT" "INTENT CLAIM-ASSIGN ticket=T-dry" "dry-run: CLAIM-ASSIGN intent logged"
assert_eq "$ASSIGN_CALLS" "0"                          "dry-run: no real adapter assign"

# =============================================================================
echo -e "\n${CYAN}AC: a failed assign logs a warning and does not fail the spawn${NC}"
# =============================================================================
reset_state
ORCH_CLAIM_ASSIGN=1; CLAIM_RESULT=0; MODE="live"; TRACKER_ASSIGN_RC=1
spawn_dispatch T-fail "Ready for Development" be-developer SPAWN "note" >"$TEST_DIR/o.txt" 2>"$TEST_DIR/e.txt"
RC=$?
assert_eq "$RC" "0"                                    "failed assign: spawn NON-FATAL (rc 0)"
assert_eq "$ASSIGN_CALLS" "1"                          "failed assign: assign was attempted"
assert_contains "$(cat "$TEST_DIR/e.txt")" "non-fatal" "failed assign: warning logged (non-fatal)"
assert_eq "$LIVE_SPAWNS" "1"                           "failed assign: spawn still proceeds (slot consumed)"

# =============================================================================
echo -e "\n${CYAN}AC: the assignee is never the claim of record${NC}"
# =============================================================================
# A LOST claim never assigns: the assign strictly FOLLOWS a won claim; it is never
# read back to decide ownership. (ownership = acquire_remote_claim's verdict alone)
reset_state
ORCH_CLAIM_ASSIGN=1; CLAIM_RESULT=1; MODE="live"      # claim LOST
run_dispatch T-lost
assert_eq "$RC" "3"                                    "lost claim: rc 3 (re-queued)"
assert_eq "$ASSIGN_CALLS" "0"                          "lost claim: NEVER assigns (assign follows the claim)"
assert_contains "$OUT" "INTENT SKIP-CLAIMED ticket=T-lost" "lost claim: SKIP-CLAIMED (claim comment is authority)"

# mode=off: no claim staked => nothing won => never assigns even with flag on.
reset_state
ORCH_CLAIM_ASSIGN=1; ORCH_CLAIM_MODE=off; MODE="live"
run_dispatch T-modeoff
assert_eq "$ASSIGN_CALLS" "0"                          "mode=off: no won claim => no assign"
assert_not_contains "$OUT" "CLAIM-ASSIGN"              "mode=off: no CLAIM-ASSIGN intent"

# =============================================================================
echo -e "\n${CYAN}=== Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, $TOTAL total ===${NC}"
# =============================================================================
rm -rf "$TEST_DIR" 2>/dev/null || true
[ "$FAIL" -eq 0 ] || exit 1
