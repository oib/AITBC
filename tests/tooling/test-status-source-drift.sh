#!/bin/bash
# =============================================================================
# Test: Status Source-of-Truth Drift Guard (ABS-404)
# =============================================================================
# Exercises scripts/status-source-drift-guard.sh, the single central guard that
# checks every embedded copy of the status list/order/terminality against
# profiles/neutral/adapters/statuses.yaml (COPY A: iteration-guard ranks;
# COPY B: orchestrator is_known_status; COPY C: orchestrator terminal rest-skip
# lists; COPY D: backend statuses.yaml mirror).
#
# The headline case (AC3): a NEW status added to statuses.yaml without the
# corresponding follow-up in an embedded copy turns the central guard RED — the
# exact ABS-338 'Canceled' drift, caught now BEFORE the merge instead of at the
# release check. This file is auto-discovered by the CI / pre-release
# tests/test-*.sh loops, which is the AC4 wiring (no config edit needed).
#
# Run from repo root: bash tests/tooling/test-status-source-drift.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/status-source-drift-guard.sh"
SOURCE="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"

PASS=0
FAIL=0
TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Run the guard; echo its exit code (never aborts under set -e).
guard_exit() {
    local ec=0
    STATUS_SOURCE_FILE="$1" bash "$GUARD" >/dev/null 2>&1 || ec=$?
    echo "$ec"
}
# Run the guard; echo its stderr.
guard_stderr() { STATUS_SOURCE_FILE="$1" bash "$GUARD" 2>&1 >/dev/null || true; }

assert_exit() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"; FAIL=$((FAIL + 1))
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

echo -e "${CYAN}=== Status Source Drift Guard (ABS-404) ===${NC}\n"

# --- Clean repo: the guard is green -------------------------------------------
echo -e "${CYAN}Clean repo (no drift)${NC}"
assert_exit "$(guard_exit "$SOURCE")" 0 "guard passes against the real statuses.yaml + embedded copies"

# --- AC3: a NEW status in statuses.yaml with no follow-up -> guard RED ---------
# Inject a status the embedded copies do NOT carry; the guard must go red on
# every copy that duplicates the list.
echo -e "\n${CYAN}AC3: new status without a follow-up in the copies -> guard red${NC}"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/status-drift-test-XXXXXX")
trap 'rm -rf "$TMP"' EXIT

# Non-terminal new status inserted before Canceled (keeps YAML shape valid).
sed 's/^  - name: Canceled/  - name: Frobnicated\n    next: []\n  - name: Canceled/' \
    "$SOURCE" > "$TMP/nonterminal.yaml"
nt_out="$(guard_stderr "$TMP/nonterminal.yaml")"
assert_exit "$(guard_exit "$TMP/nonterminal.yaml")" 1 "injected non-terminal status -> guard exits 1"
assert_contains "$nt_out" "COPY A" "COPY A (iteration-guard ranks) drift reported"
assert_contains "$nt_out" "COPY B" "COPY B (is_known_status) drift reported"
assert_contains "$nt_out" "COPY D" "COPY D (backend mirror) drift reported"
assert_contains "$nt_out" "COPY F: status 'Frobnicated'" "COPY F (knowledge doc) drift reported for the new status"

# Terminal new status (terminal: true) -> ALSO trips the COPY C terminal check.
sed 's/^  - name: Canceled/  - name: Frobnicated\n    terminal: true\n    next: []\n  - name: Canceled/' \
    "$SOURCE" > "$TMP/terminal.yaml"
t_out="$(guard_stderr "$TMP/terminal.yaml")"
assert_exit "$(guard_exit "$TMP/terminal.yaml")" 1 "injected terminal status -> guard exits 1"
assert_contains "$t_out" "COPY C: terminal status 'Frobnicated'" "COPY C (terminal rest-skip lists) drift reported"

# --- COPY E: fastlane IN_FLIGHT token that is not a statuses.yaml name -> red --
# A bogus token in the fastlane IN_FLIGHT membership subset (or a status renamed
# in statuses.yaml that leaves an IN_FLIGHT token dangling) must turn the guard
# red — the fastlane copy the Stage-1 review found uncovered (AC1).
echo -e "\n${CYAN}COPY E: fastlane IN_FLIGHT token not in statuses.yaml -> guard red${NC}"
FL="$REPO_ROOT/scripts/fastlane-eligibility.sh"
if [ -f "$FL" ]; then
    sed 's/^IN_FLIGHT="In Progress/IN_FLIGHT="Bogus Status|In Progress/' "$FL" > "$TMP/fastlane.sh"
    TOTAL=$((TOTAL + 1))
    e_out="$(STATUS_FASTLANE_FILE="$TMP/fastlane.sh" bash "$GUARD" 2>&1 >/dev/null || true)"
    e_ec=0; STATUS_FASTLANE_FILE="$TMP/fastlane.sh" bash "$GUARD" >/dev/null 2>&1 || e_ec=$?
    if [ "$e_ec" = "1" ]; then
        echo -e "  ${GREEN}PASS${NC} bogus IN_FLIGHT token -> guard exits 1"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} bogus IN_FLIGHT token -> guard exits 1 (got $e_ec)"; FAIL=$((FAIL + 1))
    fi
    assert_contains "$e_out" "COPY E: fastlane IN_FLIGHT token 'Bogus Status'" "COPY E drift reported"
else
    echo -e "  ${CYAN}SKIP${NC} scripts/fastlane-eligibility.sh not present"
fi

# --- COPY F: knowledge doc count claim drifts -> red ---------------------------
# The ABS-338 'Canceled' class in the DOC direction: statuses.yaml grows, the
# knowledge doc's "defines **N** canonical statuses" sentence (or a status
# mention) is forgotten (ABS-520 / epic ABS-514).
echo -e "\n${CYAN}COPY F: knowledge doc count/membership drift -> guard red${NC}"
KN="$REPO_ROOT/knowledge/ticket-lifecycle-and-statuses.md"
if [ -f "$KN" ]; then
    sed 's/defines \*\*[0-9]*\*\* canonical statuses/defines **7** canonical statuses/' "$KN" > "$TMP/knowledge.md"
    TOTAL=$((TOTAL + 1))
    f_ec=0; STATUS_KNOWLEDGE_FILE="$TMP/knowledge.md" bash "$GUARD" >/dev/null 2>&1 || f_ec=$?
    if [ "$f_ec" = "1" ]; then
        echo -e "  ${GREEN}PASS${NC} wrong count claim -> guard exits 1"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} wrong count claim -> guard exits 1 (got $f_ec)"; FAIL=$((FAIL + 1))
    fi
    f_out="$(STATUS_KNOWLEDGE_FILE="$TMP/knowledge.md" bash "$GUARD" 2>&1 >/dev/null || true)"
    assert_contains "$f_out" "COPY F: knowledge doc claims 7" "COPY F count drift reported"
else
    echo -e "  ${CYAN}SKIP${NC} knowledge doc not present"
fi

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
