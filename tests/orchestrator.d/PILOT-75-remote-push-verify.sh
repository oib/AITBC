# =============================================================================
# PILOT-75 — forward transition must be backed by a PUSH to the active remote.
# -----------------------------------------------------------------------------
# Per-story include (ABS-215 pattern): `source`d by tests/test-orchestrator.sh
# into the live harness — no shebang, no `set -e`, no re-sourcing. Runs in an
# ISOLATED child via _run_d_include (ABS-370). Shares: assert_contains /
# assert_not_contains / assert_eq, PASS/FAIL/TOTAL, REPO_ROOT, ORCH
# (orchestrator.sh path), TRACKER (mock-tracker.sh path), MOCK_TRACKER_STATUSES.
#
# THE INCIDENT (four belegte Faelle in three runs, ABS-581). A seat forward-
# transitioned a ticket (Ready for Development/In Progress -> In Review and
# beyond) on work that existed ONLY in its local worktree — never pushed. The
# ABS-255 verifier passed it: a purely local commit satisfies existence
# (git cat-file -e) AND ref-reachability (any local refs/heads contains it). But
# outside the seat worktree the work does not exist; on cleanup it vanished and
# the operator had to recover the commits by hand (PILOT-23/24, PILOT-64, and 13
# branch-recoverable findings in pilot #7).
#
# THE GUARD (runner-side, push_verify_failures wired into handoff_followthrough).
# For a FORWARD transition that claims work COMPLETE (story chain In Review=4
# through Done=12), every CLAIMED commit must be reachable under
# refs/remotes/<active-remote>/ — which `git push` updates on a successful push,
# so the check stays network-free. Not on the active remote => refused on the
# SAME ABS-255 mis-report path (declared transition never applied; the work
# bounces back to the seat to actually push). The active remote is the only source
# (ADR-A-0030) — resolved via active_remote_name(), never a hardcoded origin.
#
# Test method: call the real post-handoff entry point handoff_followthrough()
# directly in a subshell that sources orchestrator.sh, then re-points
# ORCH_STATE_ROOT at a throwaway git repo. The active remote is pinned via
# ORCH_MAIN_REMOTE=gitlab; a pushed commit is modelled by a refs/remotes/gitlab/*
# ref (exactly what `git push` writes locally). Marker/commit-verify-only gates
# left at defaults; no seat lock planted (seat-race guard fails open) — only the
# push-verify path is under test.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-75 forward transition requires push to active remote ===${NC}"

_p75_dir="$(mktemp -d /tmp/pilot75-XXXXXX)"
_p75_tdir="$_p75_dir/tickets"
_p75_repo="$_p75_dir/repo"
_p75_hf="$_p75_dir/handoff.txt"
mkdir -p "$_p75_tdir"

_p75_tracker() { MOCK_TRACKER_TICKETS_DIR="$_p75_tdir" \
    MOCK_TRACKER_STATUSES="$MOCK_TRACKER_STATUSES" bash "$TRACKER" "$@"; }
_p75_git() { git -C "$_p75_repo" "$@"; }

# Walk a fresh story down the legal pipeline edges to In Review, so a handoff
# targeting In Review lands on cur==to (rested path, like ABS-482).
_p75_to_review() {
    local tkt="$1"
    _p75_tracker transition "$tkt" "Ready for Development" --actor orchestrator    --reason setup >/dev/null 2>&1
    _p75_tracker transition "$tkt" "In Progress"           --actor be-developer    --reason setup >/dev/null 2>&1
    _p75_tracker transition "$tkt" "In Review"             --actor system-architect --reason setup >/dev/null 2>&1
}

_p75_status() { _p75_tracker get "$1" 2>/dev/null | awk -F': ' '/^status:/{print $2; exit}'; }

# --- four tickets, one per scenario ------------------------------------------
_p75_t_local=$(_p75_tracker  create --type ticket --title "PILOT-75 local-only commit, forward transition" --role be-developer 2>/dev/null)
_p75_t_pushed=$(_p75_tracker create --type ticket --title "PILOT-75 pushed commit, forward transition"     --role be-developer 2>/dev/null)
_p75_t_backw=$(_p75_tracker  create --type ticket --title "PILOT-75 local-only commit, non-forward target"  --role be-developer 2>/dev/null)
_p75_t_ks=$(_p75_tracker     create --type ticket --title "PILOT-75 kill-switch off"                        --role be-developer 2>/dev/null)

# --- a throwaway git repo -----------------------------------------------------
mkdir -p "$_p75_repo"
_p75_git init -q
_p75_git config user.email "test@example.com"
_p75_git config user.name "Test"
echo "seed" > "$_p75_repo/seed.txt"
_p75_git add seed.txt
_p75_git commit -qm "base"
_p75_base="$(_p75_git rev-parse HEAD)"

# LOCAL-ONLY — a commit that lives on the story branch but was NEVER pushed:
# refs/heads/<ticket>-auto contains it, but NO refs/remotes/gitlab/* does.
_p75_git checkout -q -b "$_p75_t_local-auto" "$_p75_base"
echo "work" > "$_p75_repo/feature.txt"
_p75_git add feature.txt
_p75_git commit -qm "feat: local-only [PILOT-75]"
_p75_local_sha="$(_p75_git rev-parse HEAD)"

# PUSHED — a commit reachable on the active remote: a refs/remotes/gitlab/* ref
# points at it, exactly what `git push gitlab HEAD:<branch>` writes locally.
_p75_git checkout -q -b "$_p75_t_pushed-auto" "$_p75_base"
echo "work" > "$_p75_repo/feature2.txt"
_p75_git add feature2.txt
_p75_git commit -qm "feat: pushed [PILOT-75]"
_p75_pushed_sha="$(_p75_git rev-parse HEAD)"
_p75_git update-ref "refs/remotes/gitlab/$_p75_t_pushed-auto" "$_p75_pushed_sha"

_p75_git checkout -q "$_p75_base" 2>/dev/null

# _p75_run <state-dir> <ticket> <to> <role> <extra-env> <handoff>
# Calls handoff_followthrough() with ORCH_STATE_ROOT re-pointed at the test repo
# and the active remote pinned to "gitlab". <extra-env> is eval'd after source.
_p75_run() {
    local sdir="$1" tkt="$2" to="$3" role="$4" extra="$5"
    printf '%s' "$6" > "$_p75_hf"
    ORCH_STATE_DIR="$sdir" bash -c '
        export ORCH_STATE_DIR="$4"
        source "$1" >/dev/null 2>&1
        ORCH_STATE_ROOT="'"$_p75_repo"'"      # git checks run against the test repo
        ORCH_MAIN_REMOTE=gitlab               # active-remote pin (ADR-A-0030)
        ORCH_LOCAL_MAIN_BRANCH=main
        export TRACKER_CMD="$2"
        export MOCK_TRACKER_TICKETS_DIR="$3"
        export MOCK_TRACKER_STATUSES="'"$MOCK_TRACKER_STATUSES"'"
        export ORCH_RUN_LOG="$4/run.log"
        MODE=live
        ORCH_VERIFY_MARKERS=0
        ORCH_RESPAWN_LIMIT=99
        '"$extra"'
        HANDOFF="$(cat "$5")"
        handoff_followthrough "$6" "$7" "$8" "$HANDOFF"
    ' _ "$ORCH" "$TRACKER" "$_p75_tdir" "$sdir" \
      "$_p75_hf" "$tkt" "$to" "$role" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
echo -e "  ${CYAN}AC1/AC4: a local-only commit + forward transition (In Review) is REFUSED${NC}"
# ---------------------------------------------------------------------------
_p75_to_review "$_p75_t_local"
_p75_sd1="$_p75_dir/s1"; mkdir -p "$_p75_sd1"
_p75_h1="## Implementation handoff
- role: be-developer
- ticket: $_p75_t_local
- commits: $_p75_local_sha
Implemented and pushed."
_p75_run "$_p75_sd1" "$_p75_t_local" "In Review" "be-developer" "" "$_p75_h1"
_p75_dump1="$(_p75_tracker get "$_p75_t_local" 2>/dev/null)"

assert_contains "$_p75_dump1" "HANDOFF-MISREPORT" \
    "PILOT-75 AC2: a never-pushed commit on a forward transition is refused on the mis-report path"
assert_contains "$_p75_dump1" "NOT reachable on the active remote" \
    "PILOT-75 AC1: the refusal names the remote-reachability failure (commit must be on the active remote)"
assert_contains "$_p75_dump1" "gitlab" \
    "PILOT-75 AC1: the refusal names the active remote (never a hardcoded origin)"
assert_contains "$_p75_dump1" "$_p75_local_sha" \
    "PILOT-75: the refusal names the failing commit hash"

# ---------------------------------------------------------------------------
echo -e "  ${CYAN}AC4 (control): the SAME commit, PUSHED to the active remote, is ACCEPTED${NC}"
# ---------------------------------------------------------------------------
_p75_to_review "$_p75_t_pushed"
_p75_sd2="$_p75_dir/s2"; mkdir -p "$_p75_sd2"
_p75_h2="## Implementation handoff
- role: be-developer
- ticket: $_p75_t_pushed
- commits: $_p75_pushed_sha
Implemented and pushed."
_p75_run "$_p75_sd2" "$_p75_t_pushed" "In Review" "be-developer" "" "$_p75_h2"
assert_not_contains "$(_p75_tracker get "$_p75_t_pushed" 2>/dev/null)" "HANDOFF-MISREPORT" \
    "PILOT-75 AC4: a commit reachable on the active remote is never refused"

# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Scope: a local-only commit on a NON-completion target (In Progress) is EXEMPT${NC}"
# ---------------------------------------------------------------------------
_p75_tracker transition "$_p75_t_backw" "Ready for Development" --actor orchestrator --reason setup >/dev/null 2>&1
_p75_tracker transition "$_p75_t_backw" "In Progress"          --actor be-developer --reason setup >/dev/null 2>&1
_p75_sd3="$_p75_dir/s3"; mkdir -p "$_p75_sd3"
_p75_h3="## Implementation handoff
- role: be-developer
- ticket: $_p75_t_backw
- commits: $_p75_local_sha
Work in progress, committed locally."
_p75_run "$_p75_sd3" "$_p75_t_backw" "In Progress" "be-developer" "" "$_p75_h3"
assert_not_contains "$(_p75_tracker get "$_p75_t_backw" 2>/dev/null)" "HANDOFF-MISREPORT" \
    "PILOT-75 scope: the push gate only fires on completion targets (In Review..Done), not In Progress"

# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Kill switch: ORCH_VERIFY_PUSH=0 restores the pre-PILOT-75 behaviour${NC}"
# ---------------------------------------------------------------------------
_p75_to_review "$_p75_t_ks"
_p75_sd4="$_p75_dir/s4"; mkdir -p "$_p75_sd4"
_p75_h4="## Implementation handoff
- role: be-developer
- ticket: $_p75_t_ks
- commits: $_p75_local_sha
Implemented and pushed."
_p75_run "$_p75_sd4" "$_p75_t_ks" "In Review" "be-developer" "ORCH_VERIFY_PUSH=0" "$_p75_h4"
assert_not_contains "$(_p75_tracker get "$_p75_t_ks" 2>/dev/null)" "HANDOFF-MISREPORT" \
    "PILOT-75 kill-switch: ORCH_VERIFY_PUSH=0 disables the remote-reachability refusal"

rm -rf "$_p75_dir"
unset _p75_dir _p75_tdir _p75_repo _p75_hf _p75_base \
      _p75_t_local _p75_t_pushed _p75_t_backw _p75_t_ks \
      _p75_local_sha _p75_pushed_sha \
      _p75_sd1 _p75_sd2 _p75_sd3 _p75_sd4 \
      _p75_h1 _p75_h2 _p75_h3 _p75_h4 _p75_dump1
unset -f _p75_tracker _p75_git _p75_to_review _p75_status _p75_run
