#!/bin/bash
# =============================================================================
# Test: pre-bash-rls-validation.sh — BEHAVIORAL + registration (ABS-149)
# =============================================================================
# ABS-149 rewrote the RLS validation hook from the broken positional-$1 form
# (which never received the command and so never fired) to the Claude Code
# stdin-JSON PreToolUse protocol (ABS-32), and registered it in the harness
# settings.template.json + hooks-config.json.
#
# WHY this targets harness/claude (not live .claude): the live .claude/ is
# generated(pin) from the release tag and must NOT be edited ahead of promotion
# (tests/test-harness-parity.sh guards this). The rewrite therefore lives in the
# harness source-of-record and lands in the live tree only at the next promotion.
# This suite exercises the harness source directly so it is green pre-promotion.
#
# bash 3.2 / BSD safe. jq is required (as it is for the hook itself); the suite
# skips with a clear message if jq is absent.
# Run from repo root: bash tests/test-rls-hook.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK="$REPO_ROOT/harness/claude/hooks/pre-bash-rls-validation.sh"
MIRROR="$REPO_ROOT/agent_providers/claude_code/hooks/pre-bash-rls-validation.sh"
SETTINGS="$REPO_ROOT/harness/claude/settings.template.json"
HOOKSCFG="$REPO_ROOT/harness/claude/hooks-config.json"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

if ! command -v jq >/dev/null 2>&1; then
    echo "SKIP: jq not installed — RLS hook behavioral tests require jq"; exit 0
fi

OUT=""; EC=0
run_hook() { EC=0; OUT=$(printf '%s' "$1" | bash "$HOOK" 2>&1) || EC=$?; }
bash_payload() { printf '{"tool_name":"Bash","tool_input":{"command":%s}}' "$(printf '%s' "$1" | jq -R .)"; }

assert_exit() {
    TOTAL=$((TOTAL + 1))
    if [ "$EC" = "$1" ]; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1));
    else echo -e "  ${RED}FAIL${NC} $2 (expected exit $1, got $EC)"; echo -e "  ${YELLOW}  Output:${NC} $OUT"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$OUT" | grep -qF -- "$1"; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1));
    else echo -e "  ${RED}FAIL${NC} $2 (expected output to contain: $1)"; echo -e "  ${YELLOW}  Output:${NC} $OUT"; FAIL=$((FAIL + 1)); fi
}
assert_empty() {
    TOTAL=$((TOTAL + 1))
    if [ -z "$OUT" ]; then echo -e "  ${GREEN}PASS${NC} $1"; PASS=$((PASS + 1));
    else echo -e "  ${RED}FAIL${NC} $1 (expected empty, got: $OUT)"; FAIL=$((FAIL + 1)); fi
}
assert_true() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "0" ]; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1));
    else echo -e "  ${RED}FAIL${NC} $2"; FAIL=$((FAIL + 1)); fi
}

echo -e "${CYAN}=== RLS hook behavioral (ABS-149) ===${NC}\n"

# --- 1. DB op without RLS context -> advisory warning, never blocks ----------
run_hook "$(bash_payload 'npx prisma db execute --file q.sql')"
assert_exit 0 "DB op without RLS context -> exit 0 (advisory, never blocks)"
assert_contains "WARNING" "warns about missing RLS context"

# --- 2. DB op WITH RLS context -> allowed, no warning ------------------------
run_hook "$(bash_payload 'node -e "withUserContext(prisma, id, fn)" # DATABASE_URL')"
assert_exit 0 "DB op with RLS context -> exit 0"
assert_contains "RLS context detected" "acknowledges RLS context"

# --- 3. Schema / migration op -> allowed without RLS context -----------------
run_hook "$(bash_payload 'npx prisma migrate dev')"
assert_exit 0 "prisma migrate -> exit 0"
assert_contains "schema operation" "migration allowed without RLS context"

# --- 4. Non-DB command -> silently ignored -----------------------------------
run_hook "$(bash_payload 'ls -la')"
assert_exit 0 "non-DB command -> exit 0"
assert_empty "non-DB command produces no output"

# --- 5. jq-missing -> fail open (exit 0), never hard-block -------------------
NOJQ="$SCRIPT_DIR/.nojq-rls.$$"; mkdir -p "$NOJQ"
for t in bash grep printf cat; do ln -sf "$(command -v $t)" "$NOJQ/$t" 2>/dev/null || true; done
EC=0; OUT=$(printf '%s' "$(bash_payload 'npx prisma db execute')" | PATH="$NOJQ" bash "$HOOK" 2>&1) || EC=$?
rm -rf "$NOJQ"
assert_exit 0 "jq missing -> fail-open exit 0"
assert_contains "jq not found" "warns about missing jq"

# --- 6. Old dead-gate regression guard: must NOT read $1 ---------------------
grep -q 'BASH_COMMAND="\$1"' "$HOOK"; assert_true "$([ $? -ne 0 ] && echo 0 || echo 1)" \
    "hook does not read the command from \$1 (old dead-gate form)"
grep -q 'payload=\$(cat)' "$HOOK"; assert_true "$?" "hook reads payload from stdin"

# --- 7. Registration: wired in harness settings.template.json + hooks-config -
jq -e '[.hooks.PreToolUse[] | select((.matcher//"")=="Bash") | .hooks[].command]
       | map(select(test("pre-bash-rls-validation\\.sh"))) | length > 0' "$SETTINGS" >/dev/null 2>&1
assert_true "$?" "RLS hook registered in harness settings.template.json (PreToolUse/Bash)"
jq -e '[.hooks.PreToolUse[] | select((.matcher//"")=="Bash") | .hooks[].command]
       | map(select(test("pre-bash-rls-validation\\.sh"))) | length > 0' "$HOOKSCFG" >/dev/null 2>&1
assert_true "$?" "RLS hook registered in harness hooks-config.json (PreToolUse/Bash)"

# --- 8. Source-of-record == provider mirror ----------------------------------
diff -q "$HOOK" "$MIRROR" >/dev/null 2>&1
assert_true "$?" "harness hook == agent_providers/claude_code mirror (byte-identical)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
