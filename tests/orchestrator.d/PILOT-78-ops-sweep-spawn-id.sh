# =============================================================================
# PILOT-78 — ops-sweep spawn_id uniqueness (ticket-less recurring seat).
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md). Shares assert_* / PASS/FAIL/TOTAL / ORCH / the
# new_env|cleanup_env|orch fixtures.
#
# THE BUG (found in Pilot 7)
#   seat_spawn_id is run_id:ticket:role:attempt. For a TICKET seat the ticket id
#   varies, so the id is unique. The hourly ops-sweep has NO ticket id — it always
#   uses run_id:ops-sweep:tdm:1 — so every dispatch of a run collided on ONE id,
#   and the backend `seat_spawn` upsert (ON CONFLICT (id)) overwrote the earlier
#   dispatch's row. Any open/close pairing then paired open(new) with close(old).
#
# THE FIX
#   ops_sweep_dispatch feeds its per-run monotonic dispatch count (OPS_SWEEP_COUNT)
#   into seat_spawn_id as SPAWN_SEQ, appended as "#N". The attempt counter stays its
#   OWN field (run.log attempt=, JSON "attempt"); the seq never replaces it (AC1).
#
# WHAT THESE TESTS PIN
#   - AC1/AC2: two ops-sweep dispatches of one run yield DISTINCT spawn_ids, while
#     attempt stays 1 in both — and WITHOUT the seq they would collide (the bug).
#   - AC1: ticket seats (SPAWN_SEQ unset) are byte-identical run_id:ticket:role:att.
#   - AC2 wiring: ops_sweep_dispatch actually sets SPAWN_SEQ from OPS_SWEEP_COUNT.
#   - AC3: OVERLAP is deliberately SUPPRESSED — a dispatch while a prior sweep still
#     holds the single-flight lock SKIP-LOCKEDs (never two live sweeps at once), so
#     the two-live-open ambiguity cannot arise in the first place.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-78 ops-sweep spawn_id uniqueness ===${NC}\n"

# --- AC1/AC2: seat_spawn_id is unique per dispatch, attempt preserved ---------
# Probe the pure function in a child bash that `source`s orchestrator.sh (the
# main-loop guard keeps `main` from running when sourced), like PILOT-26.
_pilot78_probe() {
    bash -c '
        source "'"$ORCH"'" >/dev/null 2>&1 || { echo "SOURCE-FAIL"; exit 0; }
        export ORCH_RUN_ID="run7"
        SPAWN_ATTEMPT=1
        # Two ops-sweep dispatches of the SAME run: only SPAWN_SEQ differs (the
        # dispatch count), everything else is constant.
        collide="$(seat_spawn_id ops-sweep tdm)"                 # no seq -> old id
        s1="$(SPAWN_SEQ=1 seat_spawn_id ops-sweep tdm)"
        s2="$(SPAWN_SEQ=2 seat_spawn_id ops-sweep tdm)"
        # A ticket seat leaves SPAWN_SEQ unset -> must be byte-identical to before.
        tkt="$(seat_spawn_id PILOT-9 be-developer)"
        echo "COLLIDE=$collide"
        echo "S1=$s1"
        echo "S2=$s2"
        echo "TKT=$tkt"
    '
}
_p78="$(_pilot78_probe)"

# Without a seq the two dispatches share ONE id — this is the bug being fixed.
assert_contains "$_p78" "COLLIDE=run7:ops-sweep:tdm:1" \
    "PILOT-78: without SPAWN_SEQ the ops-sweep id is run_id:ticket:role:attempt (the colliding shape)"
# With per-dispatch seq the ids are DISTINCT (AC2) ...
assert_contains "$_p78" "S1=run7:ops-sweep:tdm:1#1" \
    "PILOT-78 AC2: dispatch 1 -> run_id:ops-sweep:tdm:1#1"
assert_contains "$_p78" "S2=run7:ops-sweep:tdm:1#2" \
    "PILOT-78 AC2: dispatch 2 -> run_id:ops-sweep:tdm:1#2 (distinct from dispatch 1)"
# ... and the attempt counter is preserved as its own field in BOTH (AC1).
assert_contains "$_p78" "S1=run7:ops-sweep:tdm:1#1" \
    "PILOT-78 AC1: attempt (=1) survives as its own field alongside the seq"
# Ticket seats are untouched (SPAWN_SEQ unset) — PILOT-26 regression guard.
assert_contains "$_p78" "TKT=run7:PILOT-9:be-developer:1" \
    "PILOT-78 AC1: a ticket seat (no SPAWN_SEQ) is byte-identical run_id:ticket:role:attempt"

# --- AC2 wiring: the real dispatch feeds a per-run count into SPAWN_SEQ --------
# OPS_SWEEP_COUNT increments once per dispatch (byte-checkable, PILOT-26 idiom), so
# two dispatches of a run pass 1 then 2 and get distinct ids per the probe above.
_p78_src="$(cat "$ORCH")"
assert_contains "$_p78_src" 'local SPAWN_SEQ="$OPS_SWEEP_COUNT"' \
    "PILOT-78 AC2: ops_sweep_dispatch feeds the per-run dispatch count into SPAWN_SEQ"

# --- AC3: overlap is deliberately suppressed by the single-flight lock ---------
# Seed the cadence marker on the first sweep, then hold the ops-sweep lock (as a
# still-running prior sweep would) and drive a DUE sweep: it must SKIP-LOCKED and
# never dispatch — so two live ops-sweeps (the two-open ambiguity) cannot occur.
new_env
ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=3000000 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once >/dev/null 2>&1
mkdir -p "$ORCH_STATE_DIR/locks/ops-sweep"   # a prior sweep still holds the lock
out78=$(ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=3000200 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out78" "INTENT SKIP-LOCKED ticket=ops-sweep role=tdm" \
    "PILOT-78 AC3: a dispatch while a prior sweep holds the lock is SKIP-LOCKED (overlap suppressed)"
assert_not_contains "$out78" "INTENT OPS-SWEEP ticket=ops-sweep" \
    "PILOT-78 AC3: the suppressed dispatch does NOT open a second concurrent ops-sweep"
cleanup_env
