# =============================================================================
# ABS-301 — escalation budget must not park terminal statuses or mid-work
#           legitimate-progress states
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md). In scope: assert_contains / assert_eq /
# assert_not_contains, PASS/FAIL/TOTAL, REPO_ROOT / ORCH / TRACKER / STUB.
#
# THREE ROOT-CAUSE DEFECTS PINNED HERE (ABS-301):
#   1. Terminal-status exemption: escalation_note_stall() counted rounds on
#      Epic Done (next: []) — the self-improvement retro seat correctly does NOT
#      transition, so the budget falsely parked a finished epic (ABS-217).
#   2. Declarative source of truth: terminal: true added to statuses.yaml;
#      the sweep reads the flag from the file, never a hardcoded name list.
#   3. One-way ratchet fix: escalation_note_progress() was never called on
#      runner-mechanical epic-pipeline transitions (join_check_epic, Stories In
#      Flight -> Epic Integration), so the high-water mark never advanced and
#      every long-running epic drifted toward an auto-park (ABS-245: state
#      read 3\t0 at Epic Integration).
# =============================================================================

echo -e "\n${CYAN}=== ABS-301 escalation-budget terminal exemption + ratchet fix ===${NC}\n"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-301 Part 1 — terminal status: no stall counted, never parked${NC}"
# ---------------------------------------------------------------------------
# Directly exercise escalation_note_stall on "Epic Done" (terminal: true).
# Must return 1 (no-park) even when called ORCH_ESCALATION_BUDGET times.
_abs301_terminal_stall() {
    bash -c '
        source "$1" >/dev/null 2>&1
        export ORCH_ESCALATION_LOOPBREAKER=1
        export ORCH_ESCALATION_BUDGET=2
        export ORCH_STATE_DIR="$(mktemp -d)"
        export MOCK_TRACKER_STATUSES="$2"
        result=0
        # Call stall twice (= budget); each must return 1 (no park).
        escalation_note_stall "T-TERM" "Epic Done" "self-improvement" || result=$(( result + 1 ))
        escalation_note_stall "T-TERM" "Epic Done" "self-improvement" || result=$(( result + 1 ))
        # Count must stay 0 — terminal status writes nothing to the state file.
        count=$(escalation_count "T-TERM")
        printf "no-park=%s count=%s\n" "$result" "$count"
        rm -rf "$ORCH_STATE_DIR"
    ' _abs301 "$ORCH" "$MOCK_TRACKER_STATUSES"
}
_abs301_out="$(_abs301_terminal_stall)"
assert_eq "$(printf '%s\n' "$_abs301_out" | grep -o 'no-park=[0-9]*' | cut -d= -f2)" "2" \
    "ABS-301 AC1: escalation_note_stall returns no-park (1) on terminal status for BOTH calls"
assert_eq "$(printf '%s\n' "$_abs301_out" | grep -o 'count=[0-9]*' | cut -d= -f2)" "0" \
    "ABS-301 AC1: stall counter stays 0 — terminal status is not counted"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-301 Part 2 — terminal flag read from statuses.yaml (not hardcoded)${NC}"
# ---------------------------------------------------------------------------
# Verify status_is_terminal reads the file: Epic Done → terminal, In Progress → not.
_abs301_terminal_check() {
    bash -c '
        source "$1" >/dev/null 2>&1
        export MOCK_TRACKER_STATUSES="$2"
        epic_done_terminal=0
        in_progress_terminal=0
        status_is_terminal "Epic Done"   && epic_done_terminal=1
        status_is_terminal "In Progress" && in_progress_terminal=1
        printf "epic_done=%s in_progress=%s\n" "$epic_done_terminal" "$in_progress_terminal"
    ' _abs301 "$ORCH" "$MOCK_TRACKER_STATUSES"
}
_abs301_tc="$(_abs301_terminal_check)"
assert_eq "$(printf '%s\n' "$_abs301_tc" | grep -o 'epic_done=[01]' | cut -d= -f2)" "1" \
    "ABS-301 AC4: status_is_terminal reads terminal:true from statuses.yaml — Epic Done is terminal"
assert_eq "$(printf '%s\n' "$_abs301_tc" | grep -o 'in_progress=[01]' | cut -d= -f2)" "0" \
    "ABS-301 AC4: status_is_terminal reads from file — In Progress is NOT terminal (not hardcoded)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-301 Part 3 — epic JOIN resets the escalation counter (ratchet fix)${NC}"
# ---------------------------------------------------------------------------
# Simulate the ABS-245 scenario: an epic with 3 stall rounds (count=3, hw=0)
# transitions to Epic Integration via the JOIN rule. After the fix,
# join_check_epic MUST call escalation_note_progress, advancing the high-water
# to 27 (Epic Integration chain_index) and resetting count to 0.
new_env
export ORCH_ESCALATION_LOOPBREAKER=1
export ORCH_ESCALATION_BUDGET=3

E=$(tracker create --type epic --title "ABS-301 ratchet-fix epic")
A=$(tracker create --type ticket --title "ABS-301 child" --parent "$E")
# Move epic to Stories In Flight (use the legal Backlog -> Stories In Flight edge,
# ABS-214). The JOIN rule only fires when the epic rests here.
tracker transition "$E" "Stories In Flight" --actor po-agent --reason "test" >/dev/null
# Move child to Done via the correct story pipeline path.
tracker transition "$A" "Ready for Development" --actor orchestrator --reason "test" >/dev/null
tracker transition "$A" "In Progress" --actor be-developer --reason "test" >/dev/null
tracker transition "$A" "In Review" --actor be-developer --reason "test" >/dev/null
tracker transition "$A" "In Test" --actor qas --reason "test" >/dev/null
tracker transition "$A" "Ready for Human Acceptance" --actor qas --reason "test" >/dev/null
tracker transition "$A" "Ready for Merge" --actor human --reason "test" >/dev/null
tracker transition "$A" "Done" --actor human --reason "test" >/dev/null
baseline

# Pre-load escalation state to simulate the ABS-245 3\t0 ratchet.
( source "$ORCH" >/dev/null 2>&1
  escalation_write "$E" 3 0 ) 2>/dev/null || true

# Confirm the pre-load.
_abs301_pre_count=$(bash -c '
    source "$1" >/dev/null 2>&1
    escalation_count "$2"
' _abs301 "$ORCH" "$E" 2>/dev/null)
assert_eq "$_abs301_pre_count" "3" \
    "ABS-301 AC2 setup: pre-loaded escalation count=3 (the ABS-245 3\\t0 ratchet)"

# Run ONE reconcile cycle in --live mode so the JOIN transition AND
# escalation_note_progress actually fire.
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)

# The JOIN should have fired (epic_children_rows sees all Done).
assert_contains "$out" "INTENT JOIN ticket=$E" \
    "ABS-301 AC2: JOIN fires (all children Done)"

# escalation_note_progress writes to run.log (not stdout); verify there.
_abs301_runlog="$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true)"
assert_contains "$_abs301_runlog" "ESCALATION-RESET" \
    "ABS-301 AC2: escalation_note_progress logged ESCALATION-RESET after JOIN (ratchet fix)"

# After the JOIN, the high-water must have advanced to >= 27 (Epic Integration
# chain_index), proving the reset fired. Count may have incremented once for the
# rte HANDOFF-NOMOVE at Epic Integration — that is correct (the counter now tracks
# fresh rounds from hw=27, not the stale pre-JOIN count of 3).
_abs301_post=$(bash -c '
    source "$1" >/dev/null 2>&1
    printf "count=%s hw=%s\n" "$(escalation_count "$2")" "$(escalation_highwater "$2")"
' _abs301 "$ORCH" "$E" 2>/dev/null)
_abs301_hw=$(printf '%s\n' "$_abs301_post" | grep -o 'hw=[0-9]*' | cut -d= -f2)
if [ "${_abs301_hw:-0}" -ge 27 ]; then
    assert_eq "sane" "sane" \
        "ABS-301 AC2: high-water mark >= 27 (Epic Integration chain_index) — counter tracked epic progress"
else
    assert_eq "${_abs301_hw:-0}" ">=27" \
        "ABS-301 AC2: high-water mark must reach Epic Integration (27)"
fi
# The epic must NOT be at Blocked — the stale 3-round count did NOT auto-park it.
_abs301_epic_status=$(tracker get "$E" 2>/dev/null | awk -F': ' '/^status:/{print $2}')
assert_not_contains "$_abs301_epic_status" "Blocked" \
    "ABS-301 AC2: epic NOT falsely parked to Blocked — the 3-round pre-JOIN stall count was reset"

cleanup_env
unset ORCH_ESCALATION_LOOPBREAKER ORCH_ESCALATION_BUDGET

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-301 Part 4 — real stalls still park (no masking of genuine stuck tickets)${NC}"
# ---------------------------------------------------------------------------
# A genuinely stalled ticket on a NON-terminal status with no forward progress
# must still be parked at ORCH_ESCALATION_BUDGET rounds.
new_env
export ORCH_ESCALATION_LOOPBREAKER=1
export ORCH_ESCALATION_BUDGET=2

T=$(tracker create --type ticket --title "ABS-301 genuine stall" --role be-developer)
tracker transition "$T" "Ready for Development" --actor orchestrator --reason "test" >/dev/null
baseline

# Simulate 2 stall rounds directly (budget=2, non-terminal status).
_abs301_stall_direct=$(bash -c '
    source "$1" >/dev/null 2>&1
    export ORCH_STATE_DIR="$ORCH_STATE_DIR"
    export ORCH_ESCALATION_LOOPBREAKER=1
    export ORCH_ESCALATION_BUDGET=2
    # First call: count=1, not yet at budget.
    escalation_note_stall "$2" "Ready for Development" "be-developer" && echo "PARKED-1" || echo "NOPE-1"
    # Second call: count=2, hits budget.
    escalation_note_stall "$2" "Ready for Development" "be-developer" && echo "PARKED-2" || echo "NOPE-2"
' _abs301 "$ORCH" "$T" 2>/dev/null)
assert_contains "$_abs301_stall_direct" "NOPE-1" \
    "ABS-301 AC3: first stall round does NOT park (below budget)"
assert_contains "$_abs301_stall_direct" "PARKED-2" \
    "ABS-301 AC3: genuine stall reaches budget and returns park=0 — real stalls still caught"

cleanup_env
unset ORCH_ESCALATION_LOOPBREAKER ORCH_ESCALATION_BUDGET
