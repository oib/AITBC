# =============================================================================
# ABS-451 — In Progress orphan self-heal: an UNOWNED "In Progress" ticket (no
#           seat lock, no in-flight spawn, no crash marker) is DOWNGRADED to a
#           spawnable status ("Ready for Development") after N sweeps, instead of
#           the ABS-116 NOTIFY-only dead-end.
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS (observed live: ABS-417 3× in 12h 2026-07-18/19; ABS-438)
# A TDM blocker-resume (or human release) that targets "In Progress" parks a
# ticket in a status no seat is re-derived for. The runner could only emit a
# repeating stuck NOTIFY (ABS-116) — each occurrence needed an operator nudge
# back to "Ready for Development". This story extends the ABS-116 detector so the
# runner SELF-HEALS the orphan: downgrade to "Ready for Development" so reconcile
# dispatches a fresh seat.
#
# WHAT ABS-451 ADDS
#   1. heal_inprogress_orphan() + a hook in check_stuck(): an unowned In Progress
#      ticket resting ORCH_INPROGRESS_HEAL_SWEEPS sweeps is transitioned to
#      "Ready for Development" (gate-results comment + INPROGRESS-HEAL intent).
#   2. ORCH_INPROGRESS_HEAL_SWEEPS knob (default 3; 0 = off = pure ABS-116 NOTIFY).
#   3. Deferral: a SPAWN-CRASH marker present → heal defers so ABS-295
#      CRASH-REPAIR routes to the precise recorded origin instead.
# =============================================================================

echo -e "\n${CYAN}=== ABS-451 In Progress orphan self-heal ===${NC}\n"

# Helper: park a ticket in an UNOWNED In Progress (no lock), consuming every
# intermediate event via baseline so no seat is spawned. Valid path:
# Backlog -> Ready for Development -> In Progress.
_abs451_park_inprogress() {
    local t="$1"
    tracker transition "$t" "Ready for Development" --actor po-agent --reason "setup" >/dev/null
    tracker transition "$t" "In Progress" --actor tdm \
        --reason "TDM blocker-resume targeted In Progress (the bug ABS-451 heals)" >/dev/null
    baseline   # dry-run + reconcile-off: drains events without spawning a seat
}

_abs451_status() { tracker get "$1" | sed -n 's/^status: //p' | head -1; }

# --- AC2: unowned In Progress heals to Ready for Development after 3 sweeps -------

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_INPROGRESS_HEAL_SWEEPS=3
export ORCH_CRASH_REPAIR_SECONDS=0   # isolate: crash-repair off, heal is the only mover

# PILOT-22: a legit crashed-seat orphan carries the opt-in label (propagated to
# every factory child); heal now honours the gate, so the fixture opts in.
T=$(tracker create --type ticket --title "ABS-451 orphaned In Progress" --label orchestrator-ready)
_abs451_park_inprogress "$T"

# Sweeps 1 and 2: below threshold → no heal, ticket stays In Progress.
out1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out1" "INTENT INPROGRESS-HEAL ticket=$T" \
    "ABS-451 AC2: no heal on sweep 1 (below threshold)"
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT INPROGRESS-HEAL ticket=$T" \
    "ABS-451 AC2: no heal on sweep 2 (below threshold)"
assert_eq "$(_abs451_status "$T")" "In Progress" \
    "ABS-451 AC2: ticket still In Progress before threshold"

# Sweep 3: threshold reached → heal fires (intent + transition + comment).
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out3" "INTENT INPROGRESS-HEAL ticket=$T" \
    "ABS-451 AC2: heal emits INPROGRESS-HEAL intent on the 3rd sweep"
assert_contains "$out3" "to=Ready for Development" \
    "ABS-451 AC2: heal target is the spawnable Ready for Development"
assert_eq "$(_abs451_status "$T")" "Ready for Development" \
    "ABS-451 AC2: unowned In Progress transitioned to Ready for Development"
assert_contains "$(tracker get "$T")" "INPROGRESS-HEAL=Ready for Development (orchestrator)" \
    "ABS-451 AC2: gate-results audit comment posted on the ticket"

# Idempotency: a further sweep does not re-heal (ticket is no longer In Progress;
# reconcile now dispatches it as a normal Ready-for-Development ticket).
out4=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out4" "INTENT INPROGRESS-HEAL ticket=$T" \
    "ABS-451 AC2: no double-heal after the ticket left In Progress"

cleanup_env

# --- AC2 (knob off): ORCH_INPROGRESS_HEAL_SWEEPS=0 reproduces ABS-116 NOTIFY-only -

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_INPROGRESS_HEAL_SWEEPS=0   # heal disabled
export ORCH_STUCK_SWEEPS=3             # ABS-116 NOTIFY still active
export ORCH_CRASH_REPAIR_SECONDS=0
export ORCH_NOTIFY_TICKET=""           # notify targets the ticket itself

TOFF=$(tracker create --type ticket --title "ABS-451 knob-off In Progress")
_abs451_park_inprogress "$TOFF"

out_off=""
for _ in 1 2 3; do
    out_off=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
done
assert_not_contains "$out_off" "INTENT INPROGRESS-HEAL ticket=$TOFF" \
    "ABS-451 knob-off: no heal when ORCH_INPROGRESS_HEAL_SWEEPS=0"
assert_contains "$out_off" "stuck detected: $TOFF" \
    "ABS-451 knob-off: ABS-116 STUCK-DETECT NOTIFY preserved"
assert_eq "$(_abs451_status "$TOFF")" "In Progress" \
    "ABS-451 knob-off: ticket stays In Progress (today's behaviour)"

cleanup_env

# --- AC3-guard: an OWNED In Progress (live lock) is never healed ------------------

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_INPROGRESS_HEAL_SWEEPS=3
export ORCH_CRASH_REPAIR_SECONDS=0

TOWN=$(tracker create --type ticket --title "ABS-451 owned In Progress")
_abs451_park_inprogress "$TOWN"
# Simulate a live seat holding the station (single-flight lock present).
mkdir -p "$ORCH_STATE_DIR/locks/$TOWN"

out_own=""
for _ in 1 2 3 4; do
    out_own=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
done
assert_not_contains "$out_own" "INTENT INPROGRESS-HEAL ticket=$TOWN" \
    "ABS-451 owned: a locked In Progress ticket is not a heal candidate"
assert_eq "$(_abs451_status "$TOWN")" "In Progress" \
    "ABS-451 owned: locked ticket stays In Progress (an active seat owns it)"

cleanup_env

# --- Deferral: a SPAWN-CRASH marker present → heal defers to ABS-295 CRASH-REPAIR -

new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_INPROGRESS_HEAL_SWEEPS=3
export ORCH_CRASH_REPAIR_SECONDS=0     # crash-repair off → neither mover fires; proves deferral
export ORCH_INSTANCE_ID="test-instance-abs451-defer"

TCR=$(tracker create --type ticket --title "ABS-451 crash-marked In Progress")
baseline
tracker transition "$TCR" "Ready for Development" --actor po-agent --reason "setup" >/dev/null
# Drive a spawn crash so record_spawn_crash posts a SPAWN-CRASH gate-results marker.
export STUB_FAIL=1
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1 || true
unset STUB_FAIL
# Seat claimed In Progress before dying.
tracker transition "$TCR" "In Progress" --actor be-developer --reason "seat claimed before dying" >/dev/null
baseline

out_cr=""
for _ in 1 2 3 4; do
    out_cr=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
done
assert_not_contains "$out_cr" "INTENT INPROGRESS-HEAL ticket=$TCR" \
    "ABS-451 deferral: heal defers when a SPAWN-CRASH marker is present (ABS-295 owns it)"
assert_eq "$(_abs451_status "$TCR")" "In Progress" \
    "ABS-451 deferral: with crash-repair off, the crash-marked ticket stays In Progress (not blunt-healed)"

cleanup_env
