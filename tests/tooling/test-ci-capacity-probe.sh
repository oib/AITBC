#!/usr/bin/env bash
# =============================================================================
# Test: ci-capacity-probe.sh + the ops-sweep ci-capacity sensor (ABS-595)
# =============================================================================
# The regression this pins (Pilot 8, 2026-07-26/27): a shipped `.gitlab-ci.yml`
# on a project with NO runner makes every MR pipeline die in the stuck-timeout
# (failure_reason=stuck_or_timeout_failure), the RTE seat WAITS on a pipeline
# that can never finish, and the whole automerge lane stalls overnight.
#
# Pinned contract:
#   AC2  classify() DISTINGUISHES "infra can't run it" (0 runners / stuck_or_
#        timeout / runner_system_failure -> NO-CAPACITY, exit 2, do NOT block)
#        from "a job genuinely FAILED" (script_failure w/ runners -> RED, exit 1).
#   AC3  the headline case — MR with stuck_or_timeout_failure AND 0 runners —
#        classifies as NO-CAPACITY, so the merge lane does NOT stall on it.
#   AC1  `wait` is time-bounded: a forever-PENDING pipeline yields the NAMED
#        PIPELINE-WAIT-TIMEOUT (exit 124), never a silent unbounded wait.
#   AC4  the ops-sweep `ci-capacity` sensor fires ONCE when a CI config exists
#        with zero runners, and stays silent otherwise (config-less / runners
#        present / count unknown).
#
# Self-contained: bash 3.2 + BSD/GNU tools. Run from repo root:
#   bash tests/tooling/test-ci-capacity-probe.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROBE="$REPO_ROOT/scripts/ci-capacity-probe.sh"
SENSORS="$REPO_ROOT/scripts/ops-sweep-sensors.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    local out="$1" needle="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$needle" <<<"$out"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $needle)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -4 <<<"$out" | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
# classify_rc <status> <reason> <runners> -> echoes the exit code
classify_rc() { bash "$PROBE" classify "$1" "$2" "$3" >/dev/null 2>&1; echo $?; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/ci-capacity-XXXXXX")"
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

# =============================================================================
echo -e "${CYAN}=== ci-capacity-probe (ABS-595) ===${NC}\n"
echo -e "${CYAN}AC2. classify distinguishes infra-stuck from a real red${NC}"
# =============================================================================
assert_eq "$(classify_rc success - 1)"                        "0" "success -> GREEN (0)"
assert_eq "$(classify_rc failed script_failure 3)"            "1" "failed+script_failure, runners present -> RED (1)"
assert_eq "$(classify_rc failed runner_system_failure 3)"     "2" "failed+runner_system_failure -> NO-CAPACITY (2)"
assert_eq "$(classify_rc pending - 0)"                        "2" "pending with 0 runners -> NO-CAPACITY (2)"
assert_eq "$(classify_rc running - 1)"                        "3" "running with runners -> PENDING (3)"
# a real red and an infra-stuck must NOT collapse to the same verdict
r_red="$(classify_rc failed script_failure 3)"; r_infra="$(classify_rc failed stuck_or_timeout_failure 0)"
assert_eq "$([ "$r_red" != "$r_infra" ] && echo distinct || echo same)" "distinct" \
    "a genuine red and an infra-stuck are DIFFERENT verdicts"

# =============================================================================
echo -e "\n${CYAN}AC3. headline case: stuck_or_timeout_failure + 0 runners does NOT stall the lane${NC}"
# =============================================================================
out="$(bash "$PROBE" classify failed stuck_or_timeout_failure 0)"; rc=$?
assert_eq "$rc" "2" "stuck_or_timeout_failure + 0 runners -> exit 2 (NO-CAPACITY, non-blocking)"
assert_contains "$out" "NO-CAPACITY" "verdict names NO-CAPACITY (infra, not the story's fault)"
# The lane is 'not stalled' == the verdict is TERMINAL (0/1/2), never PENDING(3)
# for this input; a PENDING here is exactly the forever-wait the incident hit.
assert_eq "$([ "$rc" -ne 3 ] && echo terminal || echo pending)" "terminal" \
    "the verdict is terminal, so the RTE seat stops waiting instead of burning budget"

# =============================================================================
echo -e "\n${CYAN}AC1. wait is time-bounded -> a NAMED pipeline-wait timeout${NC}"
# =============================================================================
# poll cmd that NEVER reaches a terminal state (a runner-less pipeline stays 'running')
out="$(bash "$PROBE" wait 1 1 printf 'running - 1')"; rc=$?
assert_eq "$rc" "124" "forever-PENDING wait exits 124 (GNU-timeout code, ABS-573 contract)"
assert_contains "$out" "PIPELINE-WAIT-TIMEOUT" "timeout is a NAMED state, not a silent budget burn"
# a terminal verdict short-circuits the wait immediately (no burned budget)
out="$(bash "$PROBE" wait 30 1 printf 'failed stuck_or_timeout_failure 0')"; rc=$?
assert_eq "$rc" "2" "wait returns NO-CAPACITY at once when the pipeline can't run"
assert_contains "$out" "NO-CAPACITY" "wait surfaces the NO-CAPACITY verdict"

# =============================================================================
echo -e "\n${CYAN}AC4. ops-sweep ci-capacity sensor fires ONCE, loudly${NC}"
# =============================================================================
CIREPO="$TMP/ci"; git init -q "$CIREPO"; : > "$CIREPO/.gitlab-ci.yml"
BARE="$TMP/bare"; git init -q "$BARE"   # no CI config

# config present + 0 runners -> exactly one finding
out="$(OPS_REPO="$CIREPO" OPS_RUNNER_COUNT=0 bash "$SENSORS" ci-capacity)"; rc=$?
assert_eq "$rc" "0" "sensor exits 0 even with a finding (diagnosis, not a gate)"
assert_contains "$out" "ci-capacity" "fires the ci-capacity class"
assert_contains "$out" "runners=0" "evidence names the zero-runner signature"
assert_eq "$(printf '%s' "$out" | grep -c 'ci-capacity')" "1" "reports the capacity gap exactly ONCE"

# config present + runners available -> silent
out="$(OPS_REPO="$CIREPO" OPS_RUNNER_COUNT=4 bash "$SENSORS" ci-capacity)"
assert_eq "$(printf '%s' "$out" | grep -c . || true)" "0" "silent when runners ARE available"

# config present + count unknown -> skip (no false alarm)
out="$(OPS_REPO="$CIREPO" bash "$SENSORS" ci-capacity)"
assert_eq "$(printf '%s' "$out" | grep -c . || true)" "0" "silent when the runner count is unknown"

# no CI config -> skip (no capacity to worry about)
out="$(OPS_REPO="$BARE" OPS_RUNNER_COUNT=0 bash "$SENSORS" ci-capacity)"
assert_eq "$(printf '%s' "$out" | grep -c . || true)" "0" "silent when no CI config is shipped"

# the detector is registered in the driver
assert_contains "$(bash "$SENSORS" --list)" "ci-capacity" "ci-capacity listed in --list"

# =============================================================================
echo -e "\n${CYAN}usage errors fail closed (exit 64)${NC}"
# =============================================================================
bash "$PROBE" classify >/dev/null 2>&1; assert_eq "$?" "64" "classify with no args -> 64"
bash "$PROBE" bogus     >/dev/null 2>&1; assert_eq "$?" "64" "unknown subcommand -> 64"

# =============================================================================
echo -e "\n${CYAN}=== $PASS/$TOTAL passed ===${NC}"
[ "$FAIL" -eq 0 ] || { echo -e "${RED}$FAIL failed${NC}"; exit 1; }
