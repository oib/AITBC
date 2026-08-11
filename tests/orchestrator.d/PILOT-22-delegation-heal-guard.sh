# =============================================================================
# PILOT-22 — Orphan-heal × external delegation = double dispatch: the ABS-451
#            In-Progress orphan self-heal must respect a delegation marker and
#            the Backlog opt-in gate, and dispatch must re-check the opt-in, so
#            heal+dispatch cannot compose into a duplicate delivery.
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (observed live: ABS-492, 2026-07-20 12:33Z)
# ABS-492 was delegated to the v3 pilot (twin PILOT-2), deliberately WITHOUT the
# orchestrator-ready label. The operator's booking sync mirrored "In Progress"
# onto the ticket to keep the system of record honest. The ABS-451 self-heal
# then classified it as an unowned In-Progress orphan, healed it to "Ready for
# Development", and the runner DISPATCHED a duplicate be-developer seat that
# reimplemented the delegated change in parallel. The opt-in label gate was
# bypassed because heal+dispatch both operate BELOW it.
#
# WHAT PILOT-22 ADDS
#   1. heal_inprogress_orphan() defers (does NOT heal to a dispatchable status)
#      when the ticket carries a delegation marker (AC1) OR fails the Backlog
#      opt-in gate (AC2) — so the heal never manufactures a below-the-gate
#      dispatchable state. Deferral falls through to the ABS-116 NOTIFY safety net.
#   2. dispatch() re-checks the marker at the Ready-for-Development implementer
#      entry: a delegated ticket is SKIP-DELEGATED, never spawned — no
#      below-the-gate dispatch path (AC2, defense in depth).
#   3. A genuine crashed-seat orphan (opt-in label present, no delegation) still
#      heals and dispatches exactly as ABS-451 does today (AC3).
# =============================================================================

echo -e "\n${CYAN}=== PILOT-22 orphan-heal respects delegation + opt-in ===${NC}\n"

# Park a ticket in an UNOWNED In Progress (no lock), draining every intermediate
# event via baseline so no seat is spawned. Path: RfD -> In Progress.
_pilot22_park_inprogress() {
    local t="$1"
    tracker transition "$t" "Ready for Development" --actor po-agent --reason "setup" >/dev/null
    tracker transition "$t" "In Progress" --actor tdm \
        --reason "external system of record booked In Progress (the ABS-492 bug)" >/dev/null
    baseline   # dry-run + reconcile-off: drains events without spawning a seat
}
_pilot22_status() { tracker get "$1" | sed -n 's/^status: //p' | head -1; }

# --- AC1: delegated + ownerless In-Progress -> heal DEFERS, never dispatches ------
# The ticket IS opted-in (orchestrator-ready) so the ONLY thing stopping the heal
# is the delegation marker — isolates the AC1 guard. Reproduces ABS-492.
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_INPROGRESS_HEAL_SWEEPS=3
export ORCH_CRASH_REPAIR_SECONDS=0   # crash-repair off: heal is the only mover

TD=$(tracker create --type ticket --title "PILOT-22 delegated orphan" \
        --label orchestrator-ready --label delegated --role be-developer)
_pilot22_park_inprogress "$TD"

out_del=""
for _ in 1 2 3 4; do
    out_del=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
done
assert_not_contains "$out_del" "INTENT INPROGRESS-HEAL ticket=$TD" \
    "PILOT-22 AC1: a delegated orphan is NOT healed to a dispatchable status"
assert_not_contains "$out_del" "INTENT SPAWN ticket=$TD" \
    "PILOT-22 AC1: a delegated orphan never spawns a duplicate seat (ABS-492)"
assert_eq "$(_pilot22_status "$TD")" "In Progress" \
    "PILOT-22 AC1: the delegated orphan stays parked In Progress"

# AC4 idempotency: a further sweep emits no new heal transition (still parked).
out_del2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out_del2" "INTENT INPROGRESS-HEAL ticket=$TD" \
    "PILOT-22 AC4: re-running the sweep over the parked delegated ticket is idempotent"
assert_eq "$(_pilot22_status "$TD")" "In Progress" \
    "PILOT-22 AC4: still In Progress after the repeat sweep (no duplicate transition)"
cleanup_env

# --- AC2: ownerless In-Progress WITHOUT the opt-in label -> heal does NOT produce -
# a dispatchable status (the heal honours the Backlog opt-in gate; no
# below-the-gate path). This is the exact ABS-492 shape (no orchestrator-ready).
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_INPROGRESS_HEAL_SWEEPS=3
export ORCH_CRASH_REPAIR_SECONDS=0
# ORCH_REQUIRE_START_LABEL defaults to 1 (gate ON) — do not set it.

TU=$(tracker create --type ticket --title "PILOT-22 unopted orphan" --role be-developer)
_pilot22_park_inprogress "$TU"

out_unopt=""
for _ in 1 2 3 4; do
    out_unopt=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
done
assert_not_contains "$out_unopt" "INTENT INPROGRESS-HEAL ticket=$TU" \
    "PILOT-22 AC2: heal honours the opt-in gate — no dispatchable status manufactured"
assert_not_contains "$out_unopt" "INTENT SPAWN ticket=$TU" \
    "PILOT-22 AC2: an unopted orphan never spawns a seat (no below-the-gate path)"
assert_eq "$(_pilot22_status "$TU")" "In Progress" \
    "PILOT-22 AC2: the unopted orphan stays parked In Progress"
cleanup_env

# --- AC3: a GENUINE crashed-seat orphan (opt-in label, no delegation) still heals -
# Proves no regression to the legitimate ABS-451 self-heal.
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_INPROGRESS_HEAL_SWEEPS=3
export ORCH_CRASH_REPAIR_SECONDS=0

TL=$(tracker create --type ticket --title "PILOT-22 legit orphan" \
        --label orchestrator-ready --role be-developer)
_pilot22_park_inprogress "$TL"

out_legit=""
for _ in 1 2 3; do
    out_legit=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
done
assert_contains "$out_legit" "INTENT INPROGRESS-HEAL ticket=$TL" \
    "PILOT-22 AC3: a legit opted-in, non-delegated orphan still heals (ABS-451 intact)"
assert_eq "$(_pilot22_status "$TL")" "Ready for Development" \
    "PILOT-22 AC3: the legit orphan reaches the spawnable Ready for Development"
cleanup_env

# --- AC2 (dispatch layer): a delegated ticket at Ready for Development is --------
# SKIP-DELEGATED, never spawned — even when the marker is a DO-NOT-DISPATCH
# decision annotation rather than a label (covers the ticket_is_delegated OR).
new_env
export ORCH_MAX_CONCURRENT=10

TX=$(tracker create --type ticket --title "PILOT-22 delegated at RfD" \
        --label orchestrator-ready --role be-developer)
baseline
tracker transition "$TX" "Ready for Development" --actor po-agent --reason "setup" >/dev/null
tracker comment "$TX" --kind decision --actor operator \
    --body "DO-NOT-DISPATCH: delegated to external system of record (v3 pilot twin)" >/dev/null
baseline   # drain the transition + comment events

out_disp=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out_disp" "INTENT SKIP-DELEGATED ticket=$TX" \
    "PILOT-22 AC2: dispatch re-checks the marker — a delegated RfD ticket is SKIP-DELEGATED"
assert_not_contains "$out_disp" "INTENT SPAWN ticket=$TX" \
    "PILOT-22 AC2: no seat spawns for a delegated ticket at the RfD implementer entry"
cleanup_env
