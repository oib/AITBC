# =============================================================================
# PILOT-47 — progress-aware spawn budget: drain, auto-extend, per-ticket cap
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/test-orchestrator.sh. In scope:
# assert_*, REPO_ROOT / ORCH / TRACKER, new_env / baseline / cleanup_env, orch /
# tracker, PASS/FAIL/TOTAL.
#
# THE DEFECT THIS PINS (operator finding, v3-Pilot #5)
# ORCH_MAX_SPAWNS_PER_RUN hard-stopped a HEALTHY run (6/10 Done, no churn) mid-
# flight via BUDGET-PAUSE/exit 75, forcing repeated manual restarts with a raised
# cap. The runaway intent (ADR-A-0009) is right but the sensor was progress-blind.
#
# WHAT PILOT-47 ADDS
#   AC1 DRAIN: at the SOFT cap the runner holds NEW intake (SKIP-DRAIN-INTAKE) but
#        lets in-flight tickets (already spawned this run) finish, then ends the
#        run cleanly (DRAIN-COMPLETE, exit 0 — NOT the exit-75 pause).
#   AC2 auto-extend: while the run shows progress (Done count rising) the soft cap
#        grows in increments (SPAWN-BUDGET-EXTEND) instead of stopping.
#   AC3 per-ticket cap: a single cyclically-respawning ticket -> Needs PO Decision
#        (BLOCK-TICKET-SPAWN-CAP); the run continues.
#   AC4 hard backstop: the absolute ceiling (soft cap x ORCH_SPAWN_BUDGET_HARD_
#        MULTIPLE) and the per-day ledger still fail-close to exit 75.
#   AC5 marker semantics: exit 75 + BUDGET-PAUSE stay for the hard case; drain +
#        auto-extend emit NEW runlog lines only (no new marker file under state).
# =============================================================================

tracker() { bash "$TRACKER" "$@"; }   # restore the real adapter (ABS-225 idiom)

echo -e "\n${CYAN}=== PILOT-47 progress-aware spawn budget ===${NC}\n"

# --- Gate unit scenarios: drive spawn_dispatch / try_autoextend_budget directly
# in one clean orchestrator process (fresh budget/globals), the layer the budget
# decision lives in. Mirrors the ABS-308 isolated-subshell idiom. spawn_dispatch
# is called WITHOUT command substitution (redirected to a file) so its global
# side effects (DRAIN_MODE, BUDGET_HALT) are observable; count_done_tickets is
# stubbed so the progress sensor is deterministic (decoupled from adapter
# transition validity).
_p47="$(bash -c '
    set -u
    REPO_ROOT="'"$REPO_ROOT"'"; TRACKER="'"$TRACKER"'"
    export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml" TRACKER_CMD="$TRACKER"
    TD="$(mktemp -d /tmp/pilot47-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TD/tickets"; mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
    export ORCH_STATE_DIR="$TD/state"; mkdir -p "$ORCH_STATE_DIR"
    export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"
    export ORCH_REQUIRE_START_LABEL=0
    source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1
    set +e +o pipefail          # the runner sources with set -euo; relax for the harness
    tracker() { bash "$TRACKER" "$@"; }
    O="$TD/o"
    FAKE_DONE=0; count_done_tickets() { echo "$FAKE_DONE"; }
    T=$(tracker create --type ticket --title work | awk "{print \$NF}")
    tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null 2>&1

    # (AC1) soft cap spent, a NEW intake (0 prior spawns) is HELD for drain, and
    # DRAIN mode is entered (observed as a real global side effect).
    MODE=dry-run; SPAWN_BUDGET=0; SPAWNS_USED=5; ORCH_SPAWN_BUDGET_AUTOEXTEND=0
    DRAIN_MODE=0; TICKET_SPAWNS=""
    spawn_dispatch "$T" "Ready for Development" po-agent reconcile "" "" >"$O" 2>/dev/null
    echo "A1_INTAKE_DRAIN=$(grep -c SKIP-DRAIN-INTAKE "$O")"
    echo "A1_DRAINMODE=$DRAIN_MODE"

    # (AC1) an in-flight CONTINUATION (>=1 prior spawn) falls through and spawns
    # even at the exhausted soft cap — the pipeline drains to completion.
    SPAWN_BUDGET=0; SPAWNS_USED=5; TICKET_SPAWNS="[$T|3]"; LIVE_SPAWNS=0
    spawn_dispatch "$T" "In Review" system-architect reconcile "" "" >"$O" 2>/dev/null
    echo "A1_CONT_SPAWN=$(grep -c "INTENT SPAWN" "$O")"

    # (AC2) with progress (Done rose) the soft cap auto-extends by the increment;
    # a second call with no fresh progress does NOT (needs a new Done).
    ORCH_MAX_SPAWNS_PER_RUN=4; ORCH_SPAWN_BUDGET_AUTOEXTEND=1; ORCH_SPAWN_BUDGET_AUTOEXTEND_PCT=25
    ORCH_SPAWN_BUDGET_HARD_MULTIPLE=2; SPAWN_BUDGET=0; SPAWNS_USED=4; DONE_AT_LAST_CHECK=0
    SPAWN_BUDGET_EXTENDS=0; FAKE_DONE=3
    if try_autoextend_budget; then echo "A2_EXTEND1=yes"; else echo "A2_EXTEND1=no"; fi
    echo "A2_BUDGET_AFTER=$SPAWN_BUDGET"
    if try_autoextend_budget; then echo "A2_EXTEND2=yes"; else echo "A2_EXTEND2=no"; fi
    echo "A2_EXTEND_RUNLOG=$(grep -c SPAWN-BUDGET-EXTEND "$ORCH_RUN_LOG")"

    # (AC2) knob off -> never extends even with progress.
    ORCH_SPAWN_BUDGET_AUTOEXTEND=0; SPAWN_BUDGET=0; SPAWNS_USED=4; DONE_AT_LAST_CHECK=0; FAKE_DONE=9
    if try_autoextend_budget; then echo "A2_OFF=yes"; else echo "A2_OFF=no"; fi

    # (AC2/AC4) auto-extend never crosses the hard backstop (no room at the ceiling).
    ORCH_SPAWN_BUDGET_AUTOEXTEND=1; ORCH_MAX_SPAWNS_PER_RUN=4; ORCH_SPAWN_BUDGET_HARD_MULTIPLE=2
    SPAWN_BUDGET=0; SPAWNS_USED=8; DONE_AT_LAST_CHECK=0; FAKE_DONE=9   # used==hard_max=8
    if try_autoextend_budget; then echo "A4_EXTEND_ATCEIL=yes"; else echo "A4_EXTEND_ATCEIL=no"; fi

    # (AC4) hard backstop reached -> pause_for_budget (exit-75 handshake), SKIP-BUDGET,
    # BUDGET_HALT set (observed as a global side effect).
    MODE=dry-run; ORCH_MAX_SPAWNS_PER_RUN=50; ORCH_SPAWN_BUDGET_HARD_MULTIPLE=2
    SPAWNS_USED=100; BUDGET_HALT=0; SPAWN_BUDGET=0; TICKET_SPAWNS=""
    spawn_dispatch "$T" "Ready for Development" po-agent reconcile "" "" >"$O" 2>/dev/null
    echo "A4_HARD_SKIPBUDGET=$(grep -c "INTENT SKIP-BUDGET " "$O")"
    echo "A4_HALT=$BUDGET_HALT"
    if grep -q "HARD spawn backstop" "$ORCH_RUN_LOG"; then echo "A4_HARDLINE=yes"; else echo "A4_HARDLINE=no"; fi

    # (AC5) no drain/extend MARKER file was created under the state dir (runlog
    # lines only — no new marker class in work/.orchestrator*).
    echo "A5_MARKERS=$(find "$ORCH_STATE_DIR" -maxdepth 1 -type f \( -name "*drain*" -o -name "*extend*" -o -name "*autoextend*" \) 2>/dev/null | grep -c .)"
    rm -rf "$TD"
')"

assert_contains "$_p47" "A1_INTAKE_DRAIN=1" "PILOT-47 AC1: a NEW intake at the exhausted soft cap is held (SKIP-DRAIN-INTAKE)"
assert_contains "$_p47" "A1_DRAINMODE=1"    "PILOT-47 AC1: reaching the soft cap without an extend enters DRAIN mode"
assert_contains "$_p47" "A1_CONT_SPAWN=1"   "PILOT-47 AC1: an in-flight continuation still spawns at the exhausted soft cap (pipeline drains)"
assert_contains "$_p47" "A2_EXTEND1=yes"    "PILOT-47 AC2: progress (Done rose) auto-extends the soft cap"
assert_contains "$_p47" "A2_BUDGET_AFTER=1" "PILOT-47 AC2: the extension adds the increment to the remaining budget"
assert_contains "$_p47" "A2_EXTEND2=no"     "PILOT-47 AC2: a second extend needs FRESH progress (no double-extend on the same Done)"
assert_contains "$_p47" "A2_EXTEND_RUNLOG=1" "PILOT-47 AC2: the extension emits a SPAWN-BUDGET-EXTEND runlog line"
assert_contains "$_p47" "A2_OFF=no"         "PILOT-47 AC2: ORCH_SPAWN_BUDGET_AUTOEXTEND=0 never extends"
assert_contains "$_p47" "A4_EXTEND_ATCEIL=no" "PILOT-47 AC4: auto-extend never crosses the hard backstop"
assert_contains "$_p47" "A4_HARD_SKIPBUDGET=1" "PILOT-47 AC4: the hard backstop brakes with SKIP-BUDGET"
assert_contains "$_p47" "A4_HALT=1"         "PILOT-47 AC4: the hard backstop sets BUDGET_HALT (exit-75 handshake)"
assert_contains "$_p47" "A4_HARDLINE=yes"   "PILOT-47 AC4: the hard-backstop pause names the ceiling in run.log"
assert_contains "$_p47" "A5_MARKERS=0"      "PILOT-47 AC5: drain/auto-extend create NO new marker file under the state dir"
unset _p47

# --- (AC3) per-ticket cap escalates a cyclic ticket to Needs PO Decision (live).
new_env
T=$(tracker create --type ticket --title cyclic --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
baseline
_p47c="$(bash -c '
    set -u
    REPO_ROOT="'"$REPO_ROOT"'"; TRACKER="'"$TRACKER"'"
    export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml" TRACKER_CMD="$TRACKER"
    export MOCK_TRACKER_TICKETS_DIR="'"$MOCK_TRACKER_TICKETS_DIR"'"
    export ORCH_STATE_DIR="'"$ORCH_STATE_DIR"'"; export ORCH_RUN_LOG="$ORCH_STATE_DIR/run.log"
    export ORCH_REQUIRE_START_LABEL=0
    source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1
    set +e +o pipefail; MODE=live
    tracker() { bash "$TRACKER" "$@"; }
    ORCH_MAX_SPAWNS_PER_TICKET=3; SPAWN_BUDGET=10; SPAWNS_USED=3; TICKET_SPAWNS="['"$T"'|3]"
    spawn_dispatch "'"$T"'" "In Review" system-architect reconcile "" "" >"$ORCH_STATE_DIR/o" 2>/dev/null
    echo "C_INTENT=$(grep -c "INTENT BLOCK-TICKET-SPAWN-CAP" "$ORCH_STATE_DIR/o")"
    echo "C_STATUS=$(tracker get "'"$T"'" | sed -n "s/^status: //p" | head -1)"
')"
assert_contains "$_p47c" "C_INTENT=1"                "PILOT-47 AC3: a ticket at the per-ticket cap emits BLOCK-TICKET-SPAWN-CAP"
assert_contains "$_p47c" "C_STATUS=Needs PO Decision" "PILOT-47 AC3: the capped ticket is escalated to Needs PO Decision"
unset _p47c
cleanup_env

# --- (AC1) integration: a soft-cap run ENDS CLEANLY (exit 0 + DRAIN-COMPLETE),
# not the exit-75 pause. cap=1 spawns one ticket; the other NEW intake is held;
# the per-ticket cap (2) breaks the stub's non-advancing respawn so drain settles.
# A generous hard multiple keeps the absolute ceiling clear of the drain window.
new_env
export ORCH_MAX_SPAWNS_PER_RUN=1
export ORCH_SPAWN_BUDGET_AUTOEXTEND=0     # isolate drain from auto-extend
export ORCH_MAX_SPAWNS_PER_TICKET=2       # bound the stub's non-advancing respawn
export ORCH_SPAWN_BUDGET_HARD_MULTIPLE=10 # hard_max=10 >> the few drain spawns
export ORCH_BUDGET_PUSH=0
E=$(tracker create --type epic --title "drain epic")
T1=$(tracker create --type ticket --title D1 --parent "$E" --role be-developer)
T2=$(tracker create --type ticket --title D2 --parent "$E" --role be-developer)
baseline
tracker transition "$T1" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T2" "Ready for Development" --actor po --reason go >/dev/null
rc=0
ORCH_RECONCILE_ON_STARTUP=1 ORCH_RECONCILE_EVERY_N_CYCLES=1 ORCH_POLL_INTERVAL=0 \
    ORCH_MAX_CYCLES=12 orch --live >/dev/null 2>&1 || rc=$?
_rl="$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true)"
assert_eq "$rc" "0" "PILOT-47 AC1: a soft-cap run ends CLEANLY (exit 0), not the exit-75 budget pause"
assert_contains "$_rl" "SPAWN-BUDGET-DRAIN" "PILOT-47 AC1: the run logs entering DRAIN at the soft cap"
assert_contains "$_rl" "DRAIN-COMPLETE" "PILOT-47 AC1: the run logs a clean DRAIN-COMPLETE once in-flight work finished"
assert_not_contains "$_rl" "BUDGET-PAUSE exit" "PILOT-47 AC1: a soft-cap drain never takes the exit-75 hard-pause path"
cleanup_env
