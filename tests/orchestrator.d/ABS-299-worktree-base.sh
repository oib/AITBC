# =============================================================================
# ABS-299 — ensure_worktree bases new story branches on origin/main, not
#            a foreign checkout HEAD
# -----------------------------------------------------------------------------
# Sourced by tests/test-orchestrator.sh (no shebang, no re-`set -e`, shared
# assert helpers / counters — see docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS
# ensure_worktree() fell back to `git worktree add -b <ticket>-auto` with no
# base commit when no epic/<parent>-* branch existed. In a two-runner checkout
# one runner may have advanced HEAD to its own in-flight commits; a new
# worktree for a sibling story then silently inherited that foreign commit as
# its base, dragging the other runner's unreviewed code into the new branch's
# history — invisible until code review (ABS-279 retro, Befund 5).
#
# THE FIX
# The else-branch now resolves origin/$ORCH_LOCAL_MAIN_BRANCH explicitly and
# passes it to `git worktree add -b <ticket>-auto <sha>`. HEAD is only used
# when the remote ref cannot be resolved, and that fallback is logged.
#
# THREE SCENARIOS
#   Part A — no epic branch + foreign HEAD: new branch based on origin/main
#   Part B — epic branch present: worktree still based on it (no regression)
#   Part C — origin/main absent: provisioning succeeds on HEAD + log emitted
# =============================================================================

echo -e "\n${CYAN}ABS-299 — ensure_worktree bases new story branches on origin/main not foreign HEAD${NC}"

# ---------------------------------------------------------------------------
# Helper: call ensure_worktree in an isolated subshell.
#   $1 = ticket id
#   $2 = path to git repo (ORCH_TARGET_REPO for the subshell)
#   $ORCH must be visible from the calling scope (it is in the harness).
# Inherited exported env: TRACKER_CMD, MOCK_TRACKER_TICKETS_DIR.
# ORCH_STATE_DIR is pinned inside the target dir to avoid colliding with the
# harness's own state dir (exported by new_env).
# Returns: ensure_worktree exit code. Combined stdout+stderr always merged
# so log() output is capturable by $() without a separate variant.
# ---------------------------------------------------------------------------
_abs299_ew() {
    local ticket="$1" target="$2"
    ORCH_TARGET_REPO="$target" \
    ORCH_STATE_DIR="$target/.abs299-orch-state" \
    ORCH_PROTECT_LOCAL_MAIN=0 \
    bash -c '
        mkdir -p "$ORCH_STATE_DIR" 2>/dev/null
        source "$1" >/dev/null 2>&1
        ensure_worktree "$2"
    ' _abs299 "$ORCH" "$ticket" 2>&1
}

# ---------------------------------------------------------------------------
# Part A — no epic branch + foreign HEAD: new worktree bases on origin/main
# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Part A — no epic branch, foreign HEAD: new worktree must base on origin/main${NC}"
new_env

_ABS299_REMOTE="$(mktemp -d /tmp/abs299-remote-XXXXXX)"
git -C "$_ABS299_REMOTE" init -q --bare

_ABS299_TARGET="$(mktemp -d /tmp/abs299-target-XXXXXX)"
git -C "$_ABS299_TARGET" init -q
git -C "$_ABS299_TARGET" -c user.email=t@t -c user.name=t \
    commit --allow-empty -m "origin-main-base" -q
git -C "$_ABS299_TARGET" remote add origin "$_ABS299_REMOTE"
git -C "$_ABS299_TARGET" push origin HEAD:main -q 2>/dev/null

# Simulate a foreign runner: advance local HEAD beyond origin/main
git -C "$_ABS299_TARGET" -c user.email=t@t -c user.name=t \
    commit --allow-empty -m "foreign-runner-commit" -q

_ABS299_ORIGIN_SHA="$(git -C "$_ABS299_TARGET" rev-parse origin/main)"
_ABS299_FOREIGN_SHA="$(git -C "$_ABS299_TARGET" rev-parse HEAD)"

_ABS299_PARENT=$(tracker create --type ticket --title "abs299-parent-A" \
    --role be-developer)
_ABS299_T=$(tracker create --type ticket --title "abs299-story-A" \
    --role be-developer --parent "$_ABS299_PARENT")

_abs299_ew "$_ABS299_T" "$_ABS299_TARGET" || true

_ABS299_BRANCH_TIP="$(git -C "$_ABS299_TARGET" rev-parse --verify \
    "refs/heads/$_ABS299_T-auto" 2>/dev/null || echo MISSING)"

assert_eq "$_ABS299_BRANCH_TIP" "$_ABS299_ORIGIN_SHA" \
    "ABS-299 A1: new worktree branch tip == origin/main SHA (not foreign HEAD)"

# The foreign commit must NOT be reachable from the new branch
if git -C "$_ABS299_TARGET" merge-base --is-ancestor \
        "$_ABS299_FOREIGN_SHA" "$_ABS299_T-auto" 2>/dev/null; then
    _ABS299_FOREIGN_REACHABLE=yes
else
    _ABS299_FOREIGN_REACHABLE=no
fi
assert_eq "$_ABS299_FOREIGN_REACHABLE" "no" \
    "ABS-299 A2: foreign HEAD commit is NOT in the new branch's history"

rm -rf "$_ABS299_REMOTE" "$_ABS299_TARGET"
cleanup_env

# ---------------------------------------------------------------------------
# Part B — epic branch exists: worktree still based on it (no regression)
# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Part B — epic branch present: worktree still bases on it (regression guard)${NC}"
new_env

_ABS299_REMOTE="$(mktemp -d /tmp/abs299-remote-XXXXXX)"
git -C "$_ABS299_REMOTE" init -q --bare

_ABS299_TARGET="$(mktemp -d /tmp/abs299-target-XXXXXX)"
git -C "$_ABS299_TARGET" init -q
git -C "$_ABS299_TARGET" -c user.email=t@t -c user.name=t \
    commit --allow-empty -m "base-commit" -q
git -C "$_ABS299_TARGET" remote add origin "$_ABS299_REMOTE"
git -C "$_ABS299_TARGET" push origin HEAD:main -q 2>/dev/null

# Epic integration commit (distinct from origin/main)
git -C "$_ABS299_TARGET" -c user.email=t@t -c user.name=t \
    commit --allow-empty -m "epic-integration-commit" -q
_ABS299_PARENT=$(tracker create --type ticket --title "abs299-parent-B" \
    --role be-developer)
git -C "$_ABS299_TARGET" checkout -q -b "epic/$_ABS299_PARENT-integration"
_ABS299_EPIC_SHA="$(git -C "$_ABS299_TARGET" rev-parse HEAD)"

# Simulate foreign runner HEAD (ahead of epic branch, different commit)
git -C "$_ABS299_TARGET" checkout -q -b "foreign-runner-head"
git -C "$_ABS299_TARGET" -c user.email=t@t -c user.name=t \
    commit --allow-empty -m "foreign-above-epic" -q

_ABS299_T=$(tracker create --type ticket --title "abs299-story-B" \
    --role be-developer --parent "$_ABS299_PARENT")

_abs299_ew "$_ABS299_T" "$_ABS299_TARGET" || true

_ABS299_BRANCH_TIP="$(git -C "$_ABS299_TARGET" rev-parse --verify \
    "refs/heads/$_ABS299_T-auto" 2>/dev/null || echo MISSING)"

assert_eq "$_ABS299_BRANCH_TIP" "$_ABS299_EPIC_SHA" \
    "ABS-299 B1: epic branch present → worktree bases on epic branch tip (no regression)"

rm -rf "$_ABS299_REMOTE" "$_ABS299_TARGET"
cleanup_env

# ---------------------------------------------------------------------------
# Part C — origin/main absent: provisioning succeeds on HEAD + log emitted
# ---------------------------------------------------------------------------
echo -e "  ${CYAN}Part C — no origin/main: provisioning falls back to HEAD with a log line${NC}"
new_env

_ABS299_TARGET="$(mktemp -d /tmp/abs299-target-XXXXXX)"
git -C "$_ABS299_TARGET" init -q
git -C "$_ABS299_TARGET" -c user.email=t@t -c user.name=t \
    commit --allow-empty -m "local-only-commit" -q
# Deliberately NO remote → origin/main will not resolve

_ABS299_PARENT=$(tracker create --type ticket --title "abs299-parent-C" \
    --role be-developer)
_ABS299_T=$(tracker create --type ticket --title "abs299-story-C" \
    --role be-developer --parent "$_ABS299_PARENT")

_ABS299_LOG="$(_abs299_ew "$_ABS299_T" "$_ABS299_TARGET" || true)"
_ABS299_BRANCH_TIP="$(git -C "$_ABS299_TARGET" rev-parse --verify \
    "refs/heads/$_ABS299_T-auto" 2>/dev/null || echo MISSING)"

assert_not_contains "$_ABS299_BRANCH_TIP" "MISSING" \
    "ABS-299 C1: provisioning succeeds when origin/main absent (HEAD fallback)"

assert_contains "$_ABS299_LOG" "did not resolve" \
    "ABS-299 C2: fallback log line emitted when origin/main does not resolve"

rm -rf "$_ABS299_TARGET"
cleanup_env

unset _ABS299_REMOTE _ABS299_TARGET _ABS299_PARENT _ABS299_T
unset _ABS299_ORIGIN_SHA _ABS299_FOREIGN_SHA _ABS299_BRANCH_TIP
unset _ABS299_FOREIGN_REACHABLE _ABS299_EPIC_SHA _ABS299_LOG
