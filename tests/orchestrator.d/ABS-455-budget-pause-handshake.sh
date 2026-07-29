# =============================================================================
# ABS-455 — budget-pause ergonomics: operator push + restart handshake
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md). In scope: assert_*, orch / tracker / new_env /
# baseline / cleanup_env, PASS/FAIL/TOTAL.
#
# THE DEFECT THIS PINS (retro 2026-07-19)
# Per-run/per-day spawn-budget exhaustion (ADR-A-0009) ended the runner SILENTLY
# (only a tracker comment, missable at 03:00) or — worse — left it holding
# forever in STANDSTILL with no exit (the ~05:50 standstill-without-exit; one
# pause was misdiagnosed as a crash). A supervisor wrapper had no exit-code to
# restart on without losing the ADR-A-0009 cost-review point.
#
# WHAT ABS-455 ADDS
#   AC1: a budget pause emits ONE clear exit line + an operator push.
#   AC2: the standstill-WITHOUT-exit path is eliminated for the budget case —
#        a budget-caused standstill converts to the SAME clean budget-pause exit
#        (human gates still hold, distinguishably).
#   AC3: a distinct handshake EXIT CODE (default 75, ORCH_BUDGET_PAUSE_EXIT_CODE)
#        + a persisted, monotonic restart counter (the cost gate stays auditable).
# =============================================================================

tracker() { bash "$TRACKER" "$@"; }   # restore the real adapter (ABS-225 idiom)

echo -e "\n${CYAN}=== ABS-455 budget-pause restart handshake ===${NC}\n"

# --- AC3 + AC1: direct dispatch-time brake -> distinct exit code + clear line ---
# ORCH_MAX_SPAWNS_PER_RUN=0 => the very first dispatch hits budget_exhausted, so
# the run halts cleanly on --once and exits with the handshake code.
new_env
T=$(tracker create --type ticket --title "ABS-455 budget exit" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
baseline                         # drain creation/transition events at the DEFAULT budget
export ORCH_MAX_SPAWNS_PER_RUN=0 # ...then starve the budget so the next dispatch brakes
rc=0
ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "75" "ABS-455 AC3: budget exhaustion exits with the restart-handshake code (default 75)"
_rl="$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true)"
assert_contains "$_rl" "BUDGET-PAUSE exit" "ABS-455 AC1: a clear, unambiguous budget-pause exit line is emitted"
assert_contains "$_rl" "restart-count=1" "ABS-455 AC3: the exit line names the restart counter (ADR-A-0009 review point)"
assert_eq "$(cat "$ORCH_STATE_DIR/budget-restart-count" 2>/dev/null)" "1" "ABS-455 AC3: the restart counter is persisted in the state dir"

# --- AC3: the counter is MONOTONIC across restarts (supervisor accounting) ------
rc=0
ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "75" "ABS-455 AC3: a second budget pause exits with the same handshake code"
assert_eq "$(cat "$ORCH_STATE_DIR/budget-restart-count" 2>/dev/null)" "2" "ABS-455 AC3: each budget pause bumps the persisted restart counter (survives restarts)"
cleanup_env

# --- AC3: the handshake exit code is configurable -------------------------------
new_env
T=$(tracker create --type ticket --title "ABS-455 custom code" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
baseline
export ORCH_MAX_SPAWNS_PER_RUN=0
export ORCH_BUDGET_PAUSE_EXIT_CODE=42
rc=0
ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "42" "ABS-455 AC3: ORCH_BUDGET_PAUSE_EXIT_CODE overrides the handshake code"
cleanup_env

# --- AC2: a budget-caused STANDSTILL converts to a clean exit, not a forever hold
# Seed an exhausted backoff so dispatch SKIPS before the budget brake (BUDGET_HALT
# is NOT set on the dispatch path), AND exhaust the per-DAY budget so no seat will
# ever spawn this run. Without the fix the runner would loop into STANDSTILL-HELD
# forever (the 05:50 incident); with it, the watchdog converts to a budget exit.
new_env
export ORCH_STANDSTILL_SWEEPS=3
# Pin the per-day cap so this scenario is independent of the shipped default
# (PILOT-63 AC3 recalibrated it to 400; hardcoding "just above 200" here silently
# stopped exhausting the budget). Seed one line over the pinned cap.
export ORCH_MAX_SPAWNS_PER_DAY=200
T=$(tracker create --type ticket --title "ABS-455 budget standstill" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
baseline
printf '%s\t%s\t%s\n' "Ready for Development" "$(( $(date -u +%s) + 1800 ))" "1800" \
    > "$ORCH_STATE_DIR/backoff-$T"
_ledger="$ORCH_STATE_DIR/spawn-ledger-$(date -u +%Y%m%d)"
i=0; while [ "$i" -lt 205 ]; do echo "seed" >> "$_ledger"; i=$((i + 1)); done
rc=0
ORCH_RECONCILE_ON_STARTUP=1 ORCH_RECONCILE_EVERY_N_CYCLES=1 ORCH_POLL_INTERVAL=0 \
    ORCH_MAX_CYCLES=6 orch --dry-run >/dev/null 2>&1 || rc=$?
_rl="$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true)"
assert_eq "$rc" "75" "ABS-455 AC2: a budget-caused standstill exits with the handshake code, not a forever hold"
assert_contains "$_rl" "STANDSTILL-BUDGET-EXIT" "ABS-455 AC2: the standstill-without-exit path is converted to a clean budget-pause exit"
assert_not_contains "$_rl" "STANDSTILL-HELD" "ABS-455 AC2: the budget standstill never reaches the forever-hold state"
cleanup_env
