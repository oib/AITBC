#!/bin/bash
# =============================================================================
# Test: ORCH_* Knob Documentation Drift Guard (ABS-517 / epic ABS-514)
# =============================================================================
# Exercises scripts/orch-knob-doc-drift.sh — the code->doc reverse of
# docs-identifier-check.sh. Headline case: a NEW ${ORCH_*} knob read in a
# script without an SOP mention turns the guard RED. Auto-discovered by the
# CI / pre-release tests/test-*.sh loops.
#
# Run from repo root: bash tests/tooling/test-orch-knob-drift.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/orch-knob-doc-drift.sh"

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
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== ORCH Knob Doc Drift Guard (ABS-517) ===${NC}\n"

# --- real repo: green ----------------------------------------------------------
echo -e "${CYAN}Real repo${NC}"
real_ec=0
bash "$GUARD" >/dev/null 2>&1 || real_ec=$?
assert_exit "$real_ec" 0 "every ORCH_* knob read in scripts/ is documented in the SOP"

# --- fixture: undocumented new knob -> red -------------------------------------
echo -e "\n${CYAN}New undocumented knob -> guard red${NC}"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/knob-drift-test-XXXXXX")
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/scripts/hooks"
cat > "$TMP/scripts/newfeature.sh" <<'EOF'
#!/bin/bash
FROB="${ORCH_FROBNICATE_LEVEL:-0}"
EOF
printf '# SOP\n\nno knob table entry here\n' > "$TMP/sop.md"
ec=0
KNOB_SCRIPTS_GLOB_DIR="$TMP/scripts" KNOB_SOP_FILE="$TMP/sop.md" \
    bash "$GUARD" >/dev/null 2>"$TMP/err" || ec=$?
assert_exit "$ec" 1 "undocumented knob -> exit 1"
assert_contains "$(cat "$TMP/err")" "ORCH_FROBNICATE_LEVEL" "names the drifted knob"

# --- fixture: documented knob -> green -----------------------------------------
echo -e "\n${CYAN}Documented knob -> guard green${NC}"
printf '# SOP\n\n| ORCH_FROBNICATE_LEVEL | 0 | frobnication |\n' > "$TMP/sop.md"
ec=0
KNOB_SCRIPTS_GLOB_DIR="$TMP/scripts" KNOB_SOP_FILE="$TMP/sop.md" \
    bash "$GUARD" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 0 "documented knob -> exit 0"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
