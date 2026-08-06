#!/bin/bash
# =============================================================================
# Test: seats never commit to local main (ABS-224)
# =============================================================================
# Proves the mechanical guard that closes the v2.24.0 watch-run Befund: two QAS
# seats committed QA reports straight onto the local `main` (dc8449f, cccfbd5),
# in no PR and never on origin. Coverage:
#
#   AC1  the pre-commit guard aborts a SEAT commit on local main (main/master),
#        end-to-end via a real `git commit`, while a HUMAN commit (no seat env)
#        on the same branch is allowed, and a seat commit on a story branch
#        (<ticket>-auto) is allowed.
#   AC3  check_local_main_drift WARNs (intent + notify) when local main is ahead
#        of origin/main, and is silent when in sync.
#   AC4  the kill switch (ORCH_PROTECT_LOCAL_MAIN=0) disables the guard, and the
#        installer removes a previously-installed guard when toggled off.
#   AC6  check_claim_protocol WARNs when a ticket rests in "Ready for Development"
#        under an active seat lock past the threshold; silent otherwise; disabled
#        by ORCH_CLAIM_WARN_MINUTES=0.
#
# The runner functions (provision_local_main_guard / check_local_main_drift /
# check_claim_protocol) are exercised by SOURCING scripts/orchestrator.sh (main
# is source-guarded). The hook itself is invoked directly and via real git.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-local-main-guard.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK="$REPO_ROOT/scripts/hooks/pre-commit-local-main-guard.sh"

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
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"; FAIL=$((FAIL + 1)); fi
}

TMP="$(mktemp -d /tmp/lmg-XXXXXX)"
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

# State dir must exist BEFORE sourcing so LOCKS_DIR / ORCH_STATE_DIR derive from
# the temp path (both are computed at source time from ORCH_STATE_DIR).
export ORCH_STATE_DIR="$TMP/state"
mkdir -p "$ORCH_STATE_DIR/locks"
# Deterministic branch protection set for the drift/claim helpers.
export ORCH_LOCAL_MAIN_BRANCH="main"

# shellcheck disable=SC1090
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

# The runner spawns this test's shell WITH seat markers (ORCH_ROLE/ORCH_TICKET)
# in the environment — exactly the propagation the guard relies on in production.
# Clear them so the test controls the seat context per case; each case that
# simulates a seat sets ORCH_SEAT explicitly. (This also proves the belt: without
# any marker the hook must treat a commit as human.)
unset ORCH_SEAT ORCH_ROLE ORCH_TICKET ORCH_GUARD_BRANCH 2>/dev/null || true
export ORCH_PROTECT_LOCAL_MAIN=1

# run_hook <branch> [env assignments...] — invoke the guard hook with a given
# branch (ORCH_GUARD_BRANCH override) and env, printing the exit code. Starts
# from a seat-marker-free environment so each case is explicit.
run_hook() {
    local branch="$1"; shift
    local rc=0
    env -u ORCH_SEAT -u ORCH_ROLE -u ORCH_TICKET ORCH_GUARD_BRANCH="$branch" "$@" bash "$HOOK" >/dev/null 2>&1 || rc=$?
    printf '%s' "$rc"
}

# =============================================================================
echo -e "${CYAN}=== seats never commit to local main (ABS-224) ===${NC}\n"
echo -e "${CYAN}AC1/AC4 — pre-commit guard logic (direct hook invocation)${NC}"
# =============================================================================
assert_eq "$(run_hook main ORCH_SEAT=qas)"            "1" "seat (ORCH_SEAT) on main -> BLOCKED"
assert_eq "$(run_hook master ORCH_SEAT=qas)"          "1" "seat on master -> BLOCKED"
assert_eq "$(run_hook main ORCH_ROLE=be-developer)"   "1" "seat via ORCH_ROLE on main -> BLOCKED"
assert_eq "$(run_hook main ORCH_TICKET=ABS-1)"        "1" "seat via ORCH_TICKET on main -> BLOCKED"
assert_eq "$(run_hook ABS-1-auto ORCH_SEAT=qas)"      "0" "seat on story branch ABS-1-auto -> allowed"
assert_eq "$(run_hook main)"                          "0" "HUMAN (no seat env) on main -> allowed (AC1)"
assert_eq "$(run_hook main ORCH_SEAT=qas ORCH_PROTECT_LOCAL_MAIN=0)" "0" "kill switch off -> allowed (AC4)"

# =============================================================================
echo -e "\n${CYAN}AC1 — end-to-end: a real seat git commit on local main is aborted${NC}"
# =============================================================================
REPO="$TMP/repo"
git init -q "$REPO" 2>/dev/null || { mkdir -p "$REPO"; git -C "$REPO" init -q; }
git -C "$REPO" symbolic-ref HEAD refs/heads/main
git -C "$REPO" config user.email t@t.dev; git -C "$REPO" config user.name t
git -C "$REPO" config commit.gpgsign false 2>/dev/null || true

MODE="live"
ORCH_STATE_ROOT="$REPO" ORCH_PROTECT_LOCAL_MAIN=1 provision_local_main_guard >/dev/null 2>&1
assert_eq "$([ -x "$REPO/.git/hooks/pre-commit" ] && echo yes || echo no)" "yes" "installer wrote an executable pre-commit hook"
assert_contains "$(cat "$REPO/.git/hooks/pre-commit")" "ABS-224-local-main-guard" "installed hook carries the guard marker"

# Human seed commit first (env has no seat markers) -> allowed, and it BORNs the
# main branch so subsequent commits resolve `--abbrev-ref HEAD` to 'main'.
echo "seed" > "$REPO/f1"; git -C "$REPO" add f1
rc=0; ( cd "$REPO" && git commit -q -m "human seed commit on main" ) >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "human commit on local main is allowed (no seat env)"

# Seat commit on the now-born local main -> REJECTED.
echo "report" > "$REPO/qa-report"; git -C "$REPO" add qa-report
rc=0; ( cd "$REPO" && ORCH_SEAT=qas git commit -q -m "seat report on main" ) >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "seat commit on local main is REJECTED by the installed hook (AC1)"

# A seat commit on a story branch off the same repo goes through.
git -C "$REPO" checkout -q -b ABS-1-auto
echo "work" > "$REPO/f2"; git -C "$REPO" add f2
rc=0; ( cd "$REPO" && ORCH_SEAT=qas git commit -q -m "seat work on story branch" ) >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "seat commit on the story branch ABS-1-auto is allowed (AC1)"
git -C "$REPO" checkout -q main

# =============================================================================
echo -e "\n${CYAN}AC4 — kill switch: installer removes its own guard, leaves foreign hooks${NC}"
# =============================================================================
ORCH_STATE_ROOT="$REPO" ORCH_PROTECT_LOCAL_MAIN=0 provision_local_main_guard >/dev/null 2>&1
assert_eq "$([ -f "$REPO/.git/hooks/pre-commit" ] && echo yes || echo no)" "no" "kill switch off -> installer removed the guard hook"

# Foreign pre-commit hook is never clobbered.
printf '#!/bin/bash\n# operator hook\nexit 0\n' > "$REPO/.git/hooks/pre-commit"; chmod +x "$REPO/.git/hooks/pre-commit"
ORCH_STATE_ROOT="$REPO" ORCH_PROTECT_LOCAL_MAIN=1 provision_local_main_guard >/dev/null 2>&1
assert_contains "$(cat "$REPO/.git/hooks/pre-commit")" "operator hook" "foreign pre-commit hook is left untouched (fail-open)"
rm -f "$REPO/.git/hooks/pre-commit"

# =============================================================================
echo -e "\n${CYAN}AC3 — check_local_main_drift warns when local main is ahead of origin${NC}"
# =============================================================================
DR="$TMP/drift"
git init -q "$DR"; git -C "$DR" symbolic-ref HEAD refs/heads/main
git -C "$DR" config user.email t@t.dev; git -C "$DR" config user.name t
git -C "$DR" config commit.gpgsign false 2>/dev/null || true
echo a > "$DR/a"; git -C "$DR" add a; git -C "$DR" commit -q -m c1
BASE="$(git -C "$DR" rev-parse main)"
git -C "$DR" update-ref refs/remotes/origin/main "$BASE"   # origin/main == c1
echo b > "$DR/b"; git -C "$DR" add b; git -C "$DR" commit -q -m c2   # main now +1

MODE="dry-run"   # notify() emits the intent without touching a tracker
# origin is the active push remote here (single-remote repo). Declare it explicitly
# via ORCH_MAIN_REMOTE so the case is hermetic against an ambient ORCH_MAIN_REMOTE
# in the environment (PILOT-3/ABS-493: the drift check resolves the ACTIVE push
# remote, no longer a hardcoded origin) — mirrors the PILOT-3 override case below.
out="$(ORCH_STATE_ROOT="$DR" ORCH_MAIN_REMOTE=origin ORCH_PROTECT_LOCAL_MAIN=1 check_local_main_drift 2>/dev/null)"
assert_contains "$out" "INTENT LOCAL-MAIN-DRIFT" "drift emits a LOCAL-MAIN-DRIFT intent"
assert_contains "$out" "ahead=1" "drift reports ahead=1"

# In sync -> silent.
git -C "$DR" update-ref refs/remotes/origin/main "$(git -C "$DR" rev-parse main)"
rm -f "$ORCH_STATE_DIR/local-main-drift"
out="$(ORCH_STATE_ROOT="$DR" ORCH_MAIN_REMOTE=origin ORCH_PROTECT_LOCAL_MAIN=1 check_local_main_drift 2>/dev/null)"
assert_not_contains "$out" "LOCAL-MAIN-DRIFT" "in-sync local main -> no drift warning"

# Kill switch silences the drift check.
git -C "$DR" update-ref refs/remotes/origin/main "$BASE"
out="$(ORCH_STATE_ROOT="$DR" ORCH_MAIN_REMOTE=origin ORCH_PROTECT_LOCAL_MAIN=0 check_local_main_drift 2>/dev/null)"
assert_not_contains "$out" "LOCAL-MAIN-DRIFT" "kill switch off -> drift check no-ops (AC4)"

# =============================================================================
echo -e "\n${CYAN}PILOT-3 — drift compares against the ACTIVE push remote, one WARN per run${NC}"
# =============================================================================
# Two remotes: origin is STALE (dead host, cached ref frozen), gitlab is the
# ACTIVE push remote and current. Local main is +2 past stale origin but IN SYNC
# with the active remote -> the guard must be SILENT (the ABS-493 phantom-spam fix).
D2="$TMP/drift2"
git init -q "$D2"; git -C "$D2" symbolic-ref HEAD refs/heads/main
git -C "$D2" config user.email t@t.dev; git -C "$D2" config user.name t
git -C "$D2" config commit.gpgsign false 2>/dev/null || true
git -C "$D2" remote add origin https://bitbucket.invalid/x.git  # dead host (unreachable)
git -C "$D2" remote add gitlab https://gitlab.invalid/x.git     # active fallback host
echo a > "$D2/a"; git -C "$D2" add a; git -C "$D2" commit -q -m c1
C1="$(git -C "$D2" rev-parse main)"
git -C "$D2" update-ref refs/remotes/origin/main "$C1"          # origin frozen at c1 (dead host)
echo b > "$D2/b"; git -C "$D2" add b; git -C "$D2" commit -q -m c2
echo c > "$D2/c"; git -C "$D2" add c; git -C "$D2" commit -q -m c3   # local main now c1+2
C3="$(git -C "$D2" rev-parse main)"
git -C "$D2" update-ref refs/remotes/gitlab/main "$C3"         # active remote is CURRENT
git -C "$D2" config branch.main.remote gitlab                  # push target = the git-host adapter's remote
git -C "$D2" config branch.main.merge refs/heads/main

MODE="dry-run"
rm -f "$ORCH_STATE_DIR/local-main-drift"
out="$(ORCH_STATE_ROOT="$D2" ORCH_PROTECT_LOCAL_MAIN=1 check_local_main_drift 2>/dev/null)"
assert_not_contains "$out" "LOCAL-MAIN-DRIFT" "in sync with ACTIVE remote -> no drift despite stale origin +2 (PILOT-3)"

# Explicit ORCH_MAIN_REMOTE override resolves the same active remote.
rm -f "$ORCH_STATE_DIR/local-main-drift"
out="$(ORCH_STATE_ROOT="$D2" ORCH_MAIN_REMOTE=gitlab ORCH_PROTECT_LOCAL_MAIN=1 check_local_main_drift 2>/dev/null)"
assert_not_contains "$out" "LOCAL-MAIN-DRIFT" "ORCH_MAIN_REMOTE override -> compares vs active remote (PILOT-3)"

# Remove the active remote's freshness: advance local main past gitlab too. Now
# genuinely +1 ahead of the ACTIVE remote (and +3 ahead of stale origin) -> WARN.
echo d > "$D2/d"; git -C "$D2" add d; git -C "$D2" commit -q -m c4
rm -f "$ORCH_STATE_DIR/local-main-drift"
export ORCH_RUN_ID="pilot3-run-1"
out="$(ORCH_STATE_ROOT="$D2" ORCH_PROTECT_LOCAL_MAIN=1 check_local_main_drift 2>/dev/null)"
assert_contains "$out" "INTENT LOCAL-MAIN-DRIFT" "ahead of ACTIVE remote -> WARN fires (PILOT-3)"
assert_contains "$out" "ahead=1" "drift measured vs ACTIVE remote (gitlab, +1), not stale origin (+3) (PILOT-3)"
assert_contains "$out" "remote=gitlab/main" "WARN names the active remote it compared against (PILOT-3)"
# Second sweep in the SAME run -> throttled: exactly one WARN per run, no per-sweep spam.
out2="$(ORCH_STATE_ROOT="$D2" ORCH_PROTECT_LOCAL_MAIN=1 check_local_main_drift 2>/dev/null)"
assert_not_contains "$out2" "LOCAL-MAIN-DRIFT" "same run -> exactly one WARN per run, no per-sweep spam (PILOT-3)"
# A NEW run re-warns once (fresh run id, standing drift is still worth one WARN).
export ORCH_RUN_ID="pilot3-run-2"
out3="$(ORCH_STATE_ROOT="$D2" ORCH_PROTECT_LOCAL_MAIN=1 check_local_main_drift 2>/dev/null)"
assert_contains "$out3" "INTENT LOCAL-MAIN-DRIFT" "a new run re-warns once for a standing drift (PILOT-3)"
unset ORCH_RUN_ID

# =============================================================================
echo -e "\n${CYAN}AC6 — check_claim_protocol warns on a working, un-pulled ticket${NC}"
# =============================================================================
# shellcheck disable=SC2034  # MODE is read by the sourced orchestrator.sh helpers (notify), not locally.
MODE="dry-run"
TCK="ABS-777"
lock="$(lock_dir_for "$TCK")"; mkdir -p "$lock"
# Backdate the lock so its age exceeds the threshold (default 10 min -> 600s).
touch -t 202001010000 "$lock" 2>/dev/null || true
rm -f "$ORCH_STATE_DIR/claim-warn-$TCK"

out="$(ORCH_CLAIM_WARN_MINUTES=10 check_claim_protocol "$TCK" "Ready for Development" 2>/dev/null)"
assert_contains "$out" "INTENT CLAIM-PROTOCOL ticket=$TCK" "aged lock in RfD -> claim-protocol WARN"
# Second sweep in the same episode is throttled (marker present).
out="$(ORCH_CLAIM_WARN_MINUTES=10 check_claim_protocol "$TCK" "Ready for Development" 2>/dev/null)"
assert_not_contains "$out" "INTENT CLAIM-PROTOCOL" "same episode -> throttled to one WARN"

# A different status clears the episode (no warn, marker removed).
out="$(ORCH_CLAIM_WARN_MINUTES=10 check_claim_protocol "$TCK" "In Progress" 2>/dev/null)"
assert_not_contains "$out" "CLAIM-PROTOCOL" "status moved to In Progress -> no warn, episode cleared"
assert_eq "$([ -f "$ORCH_STATE_DIR/claim-warn-$TCK" ] && echo yes || echo no)" "no" "episode marker cleared when status changes"

# No lock -> never warns.
release_lock "$TCK" 2>/dev/null || rm -rf "$lock"
out="$(ORCH_CLAIM_WARN_MINUTES=10 check_claim_protocol "$TCK" "Ready for Development" 2>/dev/null)"
assert_not_contains "$out" "CLAIM-PROTOCOL" "no active lock -> no claim warning"

# Kill switch (minutes=0) disables the check.
mkdir -p "$lock"; touch -t 202001010000 "$lock" 2>/dev/null || true; rm -f "$ORCH_STATE_DIR/claim-warn-$TCK"
out="$(ORCH_CLAIM_WARN_MINUTES=0 check_claim_protocol "$TCK" "Ready for Development" 2>/dev/null)"
assert_not_contains "$out" "CLAIM-PROTOCOL" "ORCH_CLAIM_WARN_MINUTES=0 -> claim check disabled (AC4)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
