#!/bin/bash
# =============================================================================
# Test: the ticket-tag convention is mechanical, and the RTE bisect recovers
# (PILOT-79)
# =============================================================================
# Proves the guard that closes the Pilot-7 Befund: the `[PREFIX-XXX]` tag was a
# documented REQUIREMENT with no enforcement, and an untagged culprit crashes the
# epic into the dead-end `Needs PO Decision`. Coverage:
#
#   AC1  scripts/commit-tag-guard.sh classifies a story commit: a tagged commit
#        passes, an untagged story commit fails; the commit-msg hook aborts an
#        untagged SEAT commit on a story branch, end-to-end via a real git commit.
#   AC2  the operator/release EXEMPT class is honoured: a `chore(release):` commit
#        and a `[no-ticket]`-marked commit both PASS (never falsely blocked).
#   AC3  the hook fires on a STORY branch (guarded) but NOT on main/master or an
#        epic/* branch (operator/RTE territory).
#   AC4  regression, both cases: tagged story commit PASSES, untagged story commit
#        FAILS, release commit PASSES — via the installed real commit-msg hook.
#        The kill switch (ORCH_TICKET_TAG_GUARD=0) disables the guard.
#   AC5  `recover` resolves an untagged culprit to its story (next-tagged commit or
#        enclosing merge) instead of Needs PO Decision; a truly untagged range is
#        reported `unresolved` (exit 3) — the last resort, not the first.
#
# The installer (provision_ticket_tag_guard) is exercised by SOURCING
# scripts/orchestrator.sh (main is source-guarded). bash 3.2 + BSD tools only.
# Run from repo root: bash tests/tooling/test-commit-tag-guard.sh
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/commit-tag-guard.sh"
HOOK="$REPO_ROOT/scripts/hooks/commit-msg-ticket-tag-guard.sh"

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

TMP="$(mktemp -d /tmp/ctg-XXXXXX)"
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

# --- helper: write a message file and classify it via check-msg. -------------
verdict_msg() {  # $1 = message text
    printf '%s\n' "$1" > "$TMP/msg"
    bash "$GUARD" check-msg "$TMP/msg" 2>/dev/null
}
rc_of() { "$@" >/dev/null 2>&1; printf '%s' "$?"; }

# =============================================================================
echo -e "${CYAN}=== ticket-tag convention is mechanical (PILOT-79) ===${NC}\n"
echo -e "${CYAN}AC1/AC2 — classifier verdicts (check-msg)${NC}"
# =============================================================================
assert_eq "$(verdict_msg 'feat(api): add webhook [PILOT-79]')"          "tagged PILOT-79"  "tagged story commit -> tagged"
assert_eq "$(verdict_msg 'fix(auth): resolve redirect [ABS-591]')"      "tagged ABS-591"   "tagged (other prefix) -> tagged"
assert_eq "$(verdict_msg 'docs(sop): update worktree section for PILOT-66')" "untagged"    "ticket in PROSE only -> untagged (the 4d70ec09 bug)"
assert_eq "$(verdict_msg 'add a thing without any reference')"          "untagged"         "no reference at all -> untagged"
assert_eq "$(verdict_msg 'chore(release): promote governor to v2.32.0')" "exempt release-automation" "release commit -> exempt (AC2)"
assert_eq "$(verdict_msg 'docs: changelog note [no-ticket]')"          "exempt no-ticket-marker"    "[no-ticket] marker -> exempt (AC2)"
assert_eq "$(rc_of bash "$GUARD" check-msg "$TMP/should-not-exist")"    "64"               "missing message file -> usage error (exit 64)"

# =============================================================================
echo -e "\n${CYAN}AC3 — the commit-msg hook fires only on story branches (for seats)${NC}"
# =============================================================================
run_hook() {  # $1 = branch, then env assignments; writes a fixed untagged msg
    local branch="$1"; shift
    printf '%s\n' "untagged story work" > "$TMP/hookmsg"
    local rc=0
    ( cd "$REPO_ROOT" && env -u ORCH_SEAT -u ORCH_ROLE -u ORCH_TICKET \
        ORCH_GUARD_BRANCH="$branch" "$@" bash "$HOOK" "$TMP/hookmsg" ) >/dev/null 2>&1 || rc=$?
    printf '%s' "$rc"
}
assert_eq "$(run_hook PILOT-79-auto ORCH_SEAT=be-developer)" "1" "seat, untagged, story branch -> BLOCKED"
assert_eq "$(run_hook main ORCH_SEAT=be-developer)"          "0" "seat on main -> allowed (release territory)"
assert_eq "$(run_hook master ORCH_SEAT=be-developer)"        "0" "seat on master -> allowed"
assert_eq "$(run_hook epic/PILOT-71-x ORCH_SEAT=rte)"        "0" "seat on epic/* -> allowed (integration territory)"
assert_eq "$(run_hook PILOT-79-auto)"                        "0" "HUMAN (no seat env) on story branch -> allowed"
assert_eq "$(run_hook PILOT-79-auto ORCH_SEAT=be-developer ORCH_TICKET_TAG_GUARD=0)" "0" "kill switch off -> allowed (AC4)"

# =============================================================================
echo -e "\n${CYAN}AC4 — end-to-end via the INSTALLED real commit-msg hook${NC}"
# =============================================================================
export ORCH_STATE_DIR="$TMP/state"; mkdir -p "$ORCH_STATE_DIR/locks"
# shellcheck disable=SC1090
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1
# orchestrator.sh runs `set -euo pipefail`; this test drives exit codes explicitly
# (rc capture, expected non-zero verdicts), so restore its own flags.
set +e +o pipefail; set -u
unset ORCH_SEAT ORCH_ROLE ORCH_TICKET ORCH_GUARD_BRANCH 2>/dev/null || true

REPO="$TMP/repo"
git init -q "$REPO" 2>/dev/null || { mkdir -p "$REPO"; git -C "$REPO" init -q; }
git -C "$REPO" config user.email t@t.dev; git -C "$REPO" config user.name t
git -C "$REPO" config commit.gpgsign false 2>/dev/null || true

# The installed commit-msg hook resolves the classifier from the checkout's own
# scripts/ (in production that is the boilerplate checkout). Seed it so the e2e
# reflects reality rather than the fail-open no-classifier branch.
mkdir -p "$REPO/scripts"; cp "$GUARD" "$REPO/scripts/commit-tag-guard.sh"

MODE="live"
ORCH_STATE_ROOT="$REPO" ORCH_TICKET_TAG_GUARD=1 provision_ticket_tag_guard >/dev/null 2>&1
assert_eq "$([ -x "$REPO/.git/hooks/commit-msg" ] && echo yes || echo no)" "yes" "installer wrote an executable commit-msg hook"
assert_contains "$(cat "$REPO/.git/hooks/commit-msg")" "PILOT-79-ticket-tag-guard" "installed hook carries the guard marker"

# On a story branch, a seat commit.
git -C "$REPO" checkout -q -b PILOT-79-auto
echo a > "$REPO/a"; git -C "$REPO" add a
rc=0; ( cd "$REPO" && ORCH_SEAT=be-developer git commit -q -m "feat(api): tagged work [PILOT-79]" ) >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "tagged story commit PASSES (AC4)"

echo b > "$REPO/b"; git -C "$REPO" add b
rc=0; ( cd "$REPO" && ORCH_SEAT=be-developer git commit -q -m "feat(api): untagged work" ) >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "untagged story commit FAILS (AC4)"

echo c > "$REPO/c"; git -C "$REPO" add c
rc=0; ( cd "$REPO" && ORCH_SEAT=be-developer git commit -q -m "chore(release): promote governor to v9.9.9" ) >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "release commit PASSES on a story branch (AC2/AC4)"

# =============================================================================
echo -e "\n${CYAN}AC5 — RTE bisect recovery instead of Needs PO Decision${NC}"
# =============================================================================
RR="$TMP/recover"
git init -q "$RR"; git -C "$RR" config user.email t@t.dev; git -C "$RR" config user.name t
git -C "$RR" config commit.gpgsign false 2>/dev/null || true
_c() { echo "$1" > "$RR/$1"; git -C "$RR" add "$1"; git -C "$RR" commit -q -m "$2"; }
_c good   "feat: base [PILOT-90]"
good="$(git -C "$RR" rev-parse HEAD)"
_c bad1   "docs: worktree note for PILOT-91"          # untagged culprit (prose only)
culprit="$(git -C "$RR" rev-parse HEAD)"
_c bad2   "feat: more of the same story [PILOT-91]"   # next tagged commit
_c bad3   "test: coverage [PILOT-92]"
bad="$(git -C "$RR" rev-parse HEAD)"

out="$(cd "$RR" && bash "$GUARD" recover "$good..$bad" "$culprit" 2>/dev/null)"; rc=$?
assert_eq "$rc" "0" "recover resolves an untagged culprit (exit 0)"
assert_contains "$out" "child=PILOT-91" "recover maps culprit to the next tagged story PILOT-91"
assert_contains "$out" "via=next-tagged" "recover reports the resolution path"

# A range where NOTHING carries a tag after the culprit -> unresolved (exit 3).
UU="$TMP/unresolved"
git init -q "$UU"; git -C "$UU" config user.email t@t.dev; git -C "$UU" config user.name t
git -C "$UU" config commit.gpgsign false 2>/dev/null || true
echo g > "$UU/g"; git -C "$UU" add g; git -C "$UU" commit -q -m "feat: base [PILOT-90]"
ug="$(git -C "$UU" rev-parse HEAD)"
echo u > "$UU/u"; git -C "$UU" add u; git -C "$UU" commit -q -m "docs: untagged tail commit"
uc="$(git -C "$UU" rev-parse HEAD)"
out="$(cd "$UU" && bash "$GUARD" recover "$ug..$uc" "$uc" 2>/dev/null)"; rc=$?
assert_eq "$rc" "3" "wholly-untagged range -> unresolved (exit 3, last resort)"
assert_contains "$out" "unresolved" "recover prints 'unresolved'"

# check-range flags the untagged culprit and passes when all are tagged/exempt.
assert_eq "$(cd "$RR" && rc_of bash "$GUARD" check-range "$good..$bad")" "1" "check-range fails a range with an untagged commit"
assert_eq "$(cd "$RR" && rc_of bash "$GUARD" check-range "$good..$good")" "0" "check-range passes an empty range"

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}"
echo
[ "$FAIL" -eq 0 ] && { echo -e "${GREEN}ALL PASS${NC}"; exit 0; } || { echo -e "${RED}SOME FAILED${NC}"; exit 1; }
