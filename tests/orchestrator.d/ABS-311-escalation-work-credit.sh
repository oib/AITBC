# =============================================================================
# ABS-311 — escalation budget: a no-move round with VERIFIED work is not a stall
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, shared harness — see
# docs/sop/TEST_SUITE_LAYOUT.md). In scope: assert_contains / assert_eq /
# assert_not_contains, PASS/FAIL/TOTAL, ORCH / MOCK_TRACKER_STATUSES.
#
# ROOT CAUSE: escalation_note_stall() is called only on the no-move path and
# counts every no-move round as a stall — it never asks whether the round DID
# anything. ABS-301 exempted terminal statuses; this story closes the broader
# class: a fresh no-move round that produced verified work (RTE rebasing / merging
# at Epic Integration) must not consume the budget (ABS-245 was falsely parked).
#
# The fix is a work-credit signal on the no-move path (escalation_work_credit):
#   Source A — runner-verified commits: hashes (strong, unbounded, ADR-A-0024).
#   Source B — an explicit progress: marker, no commits (weak, bounded per run).
# Credit PAUSES the counter, never resets it. OFF by default (regression-safe).
# =============================================================================

echo -e "\n${CYAN}=== ABS-311 escalation work-credit (no-move round with verified work) ===${NC}\n"

# A self-contained git repo + one real commit whose hash a handoff can claim and
# the runner can verify (existence + ref-reachability). Emits: <state_dir> <sha>.
# Reused by every subshell below via its own mktemp dirs (no shared state).
_abs311_helper='
    _sd="$(mktemp -d)"; _repo="$(mktemp -d)"
    git -C "$_repo" init -q
    git -C "$_repo" config user.email t@t.t; git -C "$_repo" config user.name t
    echo work > "$_repo/f"; git -C "$_repo" add f; git -C "$_repo" commit -qm work >/dev/null 2>&1
    _sha="$(git -C "$_repo" rev-parse HEAD)"
    export ORCH_STATE_DIR="$_sd" ORCH_STATE_ROOT="$_repo" ORCH_RUN_LOG="$_sd/run.log"
    export ORCH_VERIFY_COMMITS=1 ORCH_ESCALATION_LOOPBREAKER=1
'

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-311 AC1 — verified commits: no increment, ESCALATION-WORK-CREDIT logged, never parks past budget${NC}"
# ---------------------------------------------------------------------------
_abs311_ac1() {
    bash -c '
        source "$1" >/dev/null 2>&1
        '"$_abs311_helper"'
        export ORCH_ESCALATION_BUDGET=2 ORCH_ESCALATION_WORK_CREDIT=1
        export MOCK_TRACKER_STATUSES="$2"
        H="handoff: rebased and merged
- commits: $_sha"
        parked=no
        # Run MORE rounds than the budget; each is a no-move round WITH verified work.
        for i in 1 2 3 4; do
            if escalation_work_credit "T" "Epic Integration" "$H"; then
                : # credited — withhold the stall increment
            else
                escalation_note_stall "T" "Epic Integration" "rte" && parked=yes
            fi
        done
        printf "count=%s parked=%s\n" "$(escalation_count "T")" "$parked"
        grep -q "ESCALATION-WORK-CREDIT" "$ORCH_RUN_LOG" && echo "LOGGED" || echo "NOLOG"
        rm -rf "$ORCH_STATE_DIR" "$ORCH_STATE_ROOT"
    ' _abs311 "$ORCH" "$MOCK_TRACKER_STATUSES"
}
_abs311_o1="$(_abs311_ac1)"
assert_eq "$(printf '%s\n' "$_abs311_o1" | grep -o 'count=[0-9]*' | cut -d= -f2)" "0" \
    "ABS-311 AC1: verified-commit no-move rounds never increment the escalation counter"
assert_contains "$_abs311_o1" "parked=no" \
    "ABS-311 AC1: ticket producing verified commits is NOT parked past budget"
assert_contains "$_abs311_o1" "LOGGED" \
    "ABS-311 AC1: ESCALATION-WORK-CREDIT emitted to the run log (audit trail)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-311 AC2 — no masking of real stalls (ABS-301 AC3 must not regress)${NC}"
# ---------------------------------------------------------------------------
# (a) A no-move round with NO commits and NO progress marker increments and parks
#     at budget exactly as today. (b) A round claiming hashes that FAIL runner
#     verification earns no credit (treated as no evidence → counts as a stall).
_abs311_ac2() {
    bash -c '
        source "$1" >/dev/null 2>&1
        '"$_abs311_helper"'
        export ORCH_ESCALATION_BUDGET=2 ORCH_ESCALATION_WORK_CREDIT=1
        export MOCK_TRACKER_STATUSES="$2"
        H_bare="handoff: still stuck, nothing to show"
        H_fake="handoff: I totally committed
- commits: deadbeef1234567"
        # Bare handoff: credit denied, stall counts, parks at budget=2.
        parked_bare=no
        for i in 1 2; do
            if escalation_work_credit "TB" "In Progress" "$H_bare"; then :; else
                escalation_note_stall "TB" "In Progress" "be-developer" && parked_bare=yes
            fi
        done
        # Fake-hash handoff: handoff_work_verified must be FALSE → no credit.
        cred_fake=yes
        escalation_work_credit "TF" "In Progress" "$H_fake" || cred_fake=no
        printf "count_bare=%s parked_bare=%s cred_fake=%s\n" \
            "$(escalation_count "TB")" "$parked_bare" "$cred_fake"
        rm -rf "$ORCH_STATE_DIR" "$ORCH_STATE_ROOT"
    ' _abs311 "$ORCH" "$MOCK_TRACKER_STATUSES"
}
_abs311_o2="$(_abs311_ac2)"
assert_eq "$(printf '%s\n' "$_abs311_o2" | grep -o 'count_bare=[0-9]*' | cut -d= -f2)" "2" \
    "ABS-311 AC2: no-commit/no-progress round increments exactly as today"
assert_contains "$_abs311_o2" "parked_bare=yes" \
    "ABS-311 AC2: a genuine stall still parks at budget (ABS-301 AC3 intact)"
assert_contains "$_abs311_o2" "cred_fake=no" \
    "ABS-311 AC2: hashes that FAIL runner verification earn no credit (no evidence = stall)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-311 AC3 — source-B progress credit is bounded (no infinite immunity)${NC}"
# ---------------------------------------------------------------------------
# After ORCH_ESCALATION_WORK_BUDGET progress-marker credited rounds, further
# no-move rounds increment again and the ticket is eventually parked.
_abs311_ac3() {
    bash -c '
        source "$1" >/dev/null 2>&1
        '"$_abs311_helper"'
        export ORCH_ESCALATION_BUDGET=2 ORCH_ESCALATION_WORK_BUDGET=2 ORCH_ESCALATION_WORK_CREDIT=1
        export MOCK_TRACKER_STATUSES="$2"
        H="handoff: no commit this round
- progress: bisecting the smoke failure, ruled out 4 commits"
        credits=0 parked=no
        # 2 credited rounds (=work budget), then rounds start counting toward the
        # escalation budget of 2 → parks on the 2nd counted round.
        for i in 1 2 3 4 5 6; do
            if escalation_work_credit "TP" "Epic Integration" "$H"; then
                credits=$(( credits + 1 ))
            else
                escalation_note_stall "TP" "Epic Integration" "rte" && parked=yes
            fi
        done
        printf "credits=%s count=%s parked=%s\n" "$credits" "$(escalation_count "TP")" "$parked"
        rm -rf "$ORCH_STATE_DIR" "$ORCH_STATE_ROOT"
    ' _abs311 "$ORCH" "$MOCK_TRACKER_STATUSES"
}
_abs311_o3="$(_abs311_ac3)"
assert_eq "$(printf '%s\n' "$_abs311_o3" | grep -o 'credits=[0-9]*' | cut -d= -f2)" "2" \
    "ABS-311 AC3: source-B progress credit stops after ORCH_ESCALATION_WORK_BUDGET rounds"
assert_contains "$_abs311_o3" "parked=yes" \
    "ABS-311 AC3: a seat that only ASSERTS progress is eventually parked (bounded, not immortal)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-311 AC4 — credit PAUSES but never RESETS the counter${NC}"
# ---------------------------------------------------------------------------
# A credited round must hold the counter at its prior value (not drop to 0). Only
# a forward transition (escalation_note_progress) resets it (ABS-301 ratchet).
_abs311_ac4() {
    bash -c '
        source "$1" >/dev/null 2>&1
        '"$_abs311_helper"'
        export ORCH_ESCALATION_BUDGET=5 ORCH_ESCALATION_WORK_CREDIT=1
        export MOCK_TRACKER_STATUSES="$2"
        H="handoff: merged
- commits: $_sha"
        # Pre-load the stall counter to 2 (high-water 3 = In Progress) to prove the
        # credited round does not zero it.
        escalation_write "TR" 2 3
        escalation_work_credit "TR" "In Review" "$H" >/dev/null   # credit → withhold, no reset
        held="$(escalation_count "TR")"
        # A real forward transition (In Review chain_index 4 > high-water 3) resets.
        escalation_note_progress "TR" "In Review"
        after_progress="$(escalation_count "TR")"
        printf "held=%s after_progress=%s\n" "$held" "$after_progress"
        rm -rf "$ORCH_STATE_DIR" "$ORCH_STATE_ROOT"
    ' _abs311 "$ORCH" "$MOCK_TRACKER_STATUSES"
}
_abs311_o4="$(_abs311_ac4)"
assert_eq "$(printf '%s\n' "$_abs311_o4" | grep -o 'held=[0-9]*' | cut -d= -f2)" "2" \
    "ABS-311 AC4: credited round holds the counter at its prior value (pauses, does not reset)"
assert_eq "$(printf '%s\n' "$_abs311_o4" | grep -o 'after_progress=[0-9]*' | cut -d= -f2)" "0" \
    "ABS-311 AC4: only a forward transition resets the counter (ABS-301 ratchet intact)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-311 AC5 — off-switch: ORCH_ESCALATION_WORK_CREDIT=0 is today's behaviour${NC}"
# ---------------------------------------------------------------------------
# With the knob off, a verified-commit no-move round STILL increments and STILL
# parks at budget — byte-for-byte the pre-ABS-311 behaviour (regression guard).
_abs311_ac5() {
    bash -c '
        source "$1" >/dev/null 2>&1
        '"$_abs311_helper"'
        export ORCH_ESCALATION_BUDGET=2 ORCH_ESCALATION_WORK_CREDIT=0
        export MOCK_TRACKER_STATUSES="$2"
        H="handoff: merged
- commits: $_sha"
        parked=no
        for i in 1 2; do
            if escalation_work_credit "TO" "Epic Integration" "$H"; then :; else
                escalation_note_stall "TO" "Epic Integration" "rte" && parked=yes
            fi
        done
        grep -q "ESCALATION-WORK-CREDIT" "$ORCH_RUN_LOG" && echo "LOGGED" || echo "NOLOG"
        printf "count=%s parked=%s\n" "$(escalation_count "TO")" "$parked"
        rm -rf "$ORCH_STATE_DIR" "$ORCH_STATE_ROOT"
    ' _abs311 "$ORCH" "$MOCK_TRACKER_STATUSES"
}
_abs311_o5="$(_abs311_ac5)"
assert_eq "$(printf '%s\n' "$_abs311_o5" | grep -o 'count=[0-9]*' | cut -d= -f2)" "2" \
    "ABS-311 AC5: off-switch — verified commits still increment when WORK_CREDIT=0"
assert_contains "$_abs311_o5" "parked=yes" \
    "ABS-311 AC5: off-switch — ticket still parks at budget (today's behaviour preserved)"
assert_contains "$_abs311_o5" "NOLOG" \
    "ABS-311 AC5: off-switch — no ESCALATION-WORK-CREDIT line emitted when disabled"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-311 AC6 — ABS-245 replay: epic at Epic Integration producing a commit each round is not parked${NC}"
# ---------------------------------------------------------------------------
# The exact ABS-245 scenario: an epic resting at Epic Integration whose RTE
# produces a verified commit (rebase / merge-log row) EVERY round. Across many
# more rounds than the budget it must never park to Blocked.
_abs311_ac6() {
    bash -c '
        source "$1" >/dev/null 2>&1
        '"$_abs311_helper"'
        export ORCH_ESCALATION_BUDGET=3 ORCH_ESCALATION_WORK_CREDIT=1
        export MOCK_TRACKER_STATUSES="$2"
        parked=no
        for i in 1 2 3 4 5 6 7 8; do
            # A fresh real commit each round (a rebase / merge-log-row artefact).
            echo "round $i" >> "$ORCH_STATE_ROOT/f"
            git -C "$ORCH_STATE_ROOT" commit -aqm "round $i" >/dev/null 2>&1
            rsha="$(git -C "$ORCH_STATE_ROOT" rev-parse HEAD)"
            H="rte: shepherded PR $i, appended merge-log row
- commits: $rsha"
            if escalation_work_credit "E-245" "Epic Integration" "$H"; then :; else
                escalation_note_stall "E-245" "Epic Integration" "rte" && parked=yes
            fi
        done
        printf "count=%s parked=%s\n" "$(escalation_count "E-245")" "$parked"
        rm -rf "$ORCH_STATE_DIR" "$ORCH_STATE_ROOT"
    ' _abs311 "$ORCH" "$MOCK_TRACKER_STATUSES"
}
_abs311_o6="$(_abs311_ac6)"
assert_contains "$_abs311_o6" "parked=no" \
    "ABS-311 AC6: ABS-245 replay — epic producing a verified commit each round is NOT parked"
assert_eq "$(printf '%s\n' "$_abs311_o6" | grep -o 'count=[0-9]*' | cut -d= -f2)" "0" \
    "ABS-311 AC6: ABS-245 replay — the escalation counter never accrues while work lands"

# ---------------------------------------------------------------------------
echo -e "${CYAN}ABS-311 helpers — progress-marker parsing discipline${NC}"
# ---------------------------------------------------------------------------
# handoff_progress_marker reads the declarative field only and ignores "none"/"n/a".
_abs311_helpers() {
    bash -c '
        source "$1" >/dev/null 2>&1
        m1=no; m2=no; m3=no
        handoff_progress_marker "- progress: narrowed the bisect to 2 commits" && m1=yes
        handoff_progress_marker "- progress: none" && m2=yes
        handoff_progress_marker "just a lot of prose about progress being made" && m3=yes
        printf "real=%s none=%s prose=%s\n" "$m1" "$m2" "$m3"
    ' _abs311 "$ORCH"
}
_abs311_oh="$(_abs311_helpers)"
assert_contains "$_abs311_oh" "real=yes" \
    "ABS-311 helper: handoff_progress_marker accepts an explicit progress: field"
assert_contains "$_abs311_oh" "none=no" \
    "ABS-311 helper: 'progress: none' is not a claim of advancement"
assert_contains "$_abs311_oh" "prose=no" \
    "ABS-311 helper: prose mentioning 'progress' is not a marker (declarative field only)"
