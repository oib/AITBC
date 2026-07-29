#!/bin/bash
# =============================================================================
# Test: parallel-branch id allocation is collision-free (ABS-600)
# =============================================================================
# THE FALSIFIER for ABS-600 AC3. The Pilot-8 defect was NOT a bad duplicate
# check — the check worked, it just fired too late. So a test that only asserts
# "the duplicate check catches a duplicate" would miss the point. This test
# instead reproduces the PARALLEL case at the source:
#
#   two branches, starting from the SAME base ledger, each allocate rule ids
#   INDEPENDENTLY (no knowledge of each other), then integrate onto one branch.
#
# It asserts:
#   1. TICKET-SCOPED scheme (scripts/next-rule-ledger-id.sh): after integration
#      there is NO collision — collision-free by construction. This is the pass
#      the ticket demands (a result-only duplicate check does not satisfy AC3).
#   2. The OLD running-counter scheme (both branches take max+1) DOES collide,
#      and the retained backstop (rule-ledger-check.sh C1) catches it AND now
#      names the file+heading of each colliding row (AC4 + AC5). This proves the
#      test bites and that removing the fix would go red.
#
# bash 3.2 + BSD tools only. Run from repo root:
#   bash tests/test-registry-id-parallel.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD="$REPO_ROOT/scripts/rule-ledger-check.sh"
ALLOC="$REPO_ROOT/scripts/next-rule-ledger-id.sh"

PASS=0; FAIL=0; TOTAL=0
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
assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1))
    fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== Parallel-branch id allocation (ABS-600) ===${NC}\n"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/registry-id-test-XXXXXX")
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/root/docs"

# One informative row per heading keeps the fixture minimal: informative needs
# no sensors (C2) and no risk (C3), so the test isolates C1 (id shape/uniqueness).
row() { printf '  - id: %s\n    file: docs/RULES.md\n    heading: "%s"\n    kind: informative\n' "$1" "$2"; }

# Build a ledger from a list of "id|heading" pairs, plus the matching md file so
# C4 (heading<->row, both directions) stays green and only C1 is under test.
build() { # build <ledger-path> <pair> ...
    local ledger="$1"; shift
    { echo "scope_dirs:"; echo "  - docs"; echo "scope:"; echo "  - docs/RULES.md"; echo "rules:"; } > "$ledger"
    : > "$TMP/root/docs/RULES.md"
    echo "# Rules" >> "$TMP/root/docs/RULES.md"
    local pair id heading
    for pair in "$@"; do
        id="${pair%%|*}"; heading="${pair#*|}"
        row "$id" "$heading" >> "$ledger"
        printf '\n## %s\n\nbody\n' "$heading" >> "$TMP/root/docs/RULES.md"
    done
}

run_guard() { # run_guard <ledger> -> echoes exit code, stderr to $TMP/err
    local ec=0
    RULE_LEDGER_FILE="$1" RULE_LEDGER_ROOT="$TMP/root" \
        RULE_LEDGER_REQUIRED_SCOPE="docs/RULES.md" \
        bash "$GUARD" >/dev/null 2>"$TMP/err" || ec=$?
    echo "$ec"
}

# --- The base both branches fork from -----------------------------------------
# A "branch" here is just a ledger file that starts as a copy of base; each
# branch calls the allocator against ITS OWN copy, exactly as a seat would.
build "$TMP/base.yaml" "R-0001|Base Rule"

# ============================================================================
# 1. TICKET-SCOPED SCHEME — collision-free by construction
# ============================================================================
echo -e "${CYAN}Ticket-scoped allocation (the fix)${NC}"
cp "$TMP/base.yaml" "$TMP/branchA.yaml"
cp "$TMP/base.yaml" "$TMP/branchB.yaml"

# Branch A, ticket ABS-595: allocates two ids, each time reading only its own copy.
a1="$(bash "$ALLOC" ABS-595 "$TMP/branchA.yaml")"; row "$a1" "Rule A1" >> "$TMP/branchA.yaml"
a2="$(bash "$ALLOC" ABS-595 "$TMP/branchA.yaml")"; row "$a2" "Rule A2" >> "$TMP/branchA.yaml"
# Branch B, ticket ABS-596: allocates independently, no knowledge of branch A.
b1="$(bash "$ALLOC" ABS-596 "$TMP/branchB.yaml")"; row "$b1" "Rule B1" >> "$TMP/branchB.yaml"

assert_eq "$a1 $a2 $b1" "R-ABS-595-1 R-ABS-595-2 R-ABS-596-1" "ids derive from the ticket, not a shared counter"

# Integrate: base + both branches' NEW rows onto one ledger, with matching md.
build "$TMP/merged.yaml" \
    "R-0001|Base Rule" "$a1|Rule A1" "$a2|Rule A2" "$b1|Rule B1"
assert_exit "$(run_guard "$TMP/merged.yaml")" 0 "parallel allocation integrates with NO collision (AC3)"

# ============================================================================
# 2. OLD RUNNING-COUNTER SCHEME — collides; backstop catches + locates it
# ============================================================================
echo -e "\n${CYAN}Running-counter allocation (what we replaced) — proves the backstop${NC}"
# Both branches independently read base max (R-0001) and take +1 -> both R-0002.
build "$TMP/collide.yaml" \
    "R-0001|Base Rule" "R-0002|Rule A1" "R-0002|Rule B1"
assert_exit "$(run_guard "$TMP/collide.yaml")" 1 "duplicate running-counter id -> exit 1 (AC4 backstop)"
assert_contains "$(cat "$TMP/err")" "duplicate rule ids: R-0002" "backstop names the colliding id"
assert_contains "$(cat "$TMP/err")" "Rule A1" "backstop names the first occurrence's heading (AC5)"
assert_contains "$(cat "$TMP/err")" "Rule B1" "backstop names the second occurrence's heading (AC5)"
assert_contains "$(cat "$TMP/err")" "docs/RULES.md" "backstop names the source file (AC5)"

# --- results ------------------------------------------------------------------
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1; fi
echo -e "  ${GREEN}ALL PASS${NC}"
