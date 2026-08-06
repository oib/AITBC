#!/bin/bash
# =============================================================================
# Test: Run-ID Enabler (ABS-347)
# =============================================================================
# Verifies the per-run artifact namespace feature added by ABS-347:
#   AC1: each run has a stable, non-empty run-ID recorded in run.log (RUN-START)
#   AC2: two sequential runs produce distinct run-IDs (artifact namespaces differ)
#   AC3: ORCH_RUN_ID_SEPARATION=0 disables run-ID (legacy single-stream behavior)
#
# Run from repo root: bash tests/test-run-id.sh
# =============================================================================

set -e
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

# ABS-335: LIVE-STATE REFUSAL GATE — reject if an ambient env still points at a
# live orchestrator state dir. Same pattern as test-orchestrator.sh.
_ls_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ls_state_dir="${ORCH_STATE_DIR:-${ORCH_TARGET_REPO:-$_ls_repo_root}/work/.orchestrator}"
_ls_iid_file="$_ls_state_dir/instance-id"
if [ -s "$_ls_iid_file" ]; then
    _ls_iid="$(head -n1 "$_ls_iid_file")"
    _ls_pid="$(printf '%s\n' "$_ls_iid" | awk -F- '{print $(NF-1)}')"
    if [ -n "$_ls_pid" ] && kill -0 "$_ls_pid" 2>/dev/null; then
        echo "ERROR (ABS-335): refusing to run — ambient env points at a LIVE orchestrator state dir." >&2
        exit 1
    fi
fi
unset _ls_repo_root _ls_state_dir _ls_iid_file _ls_iid _ls_pid

# Prefix-unset all ORCH_* and JIRA_* (ABS-286/ABS-291: results must be a
# function of the commit, not of the seat's exported environment).
unset "${!ORCH_@}"
unset "${!JIRA_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
STUB="$REPO_ROOT/tests/fixtures/stub-spawn.sh"

export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$TRACKER"
# Pin legacy scheduling to keep tests synchronous (same as test-orchestrator.sh).
export ORCH_ASYNC_SPAWNS=0
export ORCH_DEPENDS_GATING=0
export ORCH_SESSION_RESUME=0
export ORCH_WORKTREE_SPAWNS=0

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  Output:"; head -20 <<<"$output" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"
        echo -e "  Output:"; head -20 <<<"$output" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

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

assert_ne() {
    local actual="$1" unexpected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" != "$unexpected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected values to differ, both were '$actual')"
        FAIL=$((FAIL + 1))
    fi
}

# new_env: isolated ticket store + orchestrator state dir for each scenario.
new_env() {
    TEST_DIR="$(mktemp -d /tmp/run-id-test-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    unset ORCH_RUN_LOG
    unset ORCH_RUN_ID ORCH_RUN_ID_SEPARATION
    unset ORCH_INSTANCE_ID ORCH_INSTANCE_ID_FILE
    export ORCH_SPAWN_CMD="$STUB"
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
}

cleanup_env() {
    rm -rf "$TEST_DIR" 2>/dev/null || true
}

# orch: run orchestrator with the current exported env.
orch() { bash "$ORCH" "$@"; }

# =============================================================================
echo -e "\n${CYAN}=== AC1: run-ID is non-empty and recorded in run.log (RUN-START) ===${NC}\n"
# =============================================================================

new_env
# A dry-run --once invocation goes through main() which calls init_run_id().
orch --dry-run --once 2>/dev/null || true

run_log="$ORCH_STATE_DIR/run.log"
assert_contains "$(cat "$run_log" 2>/dev/null)" "RUN-START" \
    "run.log contains a RUN-START event"
assert_contains "$(cat "$run_log" 2>/dev/null)" "run_id=" \
    "RUN-START event carries run_id= field"

# Extract the run-ID from the log and verify it is non-empty.
extracted_run_id="$(grep "RUN-START" "$run_log" 2>/dev/null | head -1 | grep -o 'run_id=[^ ]*' | cut -d= -f2 || true)"
assert_ne "${extracted_run_id:-}" "" \
    "extracted run_id is non-empty"

cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== AC2: two sequential runs produce distinct run-IDs (no collision) ===${NC}\n"
# =============================================================================

new_env
orch --dry-run --once 2>/dev/null || true
run_log="$ORCH_STATE_DIR/run.log"

# Extract first run's ID.
id1="$(grep "RUN-START" "$run_log" 2>/dev/null | head -1 | grep -o 'run_id=[^ ]*' | cut -d= -f2 || true)"
assert_ne "${id1:-}" "" "first run: run_id non-empty"

# Second fresh invocation (same ORCH_STATE_DIR — persists run.log across runs).
orch --dry-run --once 2>/dev/null || true

# The log now has two RUN-START lines; extract the second one.
id2="$(grep "RUN-START" "$run_log" 2>/dev/null | tail -1 | grep -o 'run_id=[^ ]*' | cut -d= -f2 || true)"
assert_ne "${id2:-}" "" "second run: run_id non-empty"
assert_ne "${id1:-empty1}" "${id2:-empty2}" \
    "two sequential runs produce distinct run-IDs (artifact namespaces do not collide)"

cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== AC3: ORCH_RUN_ID_SEPARATION=0 restores legacy single-stream behavior ===${NC}\n"
# =============================================================================

new_env
# Default-on: run-ID enabled.
orch --dry-run --once 2>/dev/null || true
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "RUN-START" \
    "default (ORCH_RUN_ID_SEPARATION unset): RUN-START present"

# Now test with separation explicitly OFF.
new_env
export ORCH_RUN_ID_SEPARATION=0
orch --dry-run --once 2>/dev/null || true
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "RUN-START" \
    "ORCH_RUN_ID_SEPARATION=0: no RUN-START event (legacy single-stream)"
assert_not_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "run_id=" \
    "ORCH_RUN_ID_SEPARATION=0: no run_id= field in run.log"

cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== AC3b: ORCH_RUN_ID pin (explicit override) ===${NC}\n"
# =============================================================================

new_env
export ORCH_RUN_ID="pinned-test-run-001"
orch --dry-run --once 2>/dev/null || true
assert_contains "$(cat "$ORCH_STATE_DIR/run.log" 2>/dev/null)" "run_id=pinned-test-run-001" \
    "explicit ORCH_RUN_ID override is honoured verbatim"

cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}\n"
# =============================================================================

echo "Passed: $PASS / $TOTAL"
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}FAILED: $FAIL test(s)${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed${NC}"
fi
