# =============================================================================
# PILOT-63 — a failed admission must not cost a budget unit (AC1 + AC4)
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (quantified on the 2026-07-25 BUDGET-PAUSE)
# The per-day spawn budget was decremented at admission (record_daily_spawn, one
# ledger line per spawn) BEFORE the worktree-provisioning fail-closed gate in
# live_spawn. So every INTENT-SKIP-NOWORKTREE — a spawn that never reached a
# model — still cost one budget unit: 125 of the 200 units on that pause were
# such non-spawns, and the run hard-stopped 62.5% early on self-inflicted waste.
#
# THE FIX (PILOT-63 AC1): spawn_dispatch now provisions the worktree BEFORE the
# decrement; a provisioning failure rests the ticket with no ledger line. Every
# other "never reached a model" case (kill-switch, outage, halt, backoff, lock,
# cap, lost claim) already returned above the decrement, so worktree failure was
# the sole leak.
#
# AC4 FALSIFICATION: drive N failed worktree provisionings and assert the daily
# spawn ledger — the persisted budget counter — stays EMPTY. A positive control
# (a provisionable ticket) then charges exactly one unit, so the assertion is not
# vacuous (ABS-370 suite-integrity concern).
# =============================================================================

echo -e "\n${CYAN}=== PILOT-63 — failed admissions must not cost budget (AC1/AC4) ===${NC}\n"

# --- AC4: N failed worktree provisionings => daily budget ledger unchanged -----
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$TEST_DIR/target"; mkdir -p "$TARGET"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
Tfail=$(tracker create --type ticket --title "PILOT-63 budget-safe fail story" --role be-developer)
# Occupy the <ticket>-auto branch in the main working tree so `git worktree add`
# fails "already checked out elsewhere" — a representative provisioning failure
# (same mechanism as the C9b fail-closed test in the suite body).
git -C "$TARGET" checkout -q -b "$Tfail-auto"
baseline
tracker transition "$Tfail" "Ready for Development" --actor po --reason go >/dev/null

ledger="$ORCH_STATE_DIR/spawn-ledger-$(date -u +%Y%m%d)"
n=0
while [ "$n" -lt 3 ]; do
    out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null || true)
    assert_contains "$out" "INTENT SKIP-NOWORKTREE ticket=$Tfail" \
        "PILOT-63 AC4: worktree provisioning fails closed (attempt $((n + 1)))"
    assert_not_contains "$out" "INTENT HANDOFF ticket=$Tfail" \
        "PILOT-63 AC4: no spawn reached a seat on the failed provisioning (attempt $((n + 1)))"
    n=$((n + 1))
done
charged=$([ -f "$ledger" ] && wc -l < "$ledger" | tr -d ' ' || echo 0)
assert_eq "$charged" "0" \
    "PILOT-63 AC4: 3 failed worktree provisionings charged 0 budget units (daily ledger unchanged)"

unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
cleanup_env

# --- positive control: a provisionable spawn DOES charge exactly one unit ------
# Guards against a vacuous AC4 assertion — the ledger must grow when a spawn
# actually reaches a seat, so "0" above is meaningful.
new_env
export ORCH_WORKTREE_SPAWNS=1
TARGET="$TEST_DIR/target"; mkdir -p "$TARGET"
warm_git_repo "$TARGET"
export ORCH_TARGET_REPO="$TARGET"
Tok=$(tracker create --type ticket --title "PILOT-63 provisionable story" --role be-developer)
baseline
tracker transition "$Tok" "Ready for Development" --actor po --reason go >/dev/null
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1
ledger="$ORCH_STATE_DIR/spawn-ledger-$(date -u +%Y%m%d)"
charged_ok=$([ -f "$ledger" ] && wc -l < "$ledger" | tr -d ' ' || echo 0)
assert_eq "$charged_ok" "1" \
    "PILOT-63 AC4 control: a spawn that reaches a seat charges exactly one budget unit"

unset ORCH_TARGET_REPO
export ORCH_WORKTREE_SPAWNS=0
cleanup_env
