#!/bin/bash
# =============================================================================
# Test: Improvement-Proposal Change-Contract Lint (ABS-521 / epic ABS-514)
# =============================================================================
# Pins scripts/proposal-contract-lint.sh: post-cutoff proposals without the
# Invariants Preserved / Falsifying Eval / Rollback sections go RED; the
# grandfathered pre-cutoff corpus stays GREEN. Auto-discovered by the CI /
# pre-release tests/test-*.sh loops.
#
# Run from repo root: bash tests/tooling/test-proposal-contract-lint.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LINT="$REPO_ROOT/scripts/proposal-contract-lint.sh"

PASS=0
FAIL=0
TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_exit() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== Proposal change-contract lint (ABS-521) ===${NC}\n"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/proposal-lint-test-XXXXXX")
trap 'rm -rf "$TMP"' EXIT

full_contract() {
cat <<'EOF'
# Fixture proposal

## Rationale
x
## Suggested Boilerplate Change
x
## Impact
x
## Invariants Preserved
x
## Falsifying Eval
tests/test-fixture.sh
## Rollback
revert
EOF
}

# --- real corpus: grandfathered proposals stay green ---------------------------
echo -e "${CYAN}Real corpus (grandfathered)${NC}"
ec=0; bash "$LINT" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 0 "existing work/improvement-proposals corpus passes (grandfathered)"

# --- post-cutoff WITH contract -> green ----------------------------------------
echo -e "\n${CYAN}Post-cutoff with contract${NC}"
mkdir -p "$TMP/props"
full_contract > "$TMP/props/2026-08-01-good.md"
ec=0; PROPOSAL_DIR="$TMP/props" bash "$LINT" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 0 "post-cutoff proposal with full contract passes"

# --- post-cutoff MISSING Falsifying Eval -> red --------------------------------
echo -e "\n${CYAN}Post-cutoff missing sections${NC}"
full_contract | grep -v -e '^## Falsifying Eval' -e '^tests/test-fixture.sh' > "$TMP/props/2026-08-02-bad.md"
ec=0; PROPOSAL_DIR="$TMP/props" bash "$LINT" >/dev/null 2>"$TMP/err" || ec=$?
assert_exit "$ec" 1 "post-cutoff proposal without Falsifying Eval fails"
TOTAL=$((TOTAL + 1))
if grep -q 'Falsifying Eval' "$TMP/err"; then
    echo -e "  ${GREEN}PASS${NC} names the missing section"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} names the missing section"; FAIL=$((FAIL + 1))
fi

# --- pre-cutoff without contract -> green (grandfathered) ----------------------
echo -e "\n${CYAN}Pre-cutoff grandfathering${NC}"
rm -f "$TMP/props/2026-08-02-bad.md"
printf '# Old\n\n## Rationale\nx\n' > "$TMP/props/2026-07-01-legacy.md"
ec=0; PROPOSAL_DIR="$TMP/props" bash "$LINT" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 0 "pre-cutoff proposal without contract stays green"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
