#!/bin/bash
# =============================================================================
# Test: remote-claim wiring into dispatch (ABS-185, spec §7 / §4.6)
# =============================================================================
# ABS-185 inserts ONE gate into spawn_dispatch, AFTER the §5.1 concurrency-cap
# admission and BEFORE the LIVE_SPAWNS/budget increment:
#
#     if [ "$ORCH_CLAIM_MODE" != "off" ] && ! acquire_remote_claim "$ticket"; then
#         release_lock "$ticket"; intent SKIP-CLAIMED ...; return 3
#     fi
#
# This suite drives the REAL spawn_dispatch (sourced, no poll loop) and stubs the
# out-of-scope acquire_remote_claim (ABS-184, "story 3") with a controllable
# win/loss so the placement and lock/slot bookkeeping are asserted directly:
#   - off (default): claim never staked, dispatch path byte-for-byte unchanged
#   - on + won:      proceeds to spawn exactly as today (slot + budget consumed)
#   - on + lost:     releases the local lock, consumes NO slot/budget, re-queues (rc 3)
#   - on + over-cap: deferred for cap is NEVER claimed -> stays free for peers
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-claim-dispatch.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Isolated state dir: LOCKS_DIR / run.log / ledger are all derived from it at
# source time, so it MUST be exported before sourcing.
TEST_DIR="$(mktemp -d /tmp/claim-dispatch-test-XXXXXX)"
export ORCH_STATE_DIR="$TEST_DIR/.orchestrator"
mkdir -p "$ORCH_STATE_DIR"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

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
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo "$output" | head -10 | sed 's/^/    /'; FAIL=$((FAIL + 1))
    fi
}
assert_not_contains() {
    local output="$1" unexpected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$unexpected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $unexpected)"
        echo "$output" | head -10 | sed 's/^/    /'; FAIL=$((FAIL + 1))
    fi
}

# --- Stubs for out-of-scope collaborators ------------------------------------
# acquire_remote_claim is ABS-184 (story 3, out of scope here): stub it as a
# controllable win/loss that also counts stakes, so we can prove WHEN dispatch
# does (and does not) stake a claim.
CLAIM_RESULT=0        # 0 = win, 1 = loss
CLAIM_CALLS=0
acquire_remote_claim() { CLAIM_CALLS=$((CLAIM_CALLS + 1)); return "$CLAIM_RESULT"; }
# Neutralize the dry-run spawn tail (model resolution) so no real tracker is hit.
resolve_spawn_model() { :; }

lock_state() { [ -d "$(lock_dir_for "$1")" ] && echo held || echo free; }

# Fresh admission state before each scenario: empty lock dir, full budget, one
# free concurrency slot, legacy (synchronous) cap path for deterministic counts.
reset_state() {
    rm -rf "$LOCKS_DIR"; mkdir -p "$LOCKS_DIR"
    LIVE_SPAWNS=0
    SPAWN_BUDGET=50
    CLAIM_CALLS=0
    CLAIM_RESULT=0
    MODE="dry-run"
    ORCH_ASYNC_SPAWNS=0
    ORCH_MAX_CONCURRENT=3
    rm -f "$ORCH_STATE_DIR/spawn-ledger-"* 2>/dev/null || true
}

# run_dispatch <ticket> — capture spawn_dispatch stdout (INTENT lines) + rc.
# Redirect to a file rather than $(...) so spawn_dispatch runs in THIS shell and
# its LIVE_SPAWNS/SPAWN_BUDGET/CLAIM_CALLS mutations are observable (a command
# substitution would run it in a subshell and lose them).
run_dispatch() {
    local out_file="$TEST_DIR/dispatch-out.txt"
    spawn_dispatch "$1" "Ready for Development" be-developer SPAWN "note" >"$out_file" 2>/dev/null
    RC=$?
    OUT="$(cat "$out_file")"
}

echo -e "${CYAN}=== Remote-claim wiring into dispatch (ABS-185) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}AC: ORCH_CLAIM_MODE=off (default) — path unchanged, no claim staked${NC}"
# =============================================================================
reset_state
ORCH_CLAIM_MODE=off
run_dispatch T-off
assert_eq "$RC" "0"                              "off: dispatch proceeds (rc 0)"
assert_eq "$CLAIM_CALLS" "0"                     "off: acquire_remote_claim NEVER called (no claim staked)"
assert_contains "$OUT" "INTENT SPAWN ticket=T-off" "off: spawns exactly as today"
assert_not_contains "$OUT" "SKIP-CLAIMED"        "off: no SKIP-CLAIMED on the unchanged path"
assert_eq "$LIVE_SPAWNS" "1"                     "off: one spawn slot consumed"
assert_eq "$SPAWN_BUDGET" "49"                   "off: one budget unit consumed"

# unset ORCH_CLAIM_MODE must behave identically to "off" (default-off guard).
reset_state
unset ORCH_CLAIM_MODE
ORCH_CLAIM_MODE="${ORCH_CLAIM_MODE:-off}"        # mirror the runner's config default
run_dispatch T-unset
assert_eq "$CLAIM_CALLS" "0"                     "unset ORCH_CLAIM_MODE defaults to off (no claim staked)"
assert_contains "$OUT" "INTENT SPAWN ticket=T-unset" "unset: spawns exactly as today"

# =============================================================================
echo -e "\n${CYAN}AC: ORCH_CLAIM_MODE=on + won claim — proceeds to spawn as today${NC}"
# =============================================================================
reset_state
ORCH_CLAIM_MODE=on; CLAIM_RESULT=0
run_dispatch T-won
assert_eq "$RC" "0"                              "won: dispatch proceeds (rc 0)"
assert_eq "$CLAIM_CALLS" "1"                     "won: claim staked exactly once (after admission)"
assert_contains "$OUT" "INTENT SPAWN ticket=T-won" "won: spawns exactly as today"
assert_not_contains "$OUT" "SKIP-CLAIMED"        "won: no SKIP-CLAIMED"
assert_eq "$LIVE_SPAWNS" "1"                     "won: one spawn slot consumed"
assert_eq "$SPAWN_BUDGET" "49"                   "won: one budget unit consumed"

# =============================================================================
echo -e "\n${CYAN}AC: lost claim releases the lock, consumes no slot/budget, re-queues${NC}"
# =============================================================================
reset_state
ORCH_CLAIM_MODE=on; CLAIM_RESULT=1
run_dispatch T-lost
assert_eq "$RC" "3"                              "lost: rc 3 (re-queued into the pending set, like DEFER-CAP)"
assert_contains "$OUT" "INTENT SKIP-CLAIMED ticket=T-lost" "lost: SKIP-CLAIMED with role/to context"
assert_not_contains "$OUT" "INTENT SPAWN ticket=T-lost"    "lost: never reaches the spawn"
assert_eq "$LIVE_SPAWNS" "0"                     "lost: consumes NO spawn slot"
assert_eq "$SPAWN_BUDGET" "50"                   "lost: consumes NO budget"
assert_eq "$(lock_state T-lost)" "free"          "lost: local single-flight lock released"

# =============================================================================
echo -e "\n${CYAN}AC: a ticket deferred for cap is NEVER claimed (stays free for peers)${NC}"
# =============================================================================
reset_state
ORCH_CLAIM_MODE=on; CLAIM_RESULT=0
ORCH_MAX_CONCURRENT=1; LIVE_SPAWNS=1             # already at the cap -> next dispatch defers
run_dispatch T-defer
assert_eq "$RC" "3"                              "over-cap: rc 3 (DEFER-CAP)"
assert_contains "$OUT" "INTENT DEFER-CAP ticket=T-defer" "over-cap: deferred, not dropped"
assert_eq "$CLAIM_CALLS" "0"                     "over-cap: deferred ticket is NEVER claimed (no backlog hogging)"
assert_not_contains "$OUT" "SKIP-CLAIMED"        "over-cap: no claim attempted at all"
assert_eq "$(lock_state T-defer)" "free"         "over-cap: lock released on defer"
# Held claims per machine can never exceed ORCH_MAX_CONCURRENT: a claim is staked
# ONLY after cap admission (above), so in-flight claims are bounded by the same
# cap that bounds in-flight spawns.

# =============================================================================
echo -e "\n${CYAN}=== Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, $TOTAL total ===${NC}"
# =============================================================================
rm -rf "$TEST_DIR" 2>/dev/null || true
[ "$FAIL" -eq 0 ] || exit 1
