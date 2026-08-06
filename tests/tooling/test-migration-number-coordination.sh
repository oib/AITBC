#!/usr/bin/env bash
# =============================================================================
# Test: migration-number coordination at assignment/pre-merge time (ABS-449)
# =============================================================================
# ABS-428 catches a duplicate migration prefix at run/merge time — after the
# add/add conflict and Epic-Sync re-numbering are already paid. This suite pins
# the two front-loaded pieces:
#   A. scripts/next-migration-number.sh  — the next free number as the union of
#      main + the working tree + any --target ref (AC2).
#   B. scripts/migration-number-collision-check.sh — a merge-base gate that goes
#      RED before merge when two branches add the same number, naming the number
#      and the colliding files (AC1). Same family as the ABS-397/398 rebase-gate.
#
# Self-contained (own mktemp git repo, no fixed paths). bash 3.2 + BSD tools.
# Run from repo root: bash tests/tooling/test-migration-number-coordination.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NEXT="$REPO_ROOT/scripts/next-migration-number.sh"
GATE="$REPO_ROOT/scripts/migration-number-collision-check.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Assert the script's EXIT CODE (the gate's contract is its exit code).
assert_rc() {
    local expected="$1" label="$2"; shift 2
    local rc=0
    "$@" >/dev/null 2>&1 || rc=$?
    TOTAL=$((TOTAL + 1))
    if [ "$rc" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected exit '$expected', got '$rc')"; FAIL=$((FAIL + 1)); fi
}

# Assert stdout equals an expected string.
assert_out() {
    local expected="$1" label="$2"; shift 2
    local out; out="$("$@" 2>/dev/null)"
    TOTAL=$((TOTAL + 1))
    if [ "$out" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$out')"; FAIL=$((FAIL + 1)); fi
}

TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mig-coord-XXXXXX")"
cleanup() { rm -rf "$TEST_DIR"; }
trap cleanup EXIT

MDIR="migrations"   # short dir, passed via --dir; avoids the real backend path

add_mig() { mkdir -p "$MDIR"; echo "-- $1" > "$MDIR/$1"; git add "$MDIR/$1"; }

echo -e "${CYAN}=== migration-number coordination (ABS-449) ===${NC}\n"

# --- build a throwaway repo -------------------------------------------------
cd "$TEST_DIR"
git init -q .
git config user.email t@t.t; git config user.name t; git config commit.gpgsign false
git checkout -q -b main
# BASE series 001..009 (the common history for the collision cases).
i=1; while [ "$i" -le 9 ]; do add_mig "00${i}_m${i}.sql"; i=$((i + 1)); done
git commit -qm "base 001..009"
BASE_SHA="$(git rev-parse HEAD)"
# main advances to 010 (a merged migration).
add_mig "010_command_reason.sql"; git commit -qm "main adds 010"

# =============================================================================
echo -e "${CYAN}A. next-migration-number.sh — next free number (AC2)${NC}"
# =============================================================================
assert_out "011" "main tops out at 010 -> next free is 011" \
    bash "$NEXT" --dir "$MDIR"

# A target epic branch that already reserved 011 must push the answer to 012.
git checkout -q -b epic/ABS-000-integration main
add_mig "011_epic_thing.sql"; git commit -qm "epic reserves 011"
git checkout -q main
assert_out "012" "--target epic (holds 011) -> next free is 012" \
    bash "$NEXT" --dir "$MDIR" --target epic/ABS-000-integration
assert_out "011" "without the target, epic's 011 is not counted -> still 011" \
    bash "$NEXT" --dir "$MDIR"

# =============================================================================
echo -e "\n${CYAN}B. collision-check — RED before merge on a double-add (AC1)${NC}"
# =============================================================================
# Two branches fork the SAME base (001..009), each adds 010 independently.
git checkout -q -b branchA "$BASE_SHA"
add_mig "010_first.sql"; git commit -qm "branchA adds 010_first"
git checkout -q -b epicTarget "$BASE_SHA"
add_mig "010_second.sql"; git commit -qm "epicTarget adds 010_second"

assert_rc 1 "same number (010) added on both sides -> COLLISION (exit 1)" \
    bash "$GATE" epicTarget branchA --dir "$MDIR"

# The add/add case from MR !94: identical filename on both sides, off a base
# that lacks it -> still a collision (merge-base sees it added twice).
git checkout -q -b branchB "$BASE_SHA"
add_mig "010_command_reason.sql"; git commit -qm "branchB adds 010_command_reason"
git checkout -q -b epicTarget2 "$BASE_SHA"
add_mig "010_command_reason.sql"; git commit -qm "epicTarget2 adds 010_command_reason"
assert_rc 1 "identical filename added on both sides -> COLLISION (exit 1)" \
    bash "$GATE" epicTarget2 branchB --dir "$MDIR"

# Message names the number and the colliding file (AC1 wording).
MSG="$(bash "$GATE" epicTarget branchA --dir "$MDIR" 2>&1 || true)"
TOTAL=$((TOTAL + 1))
if printf '%s' "$MSG" | grep -q "010" && printf '%s' "$MSG" | grep -q "010_first.sql"; then
    echo -e "  ${GREEN}PASS${NC} error names the number (010) and the colliding file"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} error should name number + file; got: $MSG"; FAIL=$((FAIL + 1))
fi

# Clean case: a branch that simply continues the series off the target is fine.
git checkout -q -b branchC epicTarget
add_mig "011_next.sql"; git commit -qm "branchC continues with 011"
assert_rc 0 "branch continues the series (011 off target) -> OK (exit 0)" \
    bash "$GATE" epicTarget branchC --dir "$MDIR"

# =============================================================================
echo -e "\n${CYAN}C. bad input fails closed${NC}"
# =============================================================================
assert_rc 64 "unknown target ref -> exit 64 (not a false OK)" \
    bash "$GATE" no-such-branch branchA --dir "$MDIR"
assert_rc 64 "missing target arg (flag only) -> exit 64" \
    bash "$GATE" --dir "$MDIR"
assert_rc 64 "next-migration-number: unknown flag -> exit 64" \
    bash "$NEXT" --bogus

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  Failed: 0"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}All migration-number coordination tests passed.${NC}"
