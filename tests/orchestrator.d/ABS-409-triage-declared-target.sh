# =============================================================================
# ABS-409 — PO first-triage: a declared target on a parentless Backlog ticket is
#           runner-applied (no NOMOVE respawn / Needs PO Decision detour)
# -----------------------------------------------------------------------------
# Per-story include (ABS-215 pattern): `source`d by tests/tooling/test-orchestrator.sh
# into the live harness — no shebang, no `set -e`, no re-sourcing. Runs in an
# ISOLATED child via _run_d_include (ABS-370). Shares: assert_contains /
# assert_not_contains / assert_eq, PASS/FAIL/TOTAL, REPO_ROOT, ORCH
# (orchestrator.sh path), TRACKER (mock-tracker.sh path), MOCK_TRACKER_STATUSES.
#
# ROOT CAUSE (2026-07-17, 4 cases ABS-376/387/389/379): the FIRST po-agent triage
# of a parentless Backlog ticket wrote a correct WSJF "dispatchable" verdict and
# named the target status IN PROSE, but neither transitioned nor declared a
# machine-readable target. Backlog has no self-loop, so the runner booked
# HANDOFF-NOMOVE, respawned, booked a second NOMOVE, hit ORCH_RESPAWN_LIMIT and
# dumped the ticket to Needs PO Decision — where a SECOND (NPD) seat executed the
# very transition the first triage had already decided (2-3 wasted seats/ticket).
#
# THE CONTRACT (ABS-409): a po-agent Backlog-triage handoff that declares a
# machine-readable target (`to: <Status>`) is runner-applied by the EXISTING
# role-agnostic mechanism (apply_handoff_transition / handoff_target_status, the
# same "runner-applied handoff target" the bsa follow-up uses) — no respawn, no
# NPD detour. A target-less, non-transitioning triage is NOT silently advanced:
# it rests and the no-move is booked as an AUDITABLE HANDOFF-NOMOVE marker.
#
# Test method: call the real post-handoff entry point handoff_followthrough()
# directly in a subshell that sources orchestrator.sh with ORCH_STATE_DIR
# exported BEFORE the source (so run.log/LOCKS_DIR derive into the test dir) and
# the real mock-tracker backed by a temp tickets dir. Commit + marker gates off,
# no seat lock planted (so the seat-race guard fails open) — only the handoff
# target-apply / no-move path is under test.
# =============================================================================

echo -e "\n${CYAN}=== ABS-409 PO first-triage declared-target apply ===${NC}"

_abs409_dir="$(mktemp -d /tmp/abs409-XXXXXX)"
_abs409_tdir="$_abs409_dir/tickets"
_abs409_hf="$_abs409_dir/handoff.txt"
mkdir -p "$_abs409_tdir"

# _abs409_tracker <args...> — mock tracker backed by the test's isolated dirs.
_abs409_tracker() { MOCK_TRACKER_TICKETS_DIR="$_abs409_tdir" \
    MOCK_TRACKER_STATUSES="$MOCK_TRACKER_STATUSES" bash "$TRACKER" "$@"; }

# _abs409_run <state-dir> <ticket> <to> <role> <extra-env> <handoff>
# Calls handoff_followthrough() in an isolated subshell. <extra-env> is eval'd
# after the source (e.g. to pin ORCH_ESCALATION_LOOPBREAKER). Prints INTENT lines.
_abs409_run() {
    local sdir="$1" tkt="$2" to="$3" role="$4" extra="$5"
    printf '%s' "$6" > "$_abs409_hf"
    ORCH_STATE_DIR="$sdir" bash -c '
        export ORCH_STATE_DIR="$4"
        source "$1" >/dev/null 2>&1
        export TRACKER_CMD="$2"
        export MOCK_TRACKER_TICKETS_DIR="$3"
        export MOCK_TRACKER_STATUSES="'"$MOCK_TRACKER_STATUSES"'"
        export ORCH_RUN_LOG="$4/run.log"
        MODE=live
        ORCH_VERIFY_COMMITS=0
        ORCH_VERIFY_MARKERS=0
        ORCH_HANDOFF_TRANSITION=1
        ORCH_RESPAWN_LIMIT=2
        '"$extra"'
        HANDOFF="$(cat "$5")"
        handoff_followthrough "$6" "$7" "$8" "$HANDOFF"
    ' _ "$ORCH" "$TRACKER" "$_abs409_tdir" "$sdir" \
      "$_abs409_hf" "$tkt" "$to" "$role" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC2: declared 'to:' target -> runner-applied, no respawn (Backlog -> Ready for Development)${NC}"
# ---------------------------------------------------------------------------
# A fresh mock ticket rests in Backlog. The po-agent first-triage declares a
# machine-readable target. The runner must apply it — exactly like the bsa
# follow-up "runner-applied handoff target" — with NO HANDOFF-NOMOVE.
_abs409_sd1="$_abs409_dir/s1"; mkdir -p "$_abs409_sd1"
_abs409_t1=$(_abs409_tracker create --type ticket --title "ABS-409 parentless backlog story" --role be-developer 2>/dev/null)

_abs409_h1="## Backlog Triage Decision
- role: po-agent
- ticket: $_abs409_t1
- WSJF: BV=8 TC=5 RR=3 / JS=3 -> score=5.3
- Verdict: dispatch
- Reasoning: coherent, independently implementable; releasing to a fresh implementer.
to: Ready for Development"

_abs409_out1="$(_abs409_run "$_abs409_sd1" "$_abs409_t1" "Backlog" "po-agent" "" "$_abs409_h1")"
_abs409_dump1="$(_abs409_tracker get "$_abs409_t1" 2>/dev/null)"
_abs409_st1="$(printf '%s\n' "$_abs409_dump1" | awk -F': ' '/^status:/{print $2; exit}')"
_abs409_log1="$(cat "$_abs409_sd1/run.log" 2>/dev/null || true)"

assert_eq "$_abs409_st1" "Ready for Development" \
    "ABS-409 AC2: po-agent first-triage 'to: Ready for Development' is runner-applied (Backlog -> Ready for Development)"
assert_contains "$_abs409_log1" "INTENT-RUNNER-TRANSITION" \
    "ABS-409 AC2: the transition is booked as a runner-applied handoff target (RUNNER-TRANSITION run.log line)"
assert_not_contains "$_abs409_log1" "INTENT-HANDOFF-NOMOVE" \
    "ABS-409 AC3: a declared-target first-triage produces NO HANDOFF-NOMOVE (no respawn loop)"
assert_not_contains "$_abs409_log1" "INTENT-RESPAWN-LIMIT" \
    "ABS-409 AC1: declared-target first-triage never reaches the respawn limit / NPD detour"
assert_not_contains "$_abs409_st1" "Needs PO Decision" \
    "ABS-409 AC1: declared-target first-triage never detours through Needs PO Decision"

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC3: target-less prose 'dispatchable' -> rests, VISIBLE HANDOFF-NOMOVE (not silent)${NC}"
# ---------------------------------------------------------------------------
# The regression shape: the seat scores WSJF and names the destination in PROSE
# only, with no machine-readable target and no transition. The runner cannot act
# on prose. It must NOT silently advance the ticket: it rests in Backlog and the
# no-move is recorded as an auditable HANDOFF-NOMOVE marker (run.log + comment).
# ORCH_ESCALATION_LOOPBREAKER=0 isolates the single-round no-move behavior.
_abs409_sd2="$_abs409_dir/s2"; mkdir -p "$_abs409_sd2"
_abs409_t2=$(_abs409_tracker create --type ticket --title "ABS-409 target-less triage" --role be-developer 2>/dev/null)

_abs409_h2="## Backlog Triage Decision
- role: po-agent
- ticket: $_abs409_t2
- WSJF: score=5.3
- Verdict: dispatch
- Reasoning: dispatchable per the status machine; belongs in Ready for Development (named in prose only)."

_abs409_out2="$(_abs409_run "$_abs409_sd2" "$_abs409_t2" "Backlog" "po-agent" "ORCH_ESCALATION_LOOPBREAKER=0" "$_abs409_h2")"
_abs409_dump2="$(_abs409_tracker get "$_abs409_t2" 2>/dev/null)"
_abs409_st2="$(printf '%s\n' "$_abs409_dump2" | awk -F': ' '/^status:/{print $2; exit}')"
_abs409_log2="$(cat "$_abs409_sd2/run.log" 2>/dev/null || true)"

assert_eq "$_abs409_st2" "Backlog" \
    "ABS-409 AC3: a target-less, non-transitioning first-triage does NOT silently advance (rests in Backlog)"
assert_contains "$_abs409_log2" "INTENT-HANDOFF-NOMOVE" \
    "ABS-409 AC3: the target-less handoff is VISIBLY handled — HANDOFF-NOMOVE booked (not a silent rest)"
assert_contains "$_abs409_dump2" "HANDOFF-NOMOVE" \
    "ABS-409 AC3: the no-move is recorded as an auditable gate-results comment on the ticket"

rm -rf "$_abs409_dir"
