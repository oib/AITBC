#!/bin/bash
# =============================================================================
# Test: every tests/fixtures/ file on disk is tracked in the index (ABS-280)
# =============================================================================
# Regression guard for the ABS-218 class: a NEW fixture is added under
# tests/fixtures/, a .gitignore pattern silently swallows it, and the commit
# ships without it. The author's local run stays GREEN (the file is on disk);
# only a clean checkout is red. ABS-218 was approved 28/28 from a working tree
# and the defect surfaced at PO Story Acceptance, costing a full rework
# iteration (docs/agent-outputs/qa-validations/ABS-218-qa-validation.md).
#
# Three live patterns can still swallow a fixture today:
#   .gitignore:52  *.log     .gitignore:91  *.tmp     .gitignore:33  .env
# The precedent fix is a targeted negation, as .gitignore:58-59 already does
# for tests/fixtures/skill-mining/state/run.log (the skill-mining miner's
# source #2 — deleting it fails 3 assertions in tests/test-skill-mining.sh).
#
# We guard the CLASS (any fixture on disk that is not in the index), not the
# FILE: the trigger is a fixture ADD, so a file-specific assertion would not
# have caught ABS-218 itself.
#
# Coverage:
#   AC1  every file on disk under tests/fixtures/ is listed by git ls-files;
#        on violation this exits non-zero and prints each offending path.
#   AC2  both sides of the boundary: a tracked fixture passes, AND a scratch
#        file matching an ignored pattern makes the guard fire (so it cannot
#        go inert).
#   AC3  the failure message names the cause and the fix.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-fixture-integrity.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FIXTURE_DIR="tests/fixtures"

cd "$REPO_ROOT" || exit 1
# This entrypoint mentions the shipper (in the trap-hygiene note below), so the
# mechanical sandbox-guard-check requires it to source the guard. Harmless here
# (nothing is executed against the backend) — it only strips inherited env.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}

# -----------------------------------------------------------------------------
# THE GUARD. `git ls-files --others` lists files on disk that are NOT in the
# index. We deliberately do NOT pass --exclude-standard: the ignored files are
# precisely the ones we are hunting. Empty output == every fixture is tracked.
# -----------------------------------------------------------------------------
untracked_fixtures() {
    git ls-files --others -- "$FIXTURE_DIR" 2>/dev/null
}

# Exit-code face of the same guard: 0 == clean, 1 == a fixture is unindexed.
# This is what AC1's "exits non-zero" means, and what CI keys off.
guard_status() {
    [ -z "$(untracked_fixtures)" ]
}

# The scratch probe for AC2. It matches .gitignore:52 (*.log), so git hides it
# from a normal `git status` — the exact blind spot. Removed on ANY exit, so a
# failing run cannot poison the next one (or a later suite).
PROBE="$FIXTURE_DIR/.abs280-guard-probe.log"
cleanup() { rm -f "$REPO_ROOT/$PROBE"; }
# PILOT-60: keep EXIT (cleanup only) and INT/TERM (cleanup THEN exit) as SEPARATE
# traps. A combined `trap cleanup EXIT INT TERM` whose handler only returns lets
# bash resume after a signal instead of terminating — the exact trap-defect class
# this ticket audits (a returning signal handler swallowed SIGTERM in the shipper).
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

echo -e "${CYAN}=== tests/fixtures/ index integrity (ABS-280) ===${NC}\n"

# -----------------------------------------------------------------------------
echo -e "${CYAN}--- AC1/AC5: every fixture on disk is in the index ---${NC}"
# -----------------------------------------------------------------------------
cleanup  # never measure the real tree with our own probe lying in it

ON_DISK="$(find "$FIXTURE_DIR" -type f | wc -l | tr -d ' ')"
TRACKED="$(git ls-files -- "$FIXTURE_DIR" | wc -l | tr -d ' ')"
OFFENDERS="$(untracked_fixtures)"

TOTAL=$((TOTAL + 1))
if [ -z "$OFFENDERS" ]; then
    echo -e "  ${GREEN}PASS${NC} all $ON_DISK fixture files on disk are tracked ($TRACKED in index)"
    PASS=$((PASS + 1))
else
    # AC3: name the cause and the fix, so the next dev does not re-diagnose
    # this from three unrelated assertion failures in another suite.
    echo -e "  ${RED}FAIL${NC} fixture files exist on disk but are NOT in the index:"
    echo "$OFFENDERS" | sed 's/^/      /'
    echo -e "  ${YELLOW}  Cause: a .gitignore pattern is swallowing them. Which one:${NC}"
    echo "$OFFENDERS" | while IFS= read -r f; do
        [ -n "$f" ] && git check-ignore -v --no-index "$f" 2>/dev/null | sed 's/^/        /'
    done
    echo -e "  ${YELLOW}  Effect: your local run is GREEN (the file is on disk) but a clean${NC}"
    echo -e "  ${YELLOW}          checkout is RED — the file never reaches CI or a reviewer.${NC}"
    echo -e "  ${YELLOW}  Fix:    add a targeted negation to .gitignore, as .gitignore:58-59${NC}"
    echo -e "  ${YELLOW}          already does for run.log:  !$FIXTURE_DIR/<path>${NC}"
    echo -e "  ${YELLOW}          then: git add -f <path> && git commit${NC}"
    FAIL=$((FAIL + 1))
fi

# On-disk and index counts must agree (catches the inverse too: an index entry
# whose file was deleted on disk).
assert_eq "$ON_DISK" "$TRACKED" "on-disk count matches index count"

# -----------------------------------------------------------------------------
echo -e "\n${CYAN}--- AC2: the guard fires (it cannot go inert) ---${NC}"
# -----------------------------------------------------------------------------
# Negative side: plant a fixture that an ignore pattern swallows. If the guard
# is ever weakened (e.g. someone adds --exclude-standard), this assertion goes
# red instead of the guard going quietly blind.
: > "$PROBE"

assert_eq "$(git check-ignore -q "$PROBE" && echo ignored || echo visible)" "ignored" \
    "the probe is genuinely .gitignore'd (reproduces the ABS-218 blind spot)"

assert_eq "$(untracked_fixtures | grep -cFx -- "$PROBE" | tr -d ' ')" "1" \
    "guard detects the swallowed fixture"

assert_eq "$(guard_status && echo 0 || echo nonzero)" "nonzero" \
    "guard exits non-zero while the probe is present (AC1)"

# Positive side: a tracked fixture must NOT be reported. Without this, a guard
# that flags everything would also "pass" the negative side above. Anchored to
# the exact path: a substring match ("state/run.log") also matches a DIFFERENT,
# untracked fixture of the same basename, which is exactly the case we flag.
TRACKED_FIXTURE="$FIXTURE_DIR/skill-mining/state/run.log"
assert_eq "$(git ls-files --error-unmatch -- "$TRACKED_FIXTURE" >/dev/null 2>&1 && echo tracked || echo missing)" "tracked" \
    "the run.log fixture is in the index (the .gitignore:58-59 negation still holds)"

assert_eq "$(untracked_fixtures | grep -cFx -- "$TRACKED_FIXTURE" | tr -d ' ')" "0" \
    "guard does not flag that already-tracked fixture"

cleanup

assert_eq "$(guard_status && echo 0 || echo nonzero)" "0" \
    "guard exits 0 again once the probe is removed (no residue)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
