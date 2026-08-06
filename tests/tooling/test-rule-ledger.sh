#!/bin/bash
# =============================================================================
# Test: Rule Ledger Check (ABS-515 / epic ABS-514, ADR-A-0028)
# =============================================================================
# Exercises scripts/rule-ledger-check.sh: the ledger completeness/consistency
# guard over the RULES-carrying markdown surface. Mutation fixtures prove each
# failure class goes RED (an unregistered heading, a dangling anchor, a missing
# sensor, a missing risk note, a duplicate id, an invisible new rules file),
# and the real repo ledger stays GREEN. Auto-discovered by the CI /
# pre-release tests/test-*.sh loops.
#
# Run from repo root: bash tests/test-rule-ledger.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD="$REPO_ROOT/scripts/rule-ledger-check.sh"

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

echo -e "${CYAN}=== Rule Ledger Check (ABS-515) ===${NC}\n"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/rule-ledger-test-XXXXXX")
trap 'rm -rf "$TMP"' EXIT

# --- fixture mini-root ---------------------------------------------------------
# One rules file with 2 headings (one duplicated pattern is covered by the real
# repo run below), one sensor script with a function, one test sensor file.
mkdir -p "$TMP/root/docs/sop" "$TMP/root/scripts" "$TMP/root/tests"
cat > "$TMP/root/docs/sop/MINI_SOP.md" <<'EOF'
# Mini SOP

## Enforced Rule

body

## Free Rule

body
EOF
cat > "$TMP/root/scripts/mini-guard.sh" <<'EOF'
#!/bin/bash
mini_gate() { :; }
EOF
: > "$TMP/root/tests/test-mini.sh"

good_ledger() {
cat > "$TMP/ledger.yaml" <<'EOF'
scope_dirs:
  - docs/sop
scope:
  - docs/sop/MINI_SOP.md
rules:
  - id: R-0001
    file: docs/sop/MINI_SOP.md
    heading: "Enforced Rule"
    kind: enforced
    sensors: [scripts/mini-guard.sh:mini_gate, tests/test-mini.sh]
  - id: R-0002
    file: docs/sop/MINI_SOP.md
    heading: "Free Rule"
    kind: unenforced
    risk: "relies on LLM adherence"
EOF
}

run_guard() { # run_guard -> echoes exit code (stderr to $TMP/err)
    local ec=0
    RULE_LEDGER_FILE="$TMP/ledger.yaml" RULE_LEDGER_ROOT="$TMP/root" \
        RULE_LEDGER_REQUIRED_SCOPE="docs/sop/MINI_SOP.md" \
        bash "$GUARD" >/dev/null 2>"$TMP/err" || ec=$?
    echo "$ec"
}

# --- clean fixture: green ------------------------------------------------------
echo -e "${CYAN}Clean fixture${NC}"
good_ledger
assert_exit "$(run_guard)" 0 "complete consistent mini ledger passes"

# --- C4: new heading without a ledger row -> red -------------------------------
echo -e "\n${CYAN}C4: unregistered heading${NC}"
good_ledger
printf '\n## Brand New Rule\n\nbody\n' >> "$TMP/root/docs/sop/MINI_SOP.md"
assert_exit "$(run_guard)" 1 "new md heading without ledger row -> exit 1"
assert_contains "$(cat "$TMP/err")" "C4" "reported as C4"
assert_contains "$(cat "$TMP/err")" "Brand New Rule" "names the missing heading"
# restore
sed -i '' -e '/Brand New Rule/,$d' "$TMP/root/docs/sop/MINI_SOP.md" 2>/dev/null \
    || sed -i -e '/Brand New Rule/,$d' "$TMP/root/docs/sop/MINI_SOP.md"

# --- C4: dangling anchor (heading renamed in md) -------------------------------
echo -e "\n${CYAN}C4: dangling anchor${NC}"
good_ledger
printf '  - id: R-0003\n    file: docs/sop/MINI_SOP.md\n    heading: "Gone Rule"\n    kind: informative\n' >> "$TMP/ledger.yaml"
assert_exit "$(run_guard)" 1 "ledger row for absent heading -> exit 1"
assert_contains "$(cat "$TMP/err")" "dangling anchor" "reported as dangling anchor"

# --- C2: enforced with missing sensor path -------------------------------------
echo -e "\n${CYAN}C2: sensor path missing${NC}"
good_ledger
sed -i '' -e 's|tests/test-mini.sh|tests/test-ghost.sh|' "$TMP/ledger.yaml" 2>/dev/null \
    || sed -i -e 's|tests/test-mini.sh|tests/test-ghost.sh|' "$TMP/ledger.yaml"
assert_exit "$(run_guard)" 1 "enforced sensor path does not exist -> exit 1"
assert_contains "$(cat "$TMP/err")" "C2" "reported as C2"

# --- C2: sensor function not defined -------------------------------------------
echo -e "\n${CYAN}C2: sensor function missing${NC}"
good_ledger
sed -i '' -e 's|mini-guard.sh:mini_gate|mini-guard.sh:ghost_gate|' "$TMP/ledger.yaml" 2>/dev/null \
    || sed -i -e 's|mini-guard.sh:mini_gate|mini-guard.sh:ghost_gate|' "$TMP/ledger.yaml"
assert_exit "$(run_guard)" 1 "enforced sensor function not found -> exit 1"
assert_contains "$(cat "$TMP/err")" "ghost_gate" "names the missing function"

# --- C3: unenforced without risk ------------------------------------------------
echo -e "\n${CYAN}C3: unenforced without risk note${NC}"
good_ledger
sed -i '' -e '/risk: "relies on LLM adherence"/d' "$TMP/ledger.yaml" 2>/dev/null \
    || sed -i -e '/risk: "relies on LLM adherence"/d' "$TMP/ledger.yaml"
assert_exit "$(run_guard)" 1 "unenforced without risk -> exit 1"
assert_contains "$(cat "$TMP/err")" "C3" "reported as C3"

# --- C1: duplicate id -----------------------------------------------------------
echo -e "\n${CYAN}C1: duplicate rule id${NC}"
good_ledger
sed -i '' -e 's/id: R-0002/id: R-0001/' "$TMP/ledger.yaml" 2>/dev/null \
    || sed -i -e 's/id: R-0002/id: R-0001/' "$TMP/ledger.yaml"
assert_exit "$(run_guard)" 1 "duplicate id -> exit 1"
assert_contains "$(cat "$TMP/err")" "duplicate rule ids" "reported as duplicate ids"

# --- C6: new rules file invisible to the ledger -> red --------------------------
echo -e "\n${CYAN}C6: new file under scope_dir not in scope${NC}"
good_ledger
printf '# New SOP\n\n## Sneaky Rule\n\nbody\n' > "$TMP/root/docs/sop/NEW_SOP.md"
assert_exit "$(run_guard)" 1 "new *.md under scope_dir without scope entry -> exit 1"
assert_contains "$(cat "$TMP/err")" "C6" "reported as C6"
rm -f "$TMP/root/docs/sop/NEW_SOP.md"

# --- real repo: ledger green + report shape ------------------------------------
echo -e "\n${CYAN}Real repo ledger${NC}"
real_ec=0
bash "$GUARD" >/dev/null 2>&1 || real_ec=$?
assert_exit "$real_ec" 0 "repo docs/rule-ledger.yaml passes the checker"
report="$(bash "$GUARD" --report 2>/dev/null)"
assert_contains "$report" "Unenforced backlog" "report carries the absolute backlog count"
assert_contains "$report" "not: proven live-wired" "report states honest enforced semantics"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
