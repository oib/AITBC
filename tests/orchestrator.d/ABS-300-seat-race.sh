# =============================================================================
# ABS-300 — seat race: a foreign handoff may not overwrite a live seat's station
# -----------------------------------------------------------------------------
# Per-story include (ABS-215 pattern): `source`d by tests/test-orchestrator.sh
# into the live harness — no shebang, no `set -e`, no re-sourcing.
# Shares: assert_contains / assert_not_contains / assert_eq, PASS/FAIL/TOTAL,
# REPO_ROOT, ORCH (orchestrator.sh path), TRACKER (mock-tracker.sh path),
# MOCK_TRACKER_STATUSES.
#
# ROOT CAUSE (retro 2026-07-13, Befund 6): handoff_followthrough() applied a
# handoff-declared transition without asking whether the author still owned the
# ticket's station. A sweep-spawned bsa follow-up hijacked the active RTE Merging
# seat's station — ABS-254 landed in `Ready for Merge` with NO PR.
#
# The fix (ABS-300): the seat lock now records its OWNER (a sibling .owner file,
# $ORCH_SEAT_TOKEN). Before applying the transition, handoff_followthrough refuses
# when a DIFFERENT, still-LIVE seat (lock age < ORCH_LOCK_TTL) owns the station:
# SEAT-RACE runlog line + comment, status unchanged, and the refusal skips every
# budget-bearing path. A STALE lock (age >= ORCH_LOCK_TTL) does NOT block (a dead
# seat must not freeze the ticket). Default-on safety refusal (ORCH_SEAT_RACE_GUARD).
#
# Test method: plant a lock dir + .owner sibling under the isolated state dir,
# then call handoff_followthrough() directly in a subshell that sources
# orchestrator.sh with ORCH_STATE_DIR exported BEFORE the source (so LOCKS_DIR
# derives into the test dir) and the real mock-tracker backed by a temp tickets
# dir. Commit + marker gates are off so only the seat-race gate is under test.
# =============================================================================

echo -e "\n${CYAN}=== ABS-300 seat-race guard in handoff_followthrough ===${NC}"

_abs300_dir="$(mktemp -d /tmp/abs300-XXXXXX)"
_abs300_tdir="$_abs300_dir/tickets"
_abs300_hf="$_abs300_dir/handoff.txt"
mkdir -p "$_abs300_tdir"

# _abs300_tracker <args...> — mock tracker backed by the test's isolated dirs.
_abs300_tracker() { MOCK_TRACKER_TICKETS_DIR="$_abs300_tdir" \
    MOCK_TRACKER_STATUSES="$MOCK_TRACKER_STATUSES" bash "$TRACKER" "$@"; }

# _abs300_run <state-dir> <ticket> <to> <role> <seat-token> <extra-env> <handoff>
# Calls handoff_followthrough() in an isolated subshell. <extra-env> is eval'd
# after the source (e.g. to set ORCH_LOCK_TTL / pre-seed the escalation counter).
# Prints the INTENT lines on stdout.
_abs300_run() {
    local sdir="$1" tkt="$2" to="$3" role="$4" token="$5" extra="$6"
    printf '%s' "$7" > "$_abs300_hf"
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
        ORCH_ESCALATION_LOOPBREAKER=1
        ORCH_SEAT_TOKEN="'"$token"'"
        '"$extra"'
        HANDOFF="$(cat "$5")"
        handoff_followthrough "$6" "$7" "$8" "$HANDOFF"
    ' _ "$ORCH" "$TRACKER" "$_abs300_tdir" "$sdir" \
      "$_abs300_hf" "$tkt" "$to" "$role" 2>/dev/null || true
}

# Plant a seat lock owned by <owner-token> for <ticket> under <state-dir>. The
# owner is a SIBLING .owner file (the lock dir must stay empty for rmdir release).
_abs300_plant_lock() {
    local sdir="$1" tkt="$2" owner="$3"
    mkdir -p "$sdir/locks/$tkt"
    printf '%s' "$owner" > "$sdir/locks/$tkt.owner"
}

# Walk a fresh story down the legal pipeline edges to the Merging seat, so a
# handoff at Merging (default target Ready for Merge) can be exercised.
_abs300_to_merging() {
    local tkt="$1"
    _abs300_tracker transition "$tkt" "Ready for Development" --actor orchestrator --reason setup >/dev/null 2>&1
    _abs300_tracker transition "$tkt" "In Progress"           --actor be-developer --reason setup >/dev/null 2>&1
    _abs300_tracker transition "$tkt" "In Review"             --actor system-architect --reason setup >/dev/null 2>&1
    _abs300_tracker transition "$tkt" "In Test"               --actor qas --reason setup >/dev/null 2>&1
    _abs300_tracker transition "$tkt" "Design Test"           --actor qas --reason setup >/dev/null 2>&1
    _abs300_tracker transition "$tkt" "Story Acceptance"      --actor po-agent --reason setup >/dev/null 2>&1
    _abs300_tracker transition "$tkt" "Merging"               --actor rte --reason setup >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC1: foreign handoff races a LIVE lock -> REFUSED (status unchanged)${NC}"
# ---------------------------------------------------------------------------
# Seat A (rte) holds a fresh, live lock on the Merging story. Seat B (bsa
# follow-up) hands off declaring Merging -> Ready for Merge. It must be refused.
_abs300_sd1="$_abs300_dir/s1"; mkdir -p "$_abs300_sd1"
_abs300_t1=$(_abs300_tracker create --type ticket --title "ABS-300 live merging story" 2>/dev/null)
_abs300_to_merging "$_abs300_t1"
# Live lock owned by seat A (the RTE that is still merging).
_abs300_plant_lock "$_abs300_sd1" "$_abs300_t1" "rte-seat-A-token"

_abs300_h1="## Handoff
- role: bsa
- ticket: $_abs300_t1
- summary: follow-up watcher spawned me; declaring the merge done.
- to: Ready for Merge"

# Author = seat B (a DIFFERENT token than the lock owner).
_abs300_out1="$(_abs300_run "$_abs300_sd1" "$_abs300_t1" "Merging" "bsa" "bsa-seat-B-token" "" "$_abs300_h1")"

assert_contains "$_abs300_out1" "INTENT SEAT-RACE ticket=$_abs300_t1" \
    "ABS-300 AC1: foreign handoff racing a live lock emits INTENT SEAT-RACE"
assert_contains "$(cat "$_abs300_sd1/run.log" 2>/dev/null || true)" "SEAT-RACE" \
    "ABS-300 AC1: SEAT-RACE runlog line emitted"
_abs300_dump1="$(_abs300_tracker get "$_abs300_t1" 2>/dev/null)"
assert_contains "$_abs300_dump1" "SEAT-RACE" \
    "ABS-300 AC1: refusal comment posted (SEAT-RACE gate-results)"
_abs300_st1="$(printf '%s\n' "$_abs300_dump1" | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_abs300_st1" "Merging" \
    "ABS-300 AC1: status unchanged — declared transition NOT applied (station kept for the live owner)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC2a: happy path — the LOCK-OWNING seat's handoff applies (no false refusal)${NC}"
# ---------------------------------------------------------------------------
# Same live lock, but this time the author IS the owner — the transition applies.
_abs300_sd2="$_abs300_dir/s2"; mkdir -p "$_abs300_sd2"
_abs300_t2=$(_abs300_tracker create --type ticket --title "ABS-300 owner-applies story" 2>/dev/null)
_abs300_to_merging "$_abs300_t2"
_abs300_plant_lock "$_abs300_sd2" "$_abs300_t2" "rte-owner-token"

_abs300_h2="## Handoff
- role: rte
- ticket: $_abs300_t2
- summary: PR opened; resting at the human merge gate.
- to: Ready for Merge"

_abs300_out2="$(_abs300_run "$_abs300_sd2" "$_abs300_t2" "Merging" "rte" "rte-owner-token" "" "$_abs300_h2")"

assert_not_contains "$_abs300_out2" "INTENT SEAT-RACE" \
    "ABS-300 AC2a: the lock-owning seat is NOT refused (no false SEAT-RACE)"
_abs300_st2="$(_abs300_tracker get "$_abs300_t2" 2>/dev/null | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_abs300_st2" "Ready for Merge" \
    "ABS-300 AC2a: lock-owning seat's declared transition applies (Merging -> Ready for Merge)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC2b: happy path — ordinary single-seat case (no lock at all) applies${NC}"
# ---------------------------------------------------------------------------
# No lock dir on disk (or an unstamped legacy lock): the guard must fail open.
_abs300_sd3="$_abs300_dir/s3"; mkdir -p "$_abs300_sd3"
_abs300_t3=$(_abs300_tracker create --type ticket --title "ABS-300 single-seat story" 2>/dev/null)
_abs300_to_merging "$_abs300_t3"
# no _abs300_plant_lock — no seat lock present

_abs300_h3="## Handoff
- role: rte
- ticket: $_abs300_t3
- summary: single seat, no contention.
- to: Ready for Merge"

_abs300_out3="$(_abs300_run "$_abs300_sd3" "$_abs300_t3" "Merging" "rte" "rte-lone-token" "" "$_abs300_h3")"

assert_not_contains "$_abs300_out3" "INTENT SEAT-RACE" \
    "ABS-300 AC2b: single-seat normal case is never refused"
_abs300_st3="$(_abs300_tracker get "$_abs300_t3" 2>/dev/null | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_abs300_st3" "Ready for Merge" \
    "ABS-300 AC2b: single-seat handoff applies normally (Merging -> Ready for Merge)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC3: a STALE lock (age >= ORCH_LOCK_TTL) does NOT block the handoff${NC}"
# ---------------------------------------------------------------------------
# A dead seat's orphaned lock must not freeze the ticket. Owner differs from the
# author, but the lock is backdated so its age exceeds ORCH_LOCK_TTL.
_abs300_sd4="$_abs300_dir/s4"; mkdir -p "$_abs300_sd4"
_abs300_t4=$(_abs300_tracker create --type ticket --title "ABS-300 stale-lock story" 2>/dev/null)
_abs300_to_merging "$_abs300_t4"
_abs300_plant_lock "$_abs300_sd4" "$_abs300_t4" "dead-seat-token"
# Backdate the lock dir so its age far exceeds any sane ORCH_LOCK_TTL.
touch -t 200001010000 "$_abs300_sd4/locks/$_abs300_t4" 2>/dev/null

_abs300_h4="## Handoff
- role: rte
- ticket: $_abs300_t4
- summary: reclaiming from a crashed prior seat.
- to: Ready for Merge"

_abs300_out4="$(_abs300_run "$_abs300_sd4" "$_abs300_t4" "Merging" "rte" "fresh-seat-token" \
    "ORCH_LOCK_TTL=4000" "$_abs300_h4")"

assert_not_contains "$_abs300_out4" "INTENT SEAT-RACE" \
    "ABS-300 AC3: a stale (dead-seat) lock does NOT trigger a SEAT-RACE refusal"
_abs300_st4="$(_abs300_tracker get "$_abs300_t4" 2>/dev/null | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_abs300_st4" "Ready for Merge" \
    "ABS-300 AC3: handoff applies over a stale lock (dead seat must not freeze the ticket)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC4: the refusal does NOT count against the rework/no-move budget${NC}"
# ---------------------------------------------------------------------------
# Pre-seed the escalation counter, run a refused foreign handoff, and prove the
# counter is untouched (the refusal returns before every budget-bearing path).
_abs300_sd5="$_abs300_dir/s5"; mkdir -p "$_abs300_sd5"
_abs300_t5=$(_abs300_tracker create --type ticket --title "ABS-300 budget story" 2>/dev/null)
_abs300_to_merging "$_abs300_t5"
_abs300_plant_lock "$_abs300_sd5" "$_abs300_t5" "rte-live-owner"

_abs300_h5="## Handoff
- role: bsa
- ticket: $_abs300_t5
- summary: racing follow-up.
- to: Ready for Merge"

# extra-env pre-seeds the counter to 2 (high-water 6). After the refusal it must
# still be 2 — the race consumed no budget. Emit it so the parent can assert.
_abs300_out5="$(_abs300_run "$_abs300_sd5" "$_abs300_t5" "Merging" "bsa" "bsa-racer" \
    'escalation_write "'"$_abs300_t5"'" 2 6; ' "$_abs300_h5"; \
    ORCH_STATE_DIR="$_abs300_sd5" bash -c '
        export ORCH_STATE_DIR="'"$_abs300_sd5"'"
        source "'"$ORCH"'" >/dev/null 2>&1
        printf "budget=%s\n" "$(escalation_count "'"$_abs300_t5"'")"
    ' 2>/dev/null)"

assert_contains "$_abs300_out5" "INTENT SEAT-RACE" \
    "ABS-300 AC4: the foreign handoff was refused (precondition for the budget check)"
assert_contains "$_abs300_out5" "budget=2" \
    "ABS-300 AC4: refusal leaves the escalation/no-move counter untouched (was 2, still 2)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}  AC5: off-switch — ORCH_SEAT_RACE_GUARD=0 restores legacy (applies regardless)${NC}"
# ---------------------------------------------------------------------------
_abs300_sd6="$_abs300_dir/s6"; mkdir -p "$_abs300_sd6"
_abs300_t6=$(_abs300_tracker create --type ticket --title "ABS-300 off-switch story" 2>/dev/null)
_abs300_to_merging "$_abs300_t6"
_abs300_plant_lock "$_abs300_sd6" "$_abs300_t6" "rte-live-owner"

_abs300_h6="## Handoff
- role: bsa
- ticket: $_abs300_t6
- summary: racing follow-up under legacy behaviour.
- to: Ready for Merge"

_abs300_out6="$(_abs300_run "$_abs300_sd6" "$_abs300_t6" "Merging" "bsa" "bsa-racer" \
    "ORCH_SEAT_RACE_GUARD=0" "$_abs300_h6")"

assert_not_contains "$_abs300_out6" "INTENT SEAT-RACE" \
    "ABS-300 AC5: off-switch — no SEAT-RACE refusal when the guard is disabled"
_abs300_st6="$(_abs300_tracker get "$_abs300_t6" 2>/dev/null | awk -F': ' '/^status:/{print $2; exit}')"
assert_eq "$_abs300_st6" "Ready for Merge" \
    "ABS-300 AC5: off-switch — legacy behaviour applies the transition regardless of owner"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
rm -rf "$_abs300_dir"
unset -f _abs300_tracker _abs300_run _abs300_plant_lock
unset _abs300_dir _abs300_tdir _abs300_hf \
      _abs300_sd1 _abs300_sd2 _abs300_sd3 _abs300_sd4 _abs300_sd5 _abs300_sd6 \
      _abs300_t1 _abs300_t2 _abs300_t3 _abs300_t4 _abs300_t5 _abs300_t6 \
      _abs300_h1 _abs300_h2 _abs300_h3 _abs300_h4 _abs300_h5 _abs300_h6 \
      _abs300_out1 _abs300_out2 _abs300_out3 _abs300_out4 _abs300_out5 _abs300_out6 \
      _abs300_dump1 _abs300_st1 _abs300_st2 _abs300_st3 _abs300_st4 _abs300_st6
