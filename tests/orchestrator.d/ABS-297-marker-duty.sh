# =============================================================================
# ABS-297 — marker duty validation in handoff_followthrough
# -----------------------------------------------------------------------------
# Per-story include (ABS-215 pattern): `source`d by tests/test-orchestrator.sh
# into the live harness — no shebang, no `set -e`, no re-sourcing.
# Shares: assert_contains / assert_not_contains / assert_eq, PASS/FAIL/TOTAL,
# REPO_ROOT, ORCH (orchestrator.sh path), TRACKER (mock-tracker.sh path).
#
# The two new marker-duty checks added to handoff_followthrough() (ABS-297):
#
#   AC1: a po-agent handoff claiming a JOIN release on a child with no
#        JOIN-EXEMPT (triage) marker → REFUSED: INTENT MARKER-MISSING,
#        MARKER-MISSING runlog line, gate-results comment posted, no transition.
#   AC2: a bsa handoff claiming the follow-up pile is empty while a child still
#        has kind: follow-up without a kind: bsa-decision reply → REFUSED likewise.
#   AC3: happy path — JOIN-exempt claimed AND marker present → accepted, the
#        declared transition applies (no false refusal).
#   AC4: the refusal comment names the exact missing marker and the ticket it
#        must go on (grepped from the comment body).
#
# Test method: calls handoff_followthrough() directly in an isolated subshell
# that sources orchestrator.sh and uses the real mock-tracker backed by a temp
# tickets dir. Commit verification is disabled (ORCH_VERIFY_COMMITS=0) so only
# the marker gate is under test.
# =============================================================================

echo -e "\n${CYAN}=== ABS-297 marker duty validation in handoff_followthrough ===${NC}"

# Shared temp dir for this story's tests
_abs297_dir="$(mktemp -d /tmp/abs297-XXXXXX)"
_abs297_tdir="$_abs297_dir/tickets"
_abs297_sdir="$_abs297_dir/state"
_abs297_hf="$_abs297_dir/handoff.txt"
mkdir -p "$_abs297_tdir" "$_abs297_sdir"

# _abs297_tracker <args...> — wrapper that calls the mock tracker with the
# test's isolated ticket dir so test artifacts don't leak into the repo's
# work/tickets/ directory.
_abs297_tracker() { MOCK_TRACKER_TICKETS_DIR="$_abs297_tdir" bash "$TRACKER" "$@"; }

# _abs297_run <ticket> <to> <role> <handoff-text>
# Calls handoff_followthrough() in an isolated subshell:
#   - Sources orchestrator.sh (main is source-guarded; only functions load)
#   - Points TRACKER_CMD at the real mock-tracker backed by $_abs297_tdir
#   - ORCH_VERIFY_COMMITS=0  (commit gate not under test here)
#   - ORCH_VERIFY_MARKERS=1  (the gate under test)
#   - ORCH_HANDOFF_TRANSITION=1 (enables runner-side transitions for AC3)
# Returns stdout — the INTENT lines the function emits.
_abs297_run() {
    local tkt="$1" to="$2" role="$3"
    printf '%s' "$4" > "$_abs297_hf"
    bash -c '
        source "$1" >/dev/null 2>&1
        export TRACKER_CMD="$2"
        export MOCK_TRACKER_TICKETS_DIR="$3"
        export ORCH_STATE_DIR="$4"
        export ORCH_RUN_LOG="$4/run.log"
        MODE=live
        ORCH_VERIFY_COMMITS=0
        ORCH_VERIFY_MARKERS=1
        ORCH_HANDOFF_TRANSITION=1
        HANDOFF="$(cat "$5")"
        handoff_followthrough "$6" "$7" "$8" "$HANDOFF"
    ' _ "$ORCH" "$TRACKER" "$_abs297_tdir" "$_abs297_sdir" \
      "$_abs297_hf" "$tkt" "$to" "$role" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC1/AC4: JOIN-exempt claim without marker -> REFUSED${NC}"
# ---------------------------------------------------------------------------
# Set up: parent ticket + child ticket WITHOUT the JOIN-EXEMPT (triage) marker
_abs297_parent=$(_abs297_tracker create --type ticket \
    --title "ABS-297 po-agent parent" 2>/dev/null)
_abs297_child=$(_abs297_tracker create --type ticket \
    --title "ABS-297 child no-marker" --parent "$_abs297_parent" 2>/dev/null)
# Transition parent to the spawn status (Ready for Development)
_abs297_tracker transition "$_abs297_parent" "Ready for Development" \
    --actor orchestrator --reason "ABS-297 test setup" >/dev/null 2>/dev/null
# Child has NO kind: decision comment containing JOIN-EXEMPT (triage) — that is
# exactly the failure case this test pins.

# Handoff: claims the child is JOIN-EXEMPT (triage) on the same line as the ID
_abs297_h1="## Handoff

- role: po-agent
- ticket: $_abs297_parent
- summary: I have declared child $_abs297_child as JOIN-EXEMPT (triage) since it is an optional external dependency. The epic may close without it.
- to: In Progress"

_abs297_out1="$(_abs297_run "$_abs297_parent" "Ready for Development" "po-agent" "$_abs297_h1")"

assert_contains "$_abs297_out1" "INTENT MARKER-MISSING ticket=$_abs297_parent" \
    "ABS-297 AC1: JOIN-exempt claim without marker emits INTENT MARKER-MISSING"

_abs297_dump1="$(_abs297_tracker get "$_abs297_parent" 2>/dev/null)"
assert_contains "$_abs297_dump1" "MARKER-MISSING" \
    "ABS-297 AC1: JOIN-exempt claim without marker — MARKER-MISSING gate-results comment posted"
# AC4: the comment names the ticket the marker must go on
assert_contains "$_abs297_dump1" "$_abs297_child" \
    "ABS-297 AC4: refusal comment names the ticket the marker must go on"

# Transition must NOT have been applied — ticket stays in its spawn status
_abs297_st1="$(printf '%s\n' "$_abs297_dump1" | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_abs297_st1" "Ready for Development" \
    "ABS-297 AC1: JOIN-exempt claim without marker — no transition applied (handoff refused)"

# MARKER-MISSING runlog line (intent writes INTENT-MARKER-MISSING to $ORCH_RUN_LOG)
assert_contains "$(cat "$_abs297_sdir/run.log" 2>/dev/null || true)" "INTENT-MARKER-MISSING" \
    "ABS-297 AC1: MARKER-MISSING runlog line emitted"

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC2/AC4: bsa pile-empty claim with pending follow-ups -> REFUSED${NC}"
# ---------------------------------------------------------------------------
# Set up: ticket with an unanswered kind: follow-up comment (no bsa-decision reply)
_abs297_epic=$(_abs297_tracker create --type ticket \
    --title "ABS-297 ticket with pending follow-up" 2>/dev/null)
_abs297_tracker transition "$_abs297_epic" "Ready for Development" \
    --actor orchestrator --reason "ABS-297 test setup" >/dev/null 2>/dev/null
_abs297_tracker transition "$_abs297_epic" "In Progress" \
    --actor bsa --reason "ABS-297 test setup" >/dev/null 2>/dev/null
# Post a kind: follow-up comment — the pending unanswered follow-up
_abs297_tracker comment "$_abs297_epic" --kind follow-up --actor qas \
    --body "There is an unresolved scope question that needs a bsa decision." \
    >/dev/null 2>/dev/null
# No kind: bsa-decision reply — followup_pending_count returns 1

_abs297_h2="## Handoff

- role: bsa
- ticket: $_abs297_epic
- summary: I have reviewed all follow-up comments. The follow-up pile is empty and all questions have been answered.
- to: In Progress"

_abs297_out2="$(_abs297_run "$_abs297_epic" "In Progress" "bsa" "$_abs297_h2")"

assert_contains "$_abs297_out2" "INTENT MARKER-MISSING ticket=$_abs297_epic" \
    "ABS-297 AC2: bsa pile-empty claim with pending follow-ups emits MARKER-MISSING"

_abs297_dump2="$(_abs297_tracker get "$_abs297_epic" 2>/dev/null)"
assert_contains "$_abs297_dump2" "MARKER-MISSING" \
    "ABS-297 AC2: bsa pile-empty claim — MARKER-MISSING gate-results comment posted"
# AC4: the comment names the required marker (kind: bsa-decision)
assert_contains "$_abs297_dump2" "kind: bsa-decision" \
    "ABS-297 AC4: bsa refusal comment names the required marker (kind: bsa-decision)"

_abs297_st2="$(printf '%s\n' "$_abs297_dump2" | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_abs297_st2" "In Progress" \
    "ABS-297 AC2: bsa pile-empty claim with pending follow-ups — no transition applied"

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC3: happy path — JOIN-exempt claim WITH marker present -> accepted${NC}"
# ---------------------------------------------------------------------------
# Set up: parent ticket + child ticket WITH the JOIN-EXEMPT (triage) marker
_abs297_parent3=$(_abs297_tracker create --type ticket \
    --title "ABS-297 happy-path parent" 2>/dev/null)
_abs297_child3=$(_abs297_tracker create --type ticket \
    --title "ABS-297 happy-path child with marker" \
    --parent "$_abs297_parent3" 2>/dev/null)
_abs297_tracker transition "$_abs297_parent3" "Ready for Development" \
    --actor orchestrator --reason "ABS-297 test setup" >/dev/null 2>/dev/null
# Post the required marker on the child: kind: decision comment containing
# the exact join_exempt_marker() text ("JOIN-EXEMPT (triage)")
_abs297_tracker comment "$_abs297_child3" --kind decision --actor po-agent \
    --body "Optional dependency — deliberately parked. JOIN-EXEMPT (triage): the epic may complete without this child." \
    >/dev/null 2>/dev/null

# Handoff claims the child is JOIN-EXEMPT (triage) — and the marker IS there
_abs297_h3="## Handoff

- role: po-agent
- ticket: $_abs297_parent3
- summary: I have declared child $_abs297_child3 as JOIN-EXEMPT (triage) per triage decision on the child ticket.
- to: In Progress"

_abs297_out3="$(_abs297_run "$_abs297_parent3" "Ready for Development" "po-agent" "$_abs297_h3")"

assert_not_contains "$_abs297_out3" "INTENT MARKER-MISSING" \
    "ABS-297 AC3 happy path: marker present — no MARKER-MISSING (no false refusal)"

# Declared transition must have been applied (Ready for Development -> In Progress)
_abs297_st3="$(_abs297_tracker get "$_abs297_parent3" 2>/dev/null \
    | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_abs297_st3" "In Progress" \
    "ABS-297 AC3 happy path: marker present — declared transition applied (In Progress)"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
rm -rf "$_abs297_dir"
unset -f _abs297_tracker _abs297_run
unset _abs297_dir _abs297_tdir _abs297_sdir _abs297_hf \
      _abs297_parent _abs297_child _abs297_epic \
      _abs297_parent3 _abs297_child3 \
      _abs297_h1 _abs297_h2 _abs297_h3 \
      _abs297_out1 _abs297_out2 _abs297_out3 \
      _abs297_dump1 _abs297_dump2 \
      _abs297_st1 _abs297_st2 _abs297_st3
