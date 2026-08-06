#!/bin/bash
# =============================================================================
# Test: Placeholder Token Registry (ABS-144)
# =============================================================================
# Every {{TOKEN}} that ships in the repo must be accounted for: either the
# setup wizard substitutes it (scripts/setup-template.sh REPLACEMENT_KEYS) or it
# is a documented manual-fill / runtime / doc-ad-hoc token registered in the
# whitelist (tests/manual-token-whitelist.txt).
#
# WHY: a Jira-stack token (jira-mcp) once shipped in an operational
# skill while being defined in NEITHER the wizard NOR any whitelist, so a
# consumer bootstrapped with the token left literal. Nothing distinguished
# wizard-owned tokens from manual ones. This check closes that gap: an
# unregistered NEW token fails the suite.
#
# TOKEN GRAMMAR: {{[A-Z_]+}} -- the exact shape the wizard scans
# (scripts/setup-template.sh "remaining placeholders" notice). This deliberately
# ignores mustache/handlebars ({{#items}}, {{/items}}) and lowercase example
# tokens, which are not substitution placeholders.
#
# bash 3.2 / BSD safe: no associative arrays, no grep -P, no mapfile.
# Run from repo root: bash tests/test-token-registry.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SETUP_SCRIPT="$REPO_ROOT/scripts/setup-template.sh"
WHITELIST="$REPO_ROOT/tests/manual-token-whitelist.txt"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

pass() { TOTAL=$((TOTAL + 1)); PASS=$((PASS + 1)); echo -e "  ${GREEN}PASS${NC} $1"; }
fail() { TOTAL=$((TOTAL + 1)); FAIL=$((FAIL + 1)); echo -e "  ${RED}FAIL${NC} $1"; }

echo -e "\n${CYAN}=== Placeholder token registry (ABS-144) ===${NC}\n"

# --- Sanity ------------------------------------------------------------------
[ -f "$SETUP_SCRIPT" ] || { echo -e "  ${RED}FAIL${NC} setup-template.sh not found"; exit 1; }
[ -f "$WHITELIST" ]    || { echo -e "  ${RED}FAIL${NC} manual-token-whitelist.txt not found"; exit 1; }

# --- Registered token names (wizard REPLACEMENT_KEYS + whitelist) ------------
# Wizard-substituted tokens: the {{...}} entries in the REPLACEMENT_KEYS array.
WIZARD_TOKENS="$(awk '/^declare -a REPLACEMENT_KEYS=\(/{f=1;next} f&&/^\)/{f=0} f' "$SETUP_SCRIPT" \
    | grep -oE '\{\{[A-Z_]+\}\}' | sed -e 's/^{{//' -e 's/}}$//' | sort -u)"

# Whitelisted manual/runtime/doc-ad-hoc tokens (bare NAMEs; '#' comments ignored).
# NOTE: strip whitespace PER LINE (sed processes line-by-line) -- `tr -d` would
# delete newlines too and merge every entry into a single blob.
WHITELIST_TOKENS="$(grep -vE '^[[:space:]]*(#|$)' "$WHITELIST" | sed 's/[[:space:]]//g' | grep -E '^[A-Z_]+$' | sort -u)"

REGISTERED="$(printf '%s\n%s\n' "$WIZARD_TOKENS" "$WHITELIST_TOKENS" | sort -u | grep -v '^$')"

echo -e "  ${CYAN}wizard tokens:${NC} $(printf '%s' "$WIZARD_TOKENS" | grep -c . )   ${CYAN}whitelisted:${NC} $(printf '%s' "$WHITELIST_TOKENS" | grep -c . )"

# --- Scan shipped paths for tokens ------------------------------------------
# Same extension set the wizard rewrites. Exclusions:
#   .git / node_modules / tmp (worktrees)      -- not shipped source
#   graphify-out                               -- generated knowledge graph
#   HARNESS_CHANGELOG.yml                       -- append-only historical prose
#   tests/                                      -- test fixtures use synthetic
#                                                  tokens ({{FOO}}, {{NOT_A_MANIFEST_KEY}})
#                                                  that are not consumer template content
FOUND_TOKENS="$(cd "$REPO_ROOT" && find . \
    -type f \
    \( -name "*.md" -o -name "*.json" -o -name "*.yml" -o -name "*.yaml" \
       -o -name "*.sh" -o -name "*.py" -o -name "*.txt" -o -name "*.toml" \
       -o -name "*.bib" -o -name "*.cff" -o -name "*.mjs" -o -name "*.ts" \
       -o -name "NOTICE" -o -name "LICENSE" -o -name "CODEOWNERS" \
       -o -name ".env.template" \) \
    ! -path "*/.git/*" \
    ! -path "*/node_modules/*" \
    ! -path "./tmp/*" \
    ! -path "*/.harness-backup/*" \
    ! -path "*/worktrees/*" \
    ! -path "./graphify-out/*" \
    ! -path "./HARNESS_CHANGELOG.yml" \
    ! -path "./tests/*" \
    ! -path "./work/*" \
    -print0 \
    | xargs -0 grep -ohE '\{\{[A-Z_]+\}\}' 2>/dev/null \
    | sed -e 's/^{{//' -e 's/}}$//' | sort -u | grep -v '^$')"

echo -e "  ${CYAN}distinct tokens found in shipped paths:${NC} $(printf '%s' "$FOUND_TOKENS" | grep -c . )\n"

# --- Every found token must be registered ------------------------------------
UNREGISTERED=""
for tok in $FOUND_TOKENS; do
    if ! printf '%s\n' "$REGISTERED" | grep -qx "$tok"; then
        UNREGISTERED="$UNREGISTERED $tok"
    fi
done

if [ -z "$UNREGISTERED" ]; then
    pass "all shipped {{TOKEN}}s are registered (wizard REPLACEMENT_KEYS or manual-token whitelist)"
else
    fail "unregistered token(s) found in shipped paths:"
    for tok in $UNREGISTERED; do
        echo -e "        ${YELLOW}{{$tok}}${NC}"
    done
    echo -e "  ${YELLOW}  Fix: add the token to scripts/setup-template.sh REPLACEMENT_KEYS (if the${NC}"
    echo -e "  ${YELLOW}  wizard should fill it) OR to tests/manual-token-whitelist.txt (if it is a${NC}"
    echo -e "  ${YELLOW}  documented manual-fill / runtime / doc-ad-hoc token).${NC}"
fi

# --- Hygiene: whitelist must not duplicate wizard tokens ---------------------
DUP=""
for tok in $WHITELIST_TOKENS; do
    if printf '%s\n' "$WIZARD_TOKENS" | grep -qx "$tok"; then
        DUP="$DUP $tok"
    fi
done
if [ -z "$DUP" ]; then
    pass "whitelist does not duplicate wizard-substituted tokens"
else
    fail "whitelist redundantly lists wizard-substituted token(s):$DUP"
fi

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    exit 1
else
    echo -e "  Failed: 0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
