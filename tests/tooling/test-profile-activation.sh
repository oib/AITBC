#!/bin/bash
# =============================================================================
# Test: Profile Activation (ABS-37)
# =============================================================================
# Exercises scripts/lib/profile.sh (get_active_profile / get_capability_provider)
# and the scripts/profile.sh CLI (show / set) against the real profiles/
# directory shipped in this repo (neutral, evolver, jira-github-postgres,
# saw-stack). Run from repo root: bash tests/tooling/test-profile-activation.sh
#
# Cases:
#   - precedence: ACTIVE_PROFILE env > .active-profile file > "neutral" default
#   - `set` validates the profile exists and writes .active-profile;
#     `show` round-trips it back (active profile + resolved providers)
#   - unknown/missing profile falls back to neutral with a stderr warning
#   - get_capability_provider: evolver profile -> "evolver"; neutral -> "none"
#   - based_on fallback: a profile without its own capability key reads the
#     based_on target's provider (jira-github-postgres -> neutral -> "none")
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROFILE_CLI="$REPO_ROOT/scripts/profile.sh"
PROFILE_LIB="$REPO_ROOT/scripts/lib/profile.sh"

PASS=0
FAIL=0
TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  Output:"; printf '%s\n' "$output" | head -10 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_exit() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

# Isolated project dir: never touch the real repo's .active-profile.
PROJECT_DIR="$(mktemp -d)"
trap 'rm -rf "$PROJECT_DIR"' EXIT
ACTIVE_PROFILE_FILE="$PROJECT_DIR/.active-profile"

# Run a snippet with the library sourced, real PROFILES_DIR, isolated
# ACTIVE_PROFILE_FILE, and a clean env (only what we pass through).
run_lib() {
    env -i HOME="$HOME" PATH="/usr/bin:/bin" \
        REPO_ROOT="$REPO_ROOT" PROFILES_DIR="$REPO_ROOT/profiles" \
        ACTIVE_PROFILE_FILE="$ACTIVE_PROFILE_FILE" \
        "$@" bash -c "source '$PROFILE_LIB'; $LIB_CMD"
}

run_cli() {
    env -i HOME="$HOME" PATH="/usr/bin:/bin" \
        ACTIVE_PROFILE_FILE="$ACTIVE_PROFILE_FILE" \
        "$@" bash "$PROFILE_CLI" "${CLI_ARGS[@]}"
}

echo -e "${CYAN}=== Profile Activation (ABS-37) ===${NC}\n"

# --- Precedence: default (no env, no file) -----------------------------------
echo -e "${CYAN}Precedence: default${NC}"
rm -f "$ACTIVE_PROFILE_FILE"
LIB_CMD='get_active_profile'
out="$(run_lib)"
assert_eq "$out" "neutral" "no env, no file -> neutral"

# --- Precedence: file only ----------------------------------------------------
echo -e "${CYAN}Precedence: file${NC}"
echo "evolver" >"$ACTIVE_PROFILE_FILE"
LIB_CMD='get_active_profile'
out="$(run_lib)"
assert_eq "$out" "evolver" ".active-profile file -> evolver"

# --- Precedence: env wins over file -------------------------------------------
echo -e "${CYAN}Precedence: env over file${NC}"
echo "evolver" >"$ACTIVE_PROFILE_FILE"
LIB_CMD='get_active_profile'
out="$(run_lib ACTIVE_PROFILE=neutral)"
assert_eq "$out" "neutral" "ACTIVE_PROFILE=neutral overrides file (evolver)"
rm -f "$ACTIVE_PROFILE_FILE"

# --- Unknown profile falls back to neutral with a stderr warning -------------
echo -e "${CYAN}Unknown profile fallback${NC}"
LIB_CMD='get_active_profile'
out="$(run_lib ACTIVE_PROFILE=does-not-exist 2>/tmp/abs37-warn.$$)"
warn="$(cat /tmp/abs37-warn.$$)"; rm -f /tmp/abs37-warn.$$
assert_eq "$out" "neutral" "unknown profile name resolves to neutral"
assert_contains "$warn" "WARN" "unknown profile emits a stderr warning"
assert_contains "$warn" "does-not-exist" "warning names the missing profile"

# --- get_capability_provider: evolver profile active --------------------------
echo -e "${CYAN}get_capability_provider: evolver active${NC}"
LIB_CMD='get_capability_provider evolution'
out="$(run_lib ACTIVE_PROFILE=evolver)"
assert_eq "$out" "evolver" "evolution capability -> evolver under evolver profile"

# --- get_capability_provider: neutral profile active --------------------------
echo -e "${CYAN}get_capability_provider: neutral active${NC}"
LIB_CMD='get_capability_provider evolution'
out="$(run_lib ACTIVE_PROFILE=neutral)"
assert_eq "$out" "none" "evolution capability -> none under neutral profile"

# --- based_on fallback: jira-github-postgres has no evolution key, falls
#     back to its based_on (neutral), which is also "none" -------------------
echo -e "${CYAN}based_on fallback${NC}"
LIB_CMD='get_capability_provider evolution'
out="$(run_lib ACTIVE_PROFILE=jira-github-postgres)"
assert_eq "$out" "none" "jira-github-postgres has no evolution key -> based_on neutral -> none"

LIB_CMD='get_capability_provider task-tracking'
out="$(run_lib ACTIVE_PROFILE=jira-github-postgres)"
assert_eq "$out" "jira-cloud" "jira-github-postgres declares task-tracking itself (no fallback needed)"

# --- CLI: set validates the profile exists ------------------------------------
echo -e "${CYAN}CLI: set validates profile${NC}"
rm -f "$ACTIVE_PROFILE_FILE"
CLI_ARGS=(set does-not-exist)
ec=0
run_cli >/tmp/abs37-out.$$ 2>&1 || ec=$?
assert_exit "$ec" 1 "set <unknown profile> exits non-zero"
[ -f "$ACTIVE_PROFILE_FILE" ] && echo -e "  ${RED}FAIL${NC} unknown profile must not write .active-profile" && FAIL=$((FAIL+1))
rm -f /tmp/abs37-out.$$

# --- CLI: set/show round-trip --------------------------------------------------
echo -e "${CYAN}CLI: set/show round-trip${NC}"
rm -f "$ACTIVE_PROFILE_FILE"
CLI_ARGS=(set evolver)
run_cli >/dev/null 2>&1
assert_eq "$(cat "$ACTIVE_PROFILE_FILE" 2>/dev/null)" "evolver" "set evolver writes .active-profile"

CLI_ARGS=(show)
out="$(run_cli)"
assert_contains "$out" "Active profile: evolver" "show reports active profile after set"
assert_contains "$out" "evolution" "show lists the evolution capability"
assert_contains "$out" "evolver" "show resolves evolution -> evolver"

# --- CLI: show under neutral lists mock/none providers ------------------------
echo -e "${CYAN}CLI: show under neutral${NC}"
CLI_ARGS=(set neutral)
run_cli >/dev/null 2>&1
CLI_ARGS=(show)
out="$(run_cli)"
assert_contains "$out" "Active profile: neutral" "show reports neutral after set neutral"
assert_contains "$out" "task-tracking" "show lists task-tracking capability"
rm -f "$ACTIVE_PROFILE_FILE"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
