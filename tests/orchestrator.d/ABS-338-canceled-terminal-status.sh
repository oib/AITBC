# =============================================================================
# ABS-338 — `Canceled` is a canonical TERMINAL status (Epic ABS-326, Option A)
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md). In scope: assert_contains / assert_eq /
# assert_not_contains, PASS/FAIL/TOTAL, new_env / cleanup_env / baseline /
# tracker / orch, ORCH / TRACKER / MOCK_TRACKER_STATUSES / ORCH_STATE_DIR.
#
# MODEL GAP PINNED (ABS-338): Jira carries a `Canceled` status (e.g. ABS-127)
# that the v3 canonical status machine lacked. Two consumers broke on it: the
# shadow mirror skipped it (`unbekannter Jira-Status 'Canceled' — skip`,
# divergence-status finding) and the runner treated a canceled ticket as a
# stalled ACTIVE one — STUCK-DETECT fired (sweeps=3) and the ABS-132 respawn
# limiter escalated it, re-deriving forever. Operator decision-of-record
# 2026-07-17 = Option A: `Canceled` is a terminal rest (terminal: true,
# next: []) — NO map->Done+resolution, NO reverse edge (reopen = new ticket).
# This test locks: (1) the model recognizes Canceled as terminal/rest/known;
# (2) the ABS-132 respawn limiter EXEMPTS it (data-driven status_is_terminal);
# (3) STUCK-DETECT does NOT flag it, while a real non-terminal stall still does
# (no masking); (4) the YAML shape (terminal, no forward edge) and the
# profiles/backend mirror parity (ABS-338 must stay in lockstep).
# =============================================================================

echo -e "\n${CYAN}=== ABS-338 Canceled terminal-status recognition ===${NC}\n"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-338 Part 1 — the canonical model recognizes Canceled as terminal/rest/known (AC1+AC2)${NC}"
# ---------------------------------------------------------------------------
new_env
_abs338_p1=$(
  source "$ORCH" >/dev/null 2>&1
  status_is_terminal    "Canceled" && t=1 || t=0
  is_legit_rest_status  "Canceled" && r=1 || r=0
  is_known_status       "Canceled" && k=1 || k=0
  # negative control: an active status must NOT read as terminal
  status_is_terminal    "In Progress" && a=1 || a=0
  printf 'term=%s rest=%s known=%s active_term=%s\n' "$t" "$r" "$k" "$a"
)
assert_contains "$_abs338_p1" "term=1" \
    "ABS-338 AC2: status_is_terminal(Canceled)=true — data-driven terminal flag read from statuses.yaml"
assert_contains "$_abs338_p1" "rest=1" \
    "ABS-338 AC3: is_legit_rest_status(Canceled)=true — STUCK-DETECT treats a canceled ticket as a legit rest"
assert_contains "$_abs338_p1" "known=1" \
    "ABS-338 AC1: is_known_status(Canceled)=true — the runner enumerates Canceled as a canonical status"
assert_contains "$_abs338_p1" "active_term=0" \
    "ABS-338 no-masking: an active status (In Progress) is still NOT terminal"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-338 Part 2 — the ABS-132 respawn limiter EXEMPTS Canceled (AC3)${NC}"
# ---------------------------------------------------------------------------
# Same mixed-role NOMOVE pump ABS-339 pinned for Epic Done — proves the
# data-driven status_is_terminal exemption now covers the new terminal too.
new_env
C=$(tracker create --type ticket --title "ABS-338 canceled respawn-exemption")
baseline

_abs338_p2=$(
  export ORCH_RESPAWN_LIMIT=2 ORCH_ESCALATION_LOOPBREAKER=1 ORCH_ESCALATION_BUDGET=2 ORCH_ESCALATION_WORK_CREDIT=0
  source "$ORCH" >/dev/null 2>&1
  record_nomove "$C" "Canceled" "self-improvement" "terminal rest" >/dev/null 2>&1
  record_nomove "$C" "Canceled" "bsa"              "terminal rest" >/dev/null 2>&1
  dump="$(tracker get "$C" 2>/dev/null)"
  printf 'count=%s escal=%s\n' "$(nomove_count "$dump" "Canceled")" "$(escalation_count "$C")"
)
_abs338_p2_count=$(printf '%s\n' "$_abs338_p2" | grep -o 'count=[0-9]*' | cut -d= -f2)
_abs338_p2_escal=$(printf '%s\n' "$_abs338_p2" | grep -o 'escal=[0-9]*' | cut -d= -f2)
_abs338_p2_runlog="$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true)"
_abs338_p2_status=$(tracker get "$C" 2>/dev/null | awk -F': ' '/^status:/{print $2}')

assert_eq "$_abs338_p2_count" "0" \
    "ABS-338 AC3: nomove_count stays 0 on Canceled — terminal NOMOVE not counted"
assert_eq "$_abs338_p2_escal" "0" \
    "ABS-338 AC3: escalation-budget counter stays 0 on Canceled"
assert_contains "$_abs338_p2_runlog" "INTENT-HANDOFF-NOMOVE-EXEMPT" \
    "ABS-338 AC3: terminal NOMOVE recorded as an auditable HANDOFF-NOMOVE-EXEMPT line"
assert_not_contains "$_abs338_p2_runlog" "INTENT-RESPAWN-LIMIT" \
    "ABS-338 AC3: a canceled ticket produces NO RESPAWN-LIMIT escalation"
assert_not_contains "$_abs338_p2_status" "Needs PO Decision" \
    "ABS-338 AC3: a canceled ticket is NOT escalated to Needs PO Decision"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-338 Part 3 — STUCK-DETECT skips Canceled but STILL fires on a real stall (AC3, no masking)${NC}"
# ---------------------------------------------------------------------------
new_env
Cx=$(tracker create --type ticket --title "ABS-338 canceled not-stuck")
St=$(tracker create --type ticket --title "ABS-338 genuine stall")
baseline

# runlog is TAB-separated (STUCK-DETECT<TAB>ticket), so compute the presence
# flags with grep inside the subshell rather than substring-matching a space.
_abs338_p3=$(
  export ORCH_STUCK_SWEEPS=1
  source "$ORCH" >/dev/null 2>&1
  check_stuck "$Cx" "Canceled"    >/dev/null 2>&1   # legit terminal rest -> no flag
  check_stuck "$St" "In Progress" >/dev/null 2>&1   # unowned non-terminal rest -> flag
  rl="${ORCH_RUN_LOG:-$ORCH_STATE_DIR/run.log}"
  c=0; grep -q "STUCK-DETECT.*$Cx" "$rl" 2>/dev/null && c=1
  s=0; grep -q "STUCK-DETECT.*$St" "$rl" 2>/dev/null && s=1
  printf 'cancel_stuck=%s stall_stuck=%s\n' "$c" "$s"
)
assert_contains "$_abs338_p3" "cancel_stuck=0" \
    "ABS-338 AC3: STUCK-DETECT does NOT flag a canceled ticket (ends the ABS-127 Dauerrauschen)"
assert_contains "$_abs338_p3" "stall_stuck=1" \
    "ABS-338 no-masking: STUCK-DETECT still fires on a genuine non-terminal stall"
cleanup_env

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-338 Part 4 — YAML shape: Canceled is terminal with no forward edge, and the mirror copy matches (AC2)${NC}"
# ---------------------------------------------------------------------------
_abs338_prof="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
_abs338_back="$REPO_ROOT/backend/packages/core/src/workflows/statuses.yaml"

# Canceled entry carries `terminal: true` and an empty `next: []` (no reverse edge).
_abs338_block="$(awk '/^  - name: Canceled$/{f=1} f{print} f&&/next:/{exit}' "$_abs338_prof")"
assert_contains "$_abs338_block" "terminal: true" \
    "ABS-338 AC2: Canceled carries terminal: true in the canonical statuses.yaml"
assert_contains "$_abs338_block" "next: []" \
    "ABS-338 AC2: Canceled has next: [] — no reverse edge (reopen = a new ticket)"

# Mirror parity (ABS-338 edits BOTH copies in lockstep; the pre-commit
# mirror-drift guard enforces this — assert it here too).
_abs338_parity="drifted"; diff -q "$_abs338_prof" "$_abs338_back" >/dev/null 2>&1 && _abs338_parity="identical"
assert_eq "$_abs338_parity" "identical" \
    "ABS-338 AC2: profiles/ and backend/ statuses.yaml stay byte-identical (mirror parity)"
