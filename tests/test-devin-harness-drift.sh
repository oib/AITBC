#!/usr/bin/env bash
# =============================================================================
# Devin mirror drift guard (same pattern as tests/test-harness-parity.sh)
# =============================================================================
# Exercises scripts/check-devin-harness-drift.sh and reports PASS/FAIL counts.
# Run from repo root: bash tests/test-devin-harness-drift.sh
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHECK="$REPO_ROOT/scripts/check-devin-harness-drift.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_true() {
    local code="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$code" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== Devin harness drift guard ===${NC}\n"

if bash "$CHECK" >/tmp/devin_drift_check.$$ 2>&1; then
    assert_true 0 "harness/devin/ and .devin/ match their generators"
    echo "    No drift."
else
    assert_true 1 "harness/devin/ and .devin/ match their generators"
    echo "    Drift output:"
    sed 's/^/      /' /tmp/devin_drift_check.$$
fi
rm -f /tmp/devin_drift_check.$$

echo ""
echo -e "${CYAN}=== Test Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    exit 1
fi
echo -e "  Failed: 0"
echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
exit 0
