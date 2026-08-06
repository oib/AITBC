#!/bin/bash
# =============================================================================
# Test: .gitattributes enforces LF normalisation (ABS-275)
# =============================================================================
# Regression guard for the LF rules `* text=auto eol=lf` and `*.sh text eol=lf`
# (ABS-275). This repo's .gitattributes was created by f79bb79 (ABS-215) with
# only the merge=union driver, so the rules were absent until ABS-275 added
# them. Without them git for Windows (core.autocrlf=true) checks out CRLF, a
# CRLF .sh dies at exec ("bad interpreter: /bin/bash^M"), and upgrade diffs
# degrade into whole-file EOL conflicts, as a consumer hit on the
# v2.21.2 -> v2.25.0 migration.
#
# Coverage:
#   AC1  both rules are declared AND git resolves them for real paths (.sh, .md,
#        extensionless), while the ABS-215 merge=union driver still applies to
#        the SOP change log, so the two coexist rather than shadow each other.
#   AC2  this file, so dropping a rule fails CI.
#   +    the invariant behind the rules: no CRLF blob in the index.
#
# The behaviour assertions go through `git check-attr`, git's own resolver, so
# reordering or recommenting .gitattributes does not break the test. Only losing
# the behaviour does.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-gitattributes-eol.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ATTR_FILE="$REPO_ROOT/.gitattributes"

cd "$REPO_ROOT" || exit 1

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}

# check_attr <attribute> <path> -> the resolved value ("unspecified" when unset)
check_attr() {
    git check-attr "$1" -- "$2" 2>/dev/null | sed "s|^.*: $1: ||"
}

echo -e "${CYAN}=== .gitattributes LF normalisation (ABS-275) ===${NC}\n"

# -----------------------------------------------------------------------------
echo -e "${CYAN}--- AC1: the eol rules are declared ---${NC}"
# -----------------------------------------------------------------------------
# Whitespace-tolerant, comment-insensitive: the rule must be a live line.
# (A missing .gitattributes fails these two assertions anyway — no separate
# existence check needed.)
grep -qE '^[[:space:]]*\*[[:space:]]+text=auto[[:space:]]+eol=lf[[:space:]]*$' "$ATTR_FILE" \
    && r=yes || r=no
assert_eq "$r" "yes" "'* text=auto eol=lf' is declared"

grep -qE '^[[:space:]]*\*\.sh[[:space:]]+text[[:space:]]+eol=lf[[:space:]]*$' "$ATTR_FILE" \
    && r=yes || r=no
assert_eq "$r" "yes" "'*.sh text eol=lf' is declared"

# -----------------------------------------------------------------------------
echo -e "\n${CYAN}--- AC1: git RESOLVES the rules (behaviour, not text) ---${NC}"
# -----------------------------------------------------------------------------
# Shell scripts: marked text outright + checked out LF on every platform.
assert_eq "$(check_attr text 'scripts/orchestrator.sh')" "set" "a .sh file resolves text=set"
assert_eq "$(check_attr eol  'scripts/orchestrator.sh')" "lf"  "a .sh file resolves eol=lf"

# Everything else rides the catch-all: auto-detected as text, checked out LF.
assert_eq "$(check_attr text 'README.md')" "auto" "a .md file resolves text=auto"
assert_eq "$(check_attr eol  'README.md')" "lf"   "a .md file resolves eol=lf"

# A tracked path with no extension still gets the catch-all (LICENSE, Dockerfile).
assert_eq "$(check_attr eol 'LICENSE')" "lf" "an extensionless path resolves eol=lf"

# -----------------------------------------------------------------------------
echo -e "\n${CYAN}--- AC1: coexistence with the ABS-215 merge driver ---${NC}"
# -----------------------------------------------------------------------------
# Attributes are per-attribute, not per-line: the SOP change log must keep
# merge=union AND pick up eol=lf from the catch-all. A regression that clobbers
# either one fails here.
SOP="docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md"
assert_eq "$(check_attr merge "$SOP")" "union" "SOP change log keeps merge=union (ABS-215)"
assert_eq "$(check_attr eol   "$SOP")" "lf"    "SOP change log also resolves eol=lf (ABS-275)"

# -----------------------------------------------------------------------------
echo -e "\n${CYAN}--- the invariant: no CRLF blob is committed ---${NC}"
# -----------------------------------------------------------------------------
# The rules exist to keep CR out of the index. Assert the end state directly:
# `git grep --cached -I` searches committed blobs (-I skips binaries), so a
# CRLF text file that slipped in — the thing that breaks Windows consumers —
# fails the suite with the offending paths named.
TOTAL=$((TOTAL + 1))
CRLF_FILES="$(git grep --cached -I -l -- $'\r' 2>/dev/null || true)"
if [ -z "$CRLF_FILES" ]; then
    echo -e "  ${GREEN}PASS${NC} no CRLF blobs in the index"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} CRLF blobs committed to the index:"
    echo "$CRLF_FILES" | head -10 | sed 's/^/      /'
    echo -e "  ${YELLOW}  Fix: git add --renormalize . && git commit${NC}"
    FAIL=$((FAIL + 1))
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
