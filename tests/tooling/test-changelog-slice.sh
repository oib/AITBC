#!/bin/bash
# =============================================================================
# Test: HARNESS_CHANGELOG.yml slicer (ABS-227 AC2)
# =============================================================================
# Asserts that scripts/changelog-slice.sh emits ONLY the from->to slice of a
# changelog -- the exact scope that replaces reading the full 1000+ line
# HARNESS_CHANGELOG.yml into an LLM context -- including a multi-version jump,
# breaking-change extraction, and migration_notes extraction.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/tooling/test-changelog-slice.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SLICER="$REPO_ROOT/scripts/changelog-slice.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/changelog-slice-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3 (expected to find: $2)"; FAIL=$((FAIL + 1))
    fi
}
assert_not_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo -e "  ${RED}FAIL${NC} $3 (unexpectedly found: $2)"; FAIL=$((FAIL + 1))
    else
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    fi
}

# -----------------------------------------------------------------------------
# Fixture changelog: five releases so a multi-version jump is exercised
# -----------------------------------------------------------------------------
CL="$TEST_DIR/HARNESS_CHANGELOG.yml"
cat > "$CL" <<'YAML'
schema_version: "1.0.0"
generated_at: "2026-01-01T00:00:00Z"
releases:
  - version: "2.2.0"
    date: "2026-04-01"
    summary: "release 2.2.0"
    changes:
      - path: "a.md"
        change_type: modified
        description: "changed a"
        breaking: false
    migration_notes:
      - "note from 2.2.0"
  - version: "2.1.0"
    date: "2026-03-01"
    summary: "release 2.1.0"
    changes:
      - path: "b.md"
        change_type: deleted
        description: "removed b"
        breaking: true
    migration_notes: []
  - version: "2.0.0"
    date: "2026-02-01"
    summary: "release 2.0.0"
    changes: []
  - version: "1.9.0"
    date: "2026-01-15"
    summary: "release 1.9.0 SHOULD BE EXCLUDED"
    changes:
      - path: "c.md"
        change_type: modified
        description: "changed c LEAKED"
        breaking: true
    migration_notes:
      - "note from 1.9.0 LEAKED"
  - version: "1.0.0"
    date: "2026-01-01"
    summary: "initial SHOULD BE EXCLUDED"
    changes: []
YAML

# =============================================================================
echo -e "\n${CYAN}=== multi-version jump 1.9.0 -> 2.2.0 (slice 2.0.0, 2.1.0, 2.2.0) ===${NC}\n"
# =============================================================================
OUT="$(bash "$SLICER" --since 1.9.0 --to 2.2.0 --file "$CL")"
assert_contains "$OUT" "## 2.2.0 (2026-04-01)" "includes 2.2.0"
assert_contains "$OUT" "## 2.1.0 (2026-03-01)" "includes 2.1.0"
assert_contains "$OUT" "## 2.0.0 (2026-02-01)" "includes 2.0.0"
# --since is EXCLUSIVE: 1.9.0 itself and everything older must be absent
assert_not_contains "$OUT" "1.9.0" "excludes the --since version itself (exclusive lower bound)"
assert_not_contains "$OUT" "LEAKED" "no content from excluded older releases leaks in"
assert_not_contains "$OUT" "initial" "excludes 1.0.0"

# breaking-change extraction (2.1.0 deleted b.md, breaking: true)
assert_contains "$OUT" "- b.md: removed b" "extracts the breaking change from 2.1.0"
# non-breaking change is NOT listed under breaking
assert_not_contains "$OUT" "changed a" "non-breaking change a.md not listed as breaking"
# migration_notes extraction
assert_contains "$OUT" "note from 2.2.0" "extracts 2.2.0 migration note"
# releases with no breaking changes say 'none'
assert_contains "$OUT" "- none" "empty breaking/notes sections render 'none'"

# =============================================================================
echo -e "\n${CYAN}=== --to is inclusive, --since exclusive: slice 2.0.0 -> 2.1.0 ===${NC}\n"
# =============================================================================
OUT="$(bash "$SLICER" --since 2.0.0 --to 2.1.0 --file "$CL")"
assert_contains "$OUT" "## 2.1.0" "includes the --to version (inclusive upper bound)"
assert_not_contains "$OUT" "## 2.2.0" "excludes releases above --to"
assert_not_contains "$OUT" "## 2.0.0" "excludes the --since version (exclusive lower bound)"

# =============================================================================
echo -e "\n${CYAN}=== yaml format is machine-parseable ===${NC}\n"
# =============================================================================
OUT="$(bash "$SLICER" --since 2.0.0 --to 2.2.0 --format yaml --file "$CL")"
assert_contains "$OUT" 'version: "2.1.0"' "yaml format lists version"
assert_contains "$OUT" "breaking_changes:" "yaml format has breaking_changes key"
assert_contains "$OUT" "migration_notes:" "yaml format has migration_notes key"

# =============================================================================
echo -e "\n${CYAN}=== errors: missing --since / missing file ===${NC}\n"
# =============================================================================
bash "$SLICER" --to 2.2.0 --file "$CL" >/dev/null 2>&1; RC=$?
TOTAL=$((TOTAL + 1))
if [ "$RC" -eq 2 ]; then echo -e "  ${GREEN}PASS${NC} missing --since exits 2"; PASS=$((PASS + 1));
else echo -e "  ${RED}FAIL${NC} missing --since exits 2 (got $RC)"; FAIL=$((FAIL + 1)); fi

bash "$SLICER" --since 1.0.0 --file "$TEST_DIR/nope.yml" >/dev/null 2>&1; RC=$?
TOTAL=$((TOTAL + 1))
if [ "$RC" -eq 2 ]; then echo -e "  ${GREEN}PASS${NC} missing changelog file exits 2"; PASS=$((PASS + 1));
else echo -e "  ${RED}FAIL${NC} missing changelog file exits 2 (got $RC)"; FAIL=$((FAIL + 1)); fi

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
# =============================================================================
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}\n"
    exit 1
else
    echo -e "  Failed: 0\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
