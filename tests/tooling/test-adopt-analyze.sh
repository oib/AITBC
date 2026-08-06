#!/bin/bash
# =============================================================================
# Test: Existing-Project Adoption Analyzer (blueprint §8)
# =============================================================================
# Runs scripts/adopt-analyze.sh against the fixture at
# tests/fixtures/adoption/sample-project and asserts:
#   - the report detects the Node.js stack, the CI workflow file, and the
#     Jira reference
#   - the report flags the pre-existing CLAUDE.md as a harness conflict
#   - the report contains the human-approval line (ADR-A-0004)
#   - the target fixture tree is byte-for-byte unchanged (read-only guarantee)
#
# Checksums the fixture tree before/after with BSD `md5` (macOS bash 3.2
# safe — no md5sum/sha1sum dependency assumed).
# Run from repo root: bash tests/test-adopt-analyze.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ANALYZER="$REPO_ROOT/scripts/adopt-analyze.sh"
FIXTURE="$REPO_ROOT/tests/fixtures/adoption/sample-project"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/adopt-analyze-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

REPORT="$TEST_DIR/adoption-report.md"

PASS=0
FAIL=0
TOTAL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

assert_contains() {
    local output="$1"
    local expected="$2"
    local label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output (first 20 lines):${NC}"
        echo "$output" | head -20 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_eq() {
    local actual="$1"
    local expected="$2"
    local label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected: '$expected', got: '$actual')"
        FAIL=$((FAIL + 1))
    fi
}

assert_exit_code() {
    local actual="$1"
    local expected="$2"
    local label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -eq "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

assert_nonzero_exit() {
    local actual="$1"
    local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -ne 0 ]; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected non-zero exit, got 0)"
        FAIL=$((FAIL + 1))
    fi
}

# fixture_checksum — sorted per-file BSD md5 over the fixture tree, so any
# content OR structural change (added/removed/renamed file) changes the sum.
fixture_checksum() {
    find "$FIXTURE" -type f -exec md5 {} + | sort
}

# =============================================================================
echo -e "\n${CYAN}=== Test 0: Script syntax and help ===${NC}\n"
# =============================================================================
syntax_output=$(bash -n "$ANALYZER" 2>&1)
assert_exit_code $? 0 "adopt-analyze.sh has valid bash syntax"

help_output=$(bash "$ANALYZER" --help 2>&1)
assert_contains "$help_output" "read-only" "help mentions read-only guarantee"
assert_contains "$help_output" "--out" "help documents --out"

ec=0
bash "$ANALYZER" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "missing target-repo-path is rejected"

# =============================================================================
echo -e "\n${CYAN}=== Test 1: read-only guarantee (fixture tree unchanged) ===${NC}\n"
# =============================================================================
BEFORE=$(fixture_checksum)

bash "$ANALYZER" "$FIXTURE" --out "$REPORT" > "$TEST_DIR/run.log" 2>&1
RUN_EC=$?
assert_exit_code "$RUN_EC" 0 "analyzer runs successfully against the fixture"

AFTER=$(fixture_checksum)
assert_eq "$AFTER" "$BEFORE" "fixture tree checksum is identical before/after (strictly read-only)"

[ -f "$REPORT" ]
assert_exit_code $? 0 "report file was written to --out location"

# =============================================================================
echo -e "\n${CYAN}=== Test 2: refuses to write inside the target ===${NC}\n"
# =============================================================================
ec=0
bash "$ANALYZER" "$FIXTURE" --out "$FIXTURE/report.md" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "analyzer refuses --out path inside the target repo"

[ ! -f "$FIXTURE/report.md" ]
assert_exit_code $? 0 "no report file was created inside the fixture"

# =============================================================================
echo -e "\n${CYAN}=== Test 3: report content — detected stack ===${NC}\n"
# =============================================================================
REPORT_CONTENT=$(cat "$REPORT")

assert_contains "$REPORT_CONTENT" "## Detected Stack" "report has a Detected Stack section"
assert_contains "$REPORT_CONTENT" "Node.js" "detects Node.js stack from package.json"
assert_contains "$REPORT_CONTENT" "sample-project" "detected stack includes package.json name"

# =============================================================================
echo -e "\n${CYAN}=== Test 4: report content — existing CI ===${NC}\n"
# =============================================================================
assert_contains "$REPORT_CONTENT" "## Existing CI" "report has an Existing CI section"
assert_contains "$REPORT_CONTENT" "GitHub Actions" "detects GitHub Actions"
assert_contains "$REPORT_CONTENT" ".github/workflows/ci.yml" "lists the CI workflow file"

# =============================================================================
echo -e "\n${CYAN}=== Test 5: report content — tracker references ===${NC}\n"
# =============================================================================
assert_contains "$REPORT_CONTENT" "## Tracker References" "report has a Tracker References section"
assert_contains "$REPORT_CONTENT" "Jira" "detects the Jira reference"
assert_contains "$REPORT_CONTENT" "atlassian.net/browse/SAMP-101" "captures the Jira URL from README"

# =============================================================================

# =============================================================================
echo -e "\n${CYAN}=== Test 5b: tracker detection with spaces in file paths ===${NC}\n"
# =============================================================================
assert_contains "$REPORT_CONTENT" "Linear" "detects Linear reference from file with space in name"
assert_contains "$REPORT_CONTENT" "linear.app" "captures the Linear URL from docs/notes with space.md"

echo -e "\n${CYAN}=== Test 6: report content — harness conflicts ===${NC}\n"
# =============================================================================
assert_contains "$REPORT_CONTENT" "## Harness Conflicts" "report has a Harness Conflicts section"
assert_contains "$REPORT_CONTENT" "CLAUDE.md" "flags the pre-existing CLAUDE.md"
assert_contains "$REPORT_CONTENT" "will conflict with boilerplate file" "conflict uses the required phrasing"

# =============================================================================
echo -e "\n${CYAN}=== Test 7: report content — capability mapping + migration plan ===${NC}\n"
# =============================================================================
assert_contains "$REPORT_CONTENT" "## Capability Mapping Suggestion" "report has a Capability Mapping section"
assert_contains "$REPORT_CONTENT" "Task Tracking Adapter" "capability mapping lists Task Tracking Adapter"

assert_contains "$REPORT_CONTENT" "## Migration Plan Skeleton" "report has a Migration Plan Skeleton section"
assert_contains "$REPORT_CONTENT" "Stage 1" "migration plan lists staged PRs"
assert_contains "$REPORT_CONTENT" "requires human approval before execution (ADR-A-0004)" "migration plan carries the human-approval line"

# =============================================================================
# Summary
# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ $FAIL -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    exit 1
else
    echo -e "  Failed: 0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
