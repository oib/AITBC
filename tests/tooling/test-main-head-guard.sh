#!/bin/bash
# =============================================================================
# Test: a seat must not leave the MAIN checkout's HEAD moved off main (PILOT-66 AC3)
# =============================================================================
# Proves the mechanical post-checkout guard that closes the single most expensive
# pilot failure: a seat running in the MAIN checkout ran `git checkout -b <branch>`
# there and left that branch checked out, after which no `git worktree add` could
# check out the same branch — 131 alarmless SKIP-NOWORKTREE retries. Coverage:
#
#   AC3  end-to-end: a SEAT `git checkout -b <br>` in the main checkout snaps HEAD
#        back to the protected branch while KEEPING the new branch ref (so a later
#        `git worktree add <br>` succeeds); a HUMAN checkout (no seat env) is never
#        touched; a linked WORKTREE is never touched; an UNSAFE move (diverged
#        branch / dirty tree) is warn-only (no restore); the kill switch disables
#        it; the installer writes/removes the hook and never clobbers a foreign one.
#
# provision_main_head_guard is exercised by SOURCING scripts/orchestrator.sh (main
# is source-guarded). The hook itself is driven through real `git checkout`.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-main-head-guard.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/scripts/hooks/post-checkout-main-head-guard.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -8 <<<"$output" | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}

TMP="$(mktemp -d /tmp/mhg-XXXXXX)"
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

export ORCH_STATE_DIR="$TMP/state"
mkdir -p "$ORCH_STATE_DIR/locks"
export ORCH_LOCAL_MAIN_BRANCH="main"

# shellcheck disable=SC1090
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

# The runner spawns this test's shell WITH seat markers; clear them so each case
# controls its own seat context.
unset ORCH_SEAT ORCH_ROLE ORCH_TICKET ORCH_HEAD_GUARD_ACTIVE 2>/dev/null || true
export ORCH_PROTECT_LOCAL_MAIN=1

MODE="live"
cur_branch() { git -C "$1" symbolic-ref --short -q HEAD 2>/dev/null || echo DETACHED; }

# --- a fresh repo with the hook installed, a human seed commit on main --------
new_repo() {
    local repo="$1"
    git init -q "$repo" 2>/dev/null || { mkdir -p "$repo"; git -C "$repo" init -q; }
    git -C "$repo" symbolic-ref HEAD refs/heads/main
    git -C "$repo" config user.email t@t.dev; git -C "$repo" config user.name t
    git -C "$repo" config commit.gpgsign false 2>/dev/null || true
    echo seed > "$repo/f1"; git -C "$repo" add f1; git -C "$repo" commit -q -m "seed on main"
    ORCH_STATE_ROOT="$repo" ORCH_PROTECT_LOCAL_MAIN=1 provision_main_head_guard >/dev/null 2>&1
}

# =============================================================================
echo -e "${CYAN}=== a seat must not move the MAIN checkout's HEAD (PILOT-66 AC3) ===${NC}\n"
echo -e "${CYAN}installer${NC}"
# =============================================================================
REPO="$TMP/repo"; new_repo "$REPO"
assert_eq "$([ -x "$REPO/.git/hooks/post-checkout" ] && echo yes || echo no)" "yes" "installer wrote an executable post-checkout hook"
assert_contains "$(cat "$REPO/.git/hooks/post-checkout")" "PILOT-66-main-head-guard" "installed hook carries the guard marker"

# =============================================================================
echo -e "\n${CYAN}AC3 — a SEAT 'git checkout -b' in the main checkout snaps HEAD back to main${NC}"
# =============================================================================
( cd "$REPO" && ORCH_SEAT=ui-ux-design git checkout -b feature-x ) >/dev/null 2>&1
assert_eq "$(cur_branch "$REPO")" "main" "seat checkout -b feature-x -> HEAD restored to main"
assert_eq "$(git -C "$REPO" show-ref --verify --quiet refs/heads/feature-x && echo yes || echo no)" "yes" "the new branch ref is KEPT (a later 'git worktree add feature-x' can succeed)"
# The kept branch is now checkout-able in a worktree (the whole point).
assert_eq "$(git -C "$REPO" worktree add -q "$TMP/wt-fx" feature-x >/dev/null 2>&1 && echo ok || echo fail)" "ok" "'git worktree add feature-x' succeeds because the main checkout freed the branch"
git -C "$REPO" worktree remove --force "$TMP/wt-fx" >/dev/null 2>&1 || true

# =============================================================================
echo -e "\n${CYAN}AC3 — a HUMAN checkout (no seat env) is never touched${NC}"
# =============================================================================
( cd "$REPO" && git checkout -b human-branch ) >/dev/null 2>&1
assert_eq "$(cur_branch "$REPO")" "human-branch" "human checkout -b -> HEAD stays on human-branch (guard is seat-only)"
git -C "$REPO" checkout -q main

# =============================================================================
echo -e "\n${CYAN}AC3 — an UNSAFE move (branch diverged from main) is warn-only, no restore${NC}"
# =============================================================================
# Born a branch at a DIFFERENT commit than main, then checkout it as a seat: the
# restore precondition (new branch tip == main tip) fails -> leave HEAD as-is.
echo more > "$REPO/f2"; git -C "$REPO" add f2; git -C "$REPO" commit -q -m c2   # main advances
git -C "$REPO" branch diverged HEAD~1                                            # diverged != main tip
out=$( cd "$REPO" && ORCH_SEAT=qas git checkout diverged 2>&1 )
assert_eq "$(cur_branch "$REPO")" "diverged" "diverged-branch seat checkout -> NOT restored (unsafe), HEAD left on diverged"
assert_contains "$out" "post-checkout WARN (PILOT-66)" "unsafe move still emits the loud WARN"
git -C "$REPO" checkout -q main

# =============================================================================
echo -e "\n${CYAN}AC3 — a linked WORKTREE is never touched (guard is main-checkout only)${NC}"
# =============================================================================
git -C "$REPO" worktree add -q "$TMP/wt" -b wtbranch >/dev/null 2>&1
( cd "$TMP/wt" && ORCH_SEAT=be-developer git checkout -b wt-inner ) >/dev/null 2>&1
assert_eq "$(cur_branch "$TMP/wt")" "wt-inner" "seat checkout in a linked worktree -> HEAD stays (git-dir != common-dir)"
git -C "$REPO" worktree remove --force "$TMP/wt" >/dev/null 2>&1 || true

# =============================================================================
echo -e "\n${CYAN}AC3 — kill switch: installer removes its own guard, leaves foreign hooks${NC}"
# =============================================================================
ORCH_STATE_ROOT="$REPO" ORCH_PROTECT_LOCAL_MAIN=0 provision_main_head_guard >/dev/null 2>&1
assert_eq "$([ -f "$REPO/.git/hooks/post-checkout" ] && echo yes || echo no)" "no" "kill switch off -> installer removed the guard hook"
# With the guard gone, a seat checkout moves HEAD freely (proves enforcement was the hook).
( cd "$REPO" && ORCH_SEAT=qas git checkout -b after-kill ) >/dev/null 2>&1
assert_eq "$(cur_branch "$REPO")" "after-kill" "kill switch off -> seat checkout is no longer restored"
git -C "$REPO" checkout -q main

printf '#!/bin/bash\n# operator hook\nexit 0\n' > "$REPO/.git/hooks/post-checkout"; chmod +x "$REPO/.git/hooks/post-checkout"
ORCH_STATE_ROOT="$REPO" ORCH_PROTECT_LOCAL_MAIN=1 provision_main_head_guard >/dev/null 2>&1
assert_contains "$(cat "$REPO/.git/hooks/post-checkout")" "operator hook" "foreign post-checkout hook is left untouched (fail-open)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
