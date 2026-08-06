#!/usr/bin/env bash
# =============================================================================
# Test: degraded merge-base rebase-gate for the jira/mock profile (ABS-398)
# =============================================================================
# The v3-native profile enforces the rebase-gate in the backend transition guard
# off a computed `merge_readiness` (ABS-397). The jira/mock profile has no
# computed field, so scripts/rebase-gate-check.sh lets the QAS/PO seat reach the
# SAME accept/reject outcome with git only. This suite builds a real throwaway
# git repo and pins that equivalence for the three native-gate cases:
#   clean -> ACCEPT ; rebase-needed (no doc) -> REJECT ; rebase-needed + doc -> ACCEPT.
#
# Self-contained (own mktemp git repo, no fixed paths). bash 3.2 + BSD tools.
# Run from repo root: bash tests/test-rebase-gate-check.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$REPO_ROOT/scripts/rebase-gate-check.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Run the gate script and assert its EXIT CODE (the contract is the exit code).
assert_rc() {
    local expected="$1" label="$2"; shift 2
    local rc=0
    "$@" >/dev/null 2>&1 || rc=$?
    TOTAL=$((TOTAL + 1))
    if [ "$rc" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected exit '$expected', got '$rc')"; FAIL=$((FAIL + 1)); fi
}

TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rebase-gate-XXXXXX")"
cleanup() { rm -rf "$TEST_DIR"; }
trap cleanup EXIT

echo -e "${CYAN}=== degraded rebase-gate (jira/mock, ABS-398) ===${NC}\n"

# --- build a throwaway repo: epic branch + two story branches off it ----------
cd "$TEST_DIR"
git init -q .
git config user.email t@t.t; git config user.name t; git config commit.gpgsign false
git checkout -q -b "epic/ABS-000-integration"
echo base > f.txt; git add f.txt; git commit -qm base            # epic tip @ base
# stale-story forks from the OLD tip, then the epic advances past it.
git checkout -q -b stale-story
echo s2 > s2.txt; git add s2.txt; git commit -qm stale-story-work
git checkout -q "epic/ABS-000-integration"
echo more >> f.txt; git add f.txt; git commit -qm epic-advances  # tip moves past stale-story
# clean-story forks from the CURRENT (advanced) tip -> already contains it.
git checkout -q -b clean-story
echo s > s.txt; git add s.txt; git commit -qm story-work
EPIC="epic/ABS-000-integration"

# =============================================================================
echo -e "${CYAN}A. readiness — clean vs rebase-needed via git merge-base (AC1)${NC}"
# =============================================================================
assert_rc 0 "clean story (contains the epic tip) -> readiness exit 0 (clean)" \
    bash "$GATE" readiness "$EPIC" clean-story
assert_rc 1 "stale story (epic advanced past it) -> readiness exit 1 (rebase-needed)" \
    bash "$GATE" readiness "$EPIC" stale-story

# =============================================================================
echo -e "\n${CYAN}B. gate — same accept/reject outcome as the native guard (AC3)${NC}"
# =============================================================================
# Case 1: clean -> ACCEPT (matches native 'clean passes through unchanged').
assert_rc 0 "clean -> gate ACCEPT (exit 0)" \
    bash "$GATE" gate "$EPIC" clean-story "accepted"
# Case 2: rebase-needed + NO documented rebase -> REJECT (native rejects).
assert_rc 1 "rebase-needed + no documented rebase -> gate REJECT (exit 1)" \
    bash "$GATE" gate "$EPIC" stale-story "looks good to me"
# Case 3: rebase-needed + documented rebase in the same move -> ACCEPT
#         (native forces/accepts a documented rebase; word 'rebased' is the token).
assert_rc 0 "rebase-needed + 'rebased' in the reason -> gate ACCEPT (exit 0)" \
    bash "$GATE" gate "$EPIC" stale-story "rebased onto the epic tip, clean"

# =============================================================================
echo -e "\n${CYAN}C. bad input fails closed${NC}"
# =============================================================================
assert_rc 64 "unknown epic ref -> exit 64 (fails closed, not a false clean)" \
    bash "$GATE" readiness no-such-branch clean-story
assert_rc 64 "missing args -> exit 64" \
    bash "$GATE" gate "$EPIC"

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  Failed: 0"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}All rebase-gate-check tests passed.${NC}"
