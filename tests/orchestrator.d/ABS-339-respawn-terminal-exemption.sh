# =============================================================================
# ABS-339 — the ABS-132 respawn limiter must EXEMPT terminal statuses
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md). In scope: assert_contains / assert_eq /
# assert_not_contains, PASS/FAIL/TOTAL, new_env / cleanup_env / baseline /
# tracker / orch, ORCH / TRACKER / MOCK_TRACKER_STATUSES / ORCH_STATE_DIR.
#
# DEFECT PINNED (ABS-339): record_nomove() — the ABS-132 per-visit HANDOFF-NOMOVE
# counter — counted NOMOVEs on Epic Done (terminal: true, next: []). A Retro /
# Follow-up-watcher seat CORRECTLY does not transition a terminal ticket, so its
# no-move handoff is the intended terminal rest, not a stall. nomove_count keys
# on STATUS (not role), so a self-improvement retro NOMOVE + a bsa watcher NOMOVE
# summed to ORCH_RESPAWN_LIMIT at one Epic Done and escalated to Needs PO Decision
# — a status with NO legal edge back, so the sweep re-derived forever until a
# manual operator restore. Evidence: ABS-111/126/279 (2026-07-16), 181/190 (13.07).
# The ABS-199 escalation budget already had this exemption (ABS-301); this pins
# the same guard for the ABS-132 respawn counter, incl. the mixed-role pump.
# =============================================================================

echo -e "\n${CYAN}=== ABS-339 respawn-limiter terminal-state exemption ===${NC}\n"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-339 Part 1 — mixed-role NOMOVE on Epic Done: not counted, not escalated (AC1+AC3)${NC}"
# ---------------------------------------------------------------------------
# Two record_nomove rounds at Epic Done (terminal) with DIFFERENT roles — the
# mixed-role pump from operator evidence ABS-111 (retro + follow-up watcher).
# At ORCH_RESPAWN_LIMIT=2 the pre-fix limiter escalated on the 2nd round.
new_env
E=$(tracker create --type epic --title "ABS-339 terminal-exemption epic")
baseline

_abs339_p1=$(
  export ORCH_RESPAWN_LIMIT=2 ORCH_ESCALATION_LOOPBREAKER=1 ORCH_ESCALATION_BUDGET=2 ORCH_ESCALATION_WORK_CREDIT=0
  source "$ORCH" >/dev/null 2>&1
  record_nomove "$E" "Epic Done" "self-improvement" "retro handoff"   >/dev/null 2>&1
  record_nomove "$E" "Epic Done" "bsa"              "watcher handoff" >/dev/null 2>&1
  dump="$(tracker get "$E" 2>/dev/null)"
  printf 'count=%s escal=%s\n' "$(nomove_count "$dump" "Epic Done")" "$(escalation_count "$E")"
)
_abs339_count=$(printf '%s\n' "$_abs339_p1" | grep -o 'count=[0-9]*' | cut -d= -f2)
_abs339_escal=$(printf '%s\n' "$_abs339_p1" | grep -o 'escal=[0-9]*' | cut -d= -f2)
_abs339_runlog="$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true)"
_abs339_status=$(tracker get "$E" 2>/dev/null | awk -F': ' '/^status:/{print $2}')

assert_eq "$_abs339_count" "0" \
    "ABS-339 AC1: nomove_count stays 0 on Epic Done — no HANDOFF-NOMOVE marker posted (counter not incremented)"
assert_eq "$_abs339_escal" "0" \
    "ABS-339 AC1: escalation-budget counter stays 0 on terminal status"
assert_contains "$_abs339_runlog" "INTENT-HANDOFF-NOMOVE-EXEMPT" \
    "ABS-339 AC1: terminal NOMOVE recorded as an auditable HANDOFF-NOMOVE-EXEMPT run.log line"
assert_not_contains "$_abs339_runlog" "INTENT-RESPAWN-LIMIT" \
    "ABS-339 AC3: mixed-role (retro + watcher) terminal NOMOVEs produce NO RESPAWN-LIMIT escalation"
assert_not_contains "$_abs339_status" "Needs PO Decision" \
    "ABS-339 AC1: terminal ticket NOT escalated to Needs PO Decision"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-339 Part 2 — genuine NON-terminal no-move STILL escalates (no masking)${NC}"
# ---------------------------------------------------------------------------
# The exemption must not blunt the real ABS-132 guard: two no-move rounds on a
# NON-terminal status must still reach RESPAWN-LIMIT. Proves the fix only
# suppresses escalations on states that by definition cannot progress.
new_env
T=$(tracker create --type ticket --title "ABS-339 genuine no-move" --role be-developer)
tracker transition "$T" "Ready for Development" --actor orchestrator --reason "test" >/dev/null
baseline

(
  export ORCH_RESPAWN_LIMIT=2 ORCH_ESCALATION_LOOPBREAKER=0
  source "$ORCH" >/dev/null 2>&1
  record_nomove "$T" "Ready for Development" "be-developer" "no-move handoff" >/dev/null 2>&1
  record_nomove "$T" "Ready for Development" "be-developer" "no-move handoff" >/dev/null 2>&1
)
_abs339_p2_runlog="$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true)"
_abs339_p2_status=$(tracker get "$T" 2>/dev/null | awk -F': ' '/^status:/{print $2}')

assert_contains "$_abs339_p2_runlog" "INTENT-RESPAWN-LIMIT" \
    "ABS-339 no-masking: a genuine no-move on a NON-terminal status still escalates via RESPAWN-LIMIT"
assert_contains "$_abs339_p2_status" "Needs PO Decision" \
    "ABS-339 no-masking: the non-terminal escalation actually parks the ticket at Needs PO Decision"
cleanup_env
