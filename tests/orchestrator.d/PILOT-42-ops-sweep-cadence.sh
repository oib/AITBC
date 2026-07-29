# =============================================================================
# PILOT-42 — cadence-triggered TDM ops-sweep (time-driven, PHASE 0 / shadow).
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md).
#
# WHAT PILOT-42 ADDS
#   ops_sweep_dispatch() runs once at the end of every reconcile sweep. When
#   ORCH_OPS_SWEEP_INTERVAL seconds have elapsed since the last sweep it dispatches
#   ONE TDM seat (reason 'ops-sweep') to DIAGNOSE the recurring stuck-classes.
#   PHASE 0 executes nothing — the seat only writes a report.
#
# WHAT THESE TESTS PIN
#   - AC1: knob 0 => byte-identical (no dispatch, no cadence marker written).
#   - cadence: the first sweep of a run SEEDS the marker and waits a full interval;
#     a dispatch fires only once the interval has elapsed; not-yet-due stays quiet.
#   - health gate: an outage pause suppresses the sweep (never fight recovery).
# =============================================================================

echo -e "\n${CYAN}=== PILOT-42 ops-sweep cadence dispatch (Phase 0 / shadow) ===${NC}\n"

# --- AC1: knob 0 => OFF, byte-identical (no dispatch, no marker) --------------
new_env
out0=$(ORCH_OPS_SWEEP_INTERVAL=0 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out0" "INTENT OPS-SWEEP" \
    "PILOT-42 AC1: knob 0 => no ops-sweep dispatch"
assert_eq "$([ -f "$ORCH_STATE_DIR/ops-sweep-last" ] && echo yes || echo no)" "no" \
    "PILOT-42 AC1: knob 0 => no cadence marker written (byte-identical)"
cleanup_env

# --- cadence: seed on first sweep, dispatch once the interval elapses ---------
new_env
# First reconcile of the run seeds the cadence marker and does NOT dispatch.
out1=$(ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=1000000 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out1" "INTENT OPS-SWEEP" \
    "PILOT-42: first sweep seeds cadence, no immediate dispatch"
assert_eq "$([ -f "$ORCH_STATE_DIR/ops-sweep-last" ] && echo yes || echo no)" "yes" \
    "PILOT-42: first sweep seeds the cadence marker"
# Not yet due (elapsed < interval).
out2=$(ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=1000050 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out2" "INTENT OPS-SWEEP" \
    "PILOT-42: not due (elapsed < interval) => no dispatch"
# Interval elapsed => dispatch the TDM ops-sweep seat.
out3=$(ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=1000200 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out3" "INTENT OPS-SWEEP ticket=ops-sweep role=tdm" \
    "PILOT-42: cadence elapsed => OPS-SWEEP dispatched (reason ops-sweep, TDM seat)"
cleanup_env

# --- health gate: outage pause suppresses the sweep --------------------------
new_env
# Seed the cadence marker at an early clock so the later sweep is due.
ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=2000000 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once >/dev/null 2>&1
touch "$ORCH_STATE_DIR/outage"
out4=$(ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=2000500 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out4" "INTENT OPS-SWEEP" \
    "PILOT-42: outage pause suppresses the ops-sweep (never fight recovery)"
cleanup_env

# --- PILOT-73: a LIVE sweep persists its report durably + leaves a runlog line -
# End-to-end through dispatch -> run_spawn_cmd -> ops_sweep_persist_report with the
# real stub spawn (sync, so the report lands before --once returns). The Phase-0
# report is the sweep's ONLY deliverable; it must outlive the run (AC1/AC2/AC4).
new_env
ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=3000000 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once >/dev/null 2>&1
ORCH_ASYNC_SPAWNS=0 ORCH_OPS_SWEEP_INTERVAL=100 ORCH_NOW=3000200 ORCH_RECONCILE_ON_STARTUP=1 \
    orch --live --once >/dev/null 2>&1
report="$(ls "$ORCH_STATE_DIR/ops-sweep-reports"/ops-sweep.*.txt 2>/dev/null | head -1)"
assert_eq "$([ -n "$report" ] && [ -s "$report" ] && echo yes || echo no)" "yes" \
    "PILOT-73: a live sweep writes a durable report file (not under packets/)"
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "OPS-SWEEP-REPORT" \
    "PILOT-73: a live sweep leaves a greppable OPS-SWEEP-REPORT runlog line (AC2)"
cleanup_env
