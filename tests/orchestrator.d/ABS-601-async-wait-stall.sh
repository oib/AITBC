# =============================================================================
# ABS-601 — a seat that awaits an async completion notification a one-shot spawn
#           never delivers, and the orphaned background process it leaves behind
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/test-orchestrator.sh into the
# live harness — NO shebang, NO `set -e`, NO re-sourcing. In scope from the
# parent: assert_contains / assert_not_contains / assert_eq, PASS/FAIL/TOTAL,
# orch / tracker / new_env / cleanup_env / baseline, ORCH / STUB / ORCH_STATE_DIR.
#
# DEFECT PINNED (ABS-601): a spawned seat is a ONE-SHOT `claude -p` invocation —
# no later turn, no surviving event loop. A seat (an RTE at Epic-Integration,
# Pilot 8) backgrounded the ~15-min suite and ended its turn "waiting for the
# background task completion notification". That notification structurally cannot
# arrive, so the seat did NOTHING — yet exited subtype=success and was masked as a
# generic HANDOFF-NOMOVE that burned respawn budget (nomoves=2 → escalation).
# The fix: (AC3/AC4) a sensor NAMES the case ASYNC-WAIT-STALL and escalates
# directly; (AC5) the runner reaps the orphaned background process at spawn end.
# =============================================================================

echo -e "\n${CYAN}=== ABS-601 async-wait stall + orphan reap ===${NC}\n"

# Run a pure orchestrator helper in a subshell so the orchestrator's `set -e`
# stays contained. $ORCH is passed as $1 (NOT $0) so the run-vs-source guard
# does not misfire and run main().
_a601() { bash -c 'source "$1" >/dev/null 2>&1; shift; "$@"' _a601 "$ORCH" "$@"; }
_a601_runlog() { cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true; }

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-601 Part A — the async-wait detector (handoff_awaits_async_completion)${NC}"
# ---------------------------------------------------------------------------
# Both verbatim incident phrases must match; a REPORT of a finished background run
# and an ordinary handoff must NOT (no false-positive on the word "background").
if _a601 handoff_awaits_async_completion "Running. I'll wait for the background task completion notification before proceeding."; then r=0; else r=1; fi
assert_eq "$r" "0" "ABS-601 AC3: 'wait for the background task completion notification' is detected"
if _a601 handoff_awaits_async_completion "The background task bugy47b97 has been running. Let me keep checking until it completes."; then r=0; else r=1; fi
assert_eq "$r" "0" "ABS-601 AC3: 'keep checking until it completes' is detected"
if _a601 handoff_awaits_async_completion "Ran the staged suite; the background run finished and all stages are green. Releasing."; then r=1; else r=0; fi
assert_eq "$r" "0" "ABS-601 AC3: a REPORT of a finished background run is NOT flagged (no false positive)"
if _a601 handoff_awaits_async_completion "AC/DoD met. lint/type-check/integration green. Ready for review."; then r=1; else r=0; fi
assert_eq "$r" "0" "ABS-601 AC3: an ordinary completion handoff is NOT flagged"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-601 Part B — record_nomove routes an async-wait handoff to ASYNC-WAIT-STALL${NC}"
# ---------------------------------------------------------------------------
# A no-move round whose handoff carries the async-wait idiom must emit the NAMED
# marker (not a generic HANDOFF-NOMOVE) and escalate straight to Needs PO Decision.
new_env
T=$(tracker create --type ticket --title "ABS-601 async-wait unit" --role be-developer)
tracker transition "$T" "Ready for Development" --actor orchestrator --reason "test" >/dev/null
baseline
(
  source "$ORCH" >/dev/null 2>&1
  record_nomove "$T" "Ready for Development" "rte" "## Handoff
- role: rte
- next: Running. I'll wait for the background task completion notification before proceeding." >/dev/null 2>&1
)
_b_runlog="$(_a601_runlog)"
_b_status=$(tracker get "$T" 2>/dev/null | awk -F': ' '/^status:/{print $2}')
assert_contains "$_b_runlog" "INTENT-ASYNC-WAIT-STALL" \
    "ABS-601 AC4: an async-wait no-move is NAMED ASYNC-WAIT-STALL in run.log"
assert_not_contains "$_b_runlog" "INTENT-HANDOFF-NOMOVE" \
    "ABS-601 AC4: the generic HANDOFF-NOMOVE marker is NOT used for the async-wait case"
assert_contains "$_b_status" "Needs PO Decision" \
    "ABS-601 AC3: the async-wait stall escalates to Needs PO Decision (a defect, not a success)"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-601 Part B2 — a GENUINE no-move still records HANDOFF-NOMOVE (no masking)${NC}"
# ---------------------------------------------------------------------------
# The sensor must not swallow ordinary no-move rounds: a plain handoff with no
# async-wait idiom still flows through the existing HANDOFF-NOMOVE path.
new_env
T2=$(tracker create --type ticket --title "ABS-601 genuine no-move" --role be-developer)
tracker transition "$T2" "Ready for Development" --actor orchestrator --reason "test" >/dev/null
baseline
(
  source "$ORCH" >/dev/null 2>&1
  record_nomove "$T2" "Ready for Development" "be-developer" "## Handoff
- role: be-developer
- next: pattern unclear; resting for the sweep." >/dev/null 2>&1
)
_b2_runlog="$(_a601_runlog)"
assert_contains "$_b2_runlog" "INTENT-HANDOFF-NOMOVE" \
    "ABS-601 no-masking: a plain no-move handoff still records HANDOFF-NOMOVE"
assert_not_contains "$_b2_runlog" "INTENT-ASYNC-WAIT-STALL" \
    "ABS-601 no-masking: a plain no-move is NOT mis-flagged as an async-wait stall"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-601 Part C — end-to-end: async-wait spawn is named, not a silent success${NC}"
# ---------------------------------------------------------------------------
# Drive the real spawn seam: the stub emits the async-wait idiom in its handoff and
# moves nothing. The runner must NAME the failure and escalate — no false success.
new_env
export STUB_ASYNC_WAIT=1
T3=$(tracker create --type ticket --title "ABS-601 async-wait e2e" --role be-developer)
baseline
tracker transition "$T3" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT ASYNC-WAIT-STALL ticket=$T3" \
    "ABS-601 AC4 e2e: an async-wait handoff yields a NAMED ASYNC-WAIT-STALL through the real seam"
assert_not_contains "$out" "INTENT HANDOFF-NOMOVE ticket=$T3" \
    "ABS-601 AC4 e2e: the async-wait case does not fall through to a generic HANDOFF-NOMOVE"
_c_status=$(tracker get "$T3" 2>/dev/null | awk -F': ' '/^status:/{print $2}')
assert_contains "$_c_status" "Needs PO Decision" \
    "ABS-601 AC3 e2e: the async-wait stall parks the ticket at Needs PO Decision"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-601 Part D — end-to-end: the seat's orphaned background process is reaped${NC}"
# ---------------------------------------------------------------------------
# The stub backgrounds a long `sleep` (a detached child) and ends its turn. After
# the spawn reaps, that orphan must be dead (group-scoped reap), and run.log must
# record the SPAWN-REAP so the resource-leak cleanup is auditable.
new_env
export ORCH_WATCHDOG_POLL=1
_pidfile="$(mktemp -u "${TMPDIR:-/tmp}/abs601-orphan-XXXXXX")"
export STUB_ORPHAN_PIDFILE="$_pidfile"
T4=$(tracker create --type ticket --title "ABS-601 orphan reap e2e" --role be-developer)
baseline
tracker transition "$T4" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
_orphan_pid="$(cat "$_pidfile" 2>/dev/null || true)"
if [ -n "$_orphan_pid" ] && kill -0 "$_orphan_pid" 2>/dev/null; then _alive=1; else _alive=0; fi
assert_eq "$_alive" "0" \
    "ABS-601 AC5: the seat's backgrounded process is reaped at spawn end (pid=${_orphan_pid:-none})"
assert_contains "$(_a601_runlog)" "SPAWN-REAP" \
    "ABS-601 AC5: run.log records the SPAWN-REAP (the WHY a leftover process was killed)"
# Defensive cleanup in case the reap did not fire (keeps the suite host clean).
[ -n "$_orphan_pid" ] && kill -9 "$_orphan_pid" 2>/dev/null || true
rm -f "$_pidfile" 2>/dev/null || true
cleanup_env
