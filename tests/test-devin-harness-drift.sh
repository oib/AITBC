#!/usr/bin/env bash
# =============================================================================
# Devin mirror drift guard (same pattern as tests/test-harness-parity.sh)
# =============================================================================
# Exercises scripts/check-devin-harness-drift.sh and reports PASS/FAIL counts.
# Includes negative tests that inject drift to verify the guard detects it.
# Run from repo root: bash tests/test-devin-harness-drift.sh
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHECK="$REPO_ROOT/scripts/check-devin-harness-drift.sh"
MIRROR="$REPO_ROOT/scripts/mirror-claude-to-devin.py"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Track all backup files for cleanup on EXIT/ERR
BACKUP_DIR="/tmp/devin-test-backups-$$"
mkdir -p "$BACKUP_DIR"
BACKUP_FILES=()

# Cleanup trap — always restore from backups and remove temp files
cleanup() {
    local rc=$?
    for entry in "${BACKUP_FILES[@]}"; do
        local backup="${entry%%|*}"
        local target="${entry##*|}"
        if [ -f "$backup" ] && [ -n "$target" ] && [ -f "$target" ]; then
            cp "$backup" "$target" 2>/dev/null || true
        fi
    done
    rm -rf "$BACKUP_DIR" 2>/dev/null || true
    # Remove any leftover temp files
    rm -f /tmp/devin_drift_check.$$ /tmp/devin_neg_backup_$$ 2>/dev/null || true
    exit $rc
}
trap cleanup EXIT

# Helper: backup a file before mutating it (only first time — preserves original)
backup_file() {
    local target="$1"
    local backup="$BACKUP_DIR/$(echo "$target" | tr '/' '_')"
    # Only backup if not already backed up (preserve original state)
    if [ ! -f "$backup" ]; then
        cp "$target" "$backup"
        BACKUP_FILES+=("$backup|$target")
    fi
}

assert_true() {
    local code="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$code" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; FAIL=$((FAIL + 1))
    fi
}

assert_false() {
    local code="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$code" != "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label (correctly detected drift)"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (drift NOT detected)"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== Devin harness drift guard ===${NC}\n"

# --- Happy path tests --------------------------------------------------------
OUTFILE="/tmp/devin_drift_check.$$"
if bash "$CHECK" >"$OUTFILE" 2>&1; then
    assert_true 0 "harness/devin/ and .devin/ match their generators"
    echo "    No drift."
    # Verify the semantic lint ran
    if grep -q "Semantic lint: all checks passed" "$OUTFILE"; then
        assert_true 0 "semantic lint passed"
    else
        assert_true 1 "semantic lint passed"
    fi
    # Verify .claude vs harness/claude check ran
    if grep -q ".claude/ matches harness/claude/" "$OUTFILE"; then
        assert_true 0 ".claude/ vs harness/claude/ parity checked"
    else
        assert_true 1 ".claude/ vs harness/claude/ parity checked"
    fi
else
    assert_true 1 "harness/devin/ and .devin/ match their generators"
    echo "    Drift output:"
    sed 's/^/      /' "$OUTFILE"
fi
rm -f "$OUTFILE"

# --- Negative tests: inject drift and verify detection -----------------------
echo ""
echo -e "${CYAN}=== Negative tests (drift injection) ===${NC}\n"

# Test 1: Inject content drift in a .devin skill
TARGET_SKILL="$REPO_ROOT/.devin/skills/safe-workflow/SKILL.md"
if [ -f "$TARGET_SKILL" ]; then
    backup_file "$TARGET_SKILL"
    echo "<!-- DRIFT INJECTION -->" >> "$TARGET_SKILL"
    if bash "$CHECK" >/dev/null 2>&1; then
        assert_false 0 "content drift in .devin skill detected"
    else
        assert_false 1 "content drift in .devin skill detected"
    fi
else
    assert_true 0 "content drift test skipped (no safe-workflow skill)"
fi

# Test 2: Inject unknown tool in a .devin agent
TARGET_AGENT="$REPO_ROOT/.devin/agents/rte.md"
if [ -f "$TARGET_AGENT" ]; then
    backup_file "$TARGET_AGENT"
    sed -i 's/allowed-tools:/allowed-tools:\n  - bogus_invalid_tool/' "$TARGET_AGENT" 2>/dev/null || \
        sed -i '' 's/allowed-tools:/allowed-tools:\
  - bogus_invalid_tool/' "$TARGET_AGENT"
    if python3 "$MIRROR" --lint >/dev/null 2>&1; then
        assert_false 0 "unknown tool in .devin agent detected by lint"
    else
        assert_false 1 "unknown tool in .devin agent detected by lint"
    fi
else
    assert_true 0 "unknown tool test skipped (no rte agent)"
fi

# Test 3: Inject Claude model alias in a .devin agent
if [ -f "$TARGET_AGENT" ]; then
    backup_file "$TARGET_AGENT"
    sed -i 's/^model: .*/model: opus/' "$TARGET_AGENT" 2>/dev/null || \
        sed -i '' 's/^model:.*/model: opus/' "$TARGET_AGENT"
    if python3 "$MIRROR" --lint >/dev/null 2>&1; then
        assert_false 0 "Claude model alias in .devin agent detected by lint"
    else
        assert_false 1 "Claude model alias in .devin agent detected by lint"
    fi
else
    assert_true 0 "Claude model alias test skipped (no rte agent)"
fi

# Test 4: Remove subagent flag from a .devin skill that should have it
TARGET_SUBAGENT_SKILL="$REPO_ROOT/.devin/skills/pattern-discovery/SKILL.md"
if [ -f "$TARGET_SUBAGENT_SKILL" ]; then
    backup_file "$TARGET_SUBAGENT_SKILL"
    sed -i '/^subagent: true/d' "$TARGET_SUBAGENT_SKILL" 2>/dev/null || \
        sed -i '' '/^subagent: true/d' "$TARGET_SUBAGENT_SKILL"
    if python3 "$MIRROR" --lint >/dev/null 2>&1; then
        assert_false 0 "lost subagent flag in .devin skill detected by lint"
    else
        assert_false 1 "lost subagent flag in .devin skill detected by lint"
    fi
else
    assert_true 0 "subagent flag test skipped (no pattern-discovery skill)"
fi

# Verify restoration: final happy-path check
echo ""
echo -e "${CYAN}=== Post-restoration verification ===${NC}\n"
# Explicitly restore all backups before checking (the EXIT trap is a safety net)
for entry in "${BACKUP_FILES[@]}"; do
    backup="${entry%%|*}"
    target="${entry##*|}"
    if [ -f "$backup" ] && [ -n "$target" ]; then
        cp "$backup" "$target" 2>/dev/null || true
    fi
done
BACKUP_FILES=()  # clear so the trap doesn't re-restore

if bash "$CHECK" >/dev/null 2>&1; then
    assert_true 0 "all trees restored — drift guard passes again"
else
    assert_true 1 "all trees restored — drift guard passes again"
    echo "  WARNING: restoration may have failed — check git status"
fi

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
