#!/bin/bash
# =============================================================================
# Conformance test: backend-forge.sh — pr-state Done-gate adapter (ABS-350)
# =============================================================================
# Asserts the stdout contract of scripts/backend-forge.sh pr-state against
# HTTP response fixtures (no live backend or docker required — the backend forge
# API from Story 1 is stubbed via BACKEND_CURL). The fixture-based approach
# keeps this suite fast and runnable in any environment.
#
# Coverage (ACs from the ticket):
#   AC1 — pr-state <key> returns documented canonical output; the contract is
#         parseable by orchestrator.sh:story_pr_state (awk on $1 and $2).
#   AC2 — pr-state <missing-key> exits non-zero and writes to stderr.
#   AC3 — missing BACKEND_TOKEN / TRACKER_PROJECT exits non-zero + stderr.
#   AC5 — scripts/backend-forge.sh named in this file's assertion text.
#
# Run from repo root: bash tests/tooling/test-backend-forge.sh
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ADAPTER="$REPO_ROOT/scripts/backend-forge.sh"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected: '$2', got: '$1')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    TOTAL=$((TOTAL + 1))
    if echo "$1" | grep -qF -- "$2"; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected to find: $2)"; echo "$1" | head -5 | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
assert_exit_code() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -eq "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected exit $2, got $1)"; FAIL=$((FAIL + 1)); fi
}
assert_nonzero_exit() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -ne 0 ]; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $2 (expected non-zero exit, got 0)"; FAIL=$((FAIL + 1)); fi
}

# --- Build a fake-curl stub (BACKEND_CURL seam) ------------------------------
# Simulates the backend pr-state API (ABS-230 S3 route) so the suite runs with
# no live backend. Parses -o <body_file> and the URL (last http* arg), writes
# the fixture body to the temp file, and prints the HTTP status code on stdout —
# byte-identical to what real curl outputs with -w '%{http_code}'.
TMPDIR_RUN="$(mktemp -d /tmp/bgf-conf-XXXXXX)"
FAKE_CURL="$TMPDIR_RUN/fake-curl.sh"
cat > "$FAKE_CURL" <<'FAKECURL'
#!/usr/bin/env bash
# Fake curl stub for backend-forge.sh conformance tests.
body_file=""
url=""
while [ $# -gt 0 ]; do
    case "$1" in
        --config|-sS|-s|-S) shift ;;
        -X|-w|-H) shift 2 ;;
        -o) body_file="$2"; shift 2 ;;
        http://*|https://*) url="$1"; shift ;;
        *) shift ;;
    esac
done
case "$url" in
    */items/MERGED-1/pr-state)
        [ -n "$body_file" ] && printf 'MERGED #42 ci=passed mergeable=true\n' > "$body_file"
        printf '200'
        ;;
    */items/OPEN-1/pr-state)
        [ -n "$body_file" ] && printf 'OPEN #99 ci=pending mergeable=false\n' > "$body_file"
        printf '200'
        ;;
    */items/DECLINED-1/pr-state)
        [ -n "$body_file" ] && printf 'DECLINED #7 ci=failed mergeable=false\n' > "$body_file"
        printf '200'
        ;;
    */items/NONE-1/pr-state)
        [ -n "$body_file" ] && printf 'NONE\n' > "$body_file"
        printf '200'
        ;;
    */items/MISSING-1/pr-state)
        [ -n "$body_file" ] && printf 'no such item: MISSING-1\n' > "$body_file"
        printf '404'
        ;;
    */items/AUTH-FAIL/pr-state)
        [ -n "$body_file" ] && printf 'Unauthorized\n' > "$body_file"
        printf '401'
        ;;
    *)
        [ -n "$body_file" ] && printf 'internal error\n' > "$body_file"
        printf '500'
        ;;
esac
exit 0
FAKECURL
chmod +x "$FAKE_CURL"

cleanup() { rm -rf "$TMPDIR_RUN"; }
trap cleanup EXIT

forge() { bash "$ADAPTER" "$@"; }

export BACKEND_URL="http://localhost:18420"
export BACKEND_TOKEN="test-forge-token"
export TRACKER_PROJECT="TESTPROJ"
export BACKEND_CURL="$FAKE_CURL"

# =============================================================================
echo -e "${CYAN}=== Test 0: adapter file + syntax (AC5) ===${NC}\n"
# AC5: scripts/backend-forge.sh exists, is executable, and named in an assertion.
assert_contains "$ADAPTER" "backend-forge.sh" "scripts/backend-forge.sh is named in the assertion (AC5)"
ec=0; [ -f "$ADAPTER" ] || ec=1
assert_exit_code "$ec" 0 "scripts/backend-forge.sh exists"
ec=0; [ -x "$ADAPTER" ] || ec=1
assert_exit_code "$ec" 0 "scripts/backend-forge.sh is executable"
bash -n "$ADAPTER" >/dev/null 2>&1
assert_exit_code $? 0 "scripts/backend-forge.sh has valid bash syntax"

# =============================================================================
echo -e "\n${CYAN}=== Test 1: pr-state stdout contract (AC1) ===${NC}\n"
# Canonical output must be parseable by story_pr_state (awk '{print toupper($1)}'
# for STATE and awk '{print $2}' for REF) — the Done-gate contract.

out=$(forge pr-state MERGED-1)
assert_eq "$(printf '%s' "$out" | awk '{print toupper($1)}')" "MERGED" "MERGED: story_pr_state STATE = MERGED"
assert_eq "$(printf '%s' "$out" | awk '{print $2}')"          "#42"    "MERGED: story_pr_state REF = #42"
assert_contains "$out" "ci=passed"      "MERGED: ci field present in output"
assert_contains "$out" "mergeable=true" "MERGED: mergeable field present in output"

out=$(forge pr-state OPEN-1)
assert_eq "$(printf '%s' "$out" | awk '{print toupper($1)}')" "OPEN"  "OPEN: STATE = OPEN"
assert_eq "$(printf '%s' "$out" | awk '{print $2}')"          "#99"   "OPEN: REF = #99"
assert_contains "$out" "mergeable=false" "OPEN+pending: mergeable=false"

out=$(forge pr-state DECLINED-1)
assert_eq "$(printf '%s' "$out" | awk '{print toupper($1)}')" "DECLINED" "DECLINED: STATE = DECLINED"

out=$(forge pr-state NONE-1)
assert_eq "$(printf '%s' "$out" | awk '{print $1}')" "NONE" "NONE: STATE field is NONE"

# =============================================================================
echo -e "\n${CYAN}=== Test 2: missing item — non-zero exit + stderr (AC2) ===${NC}\n"
ec=0; err_out=$(forge pr-state MISSING-1 2>&1 >/dev/null) || ec=$?
assert_nonzero_exit "$ec"    "pr-state <missing-key> exits non-zero (AC2)"
assert_contains "$err_out" "MISSING-1" "pr-state <missing-key> names the key in stderr (AC2)"

# =============================================================================
echo -e "\n${CYAN}=== Test 3: missing env vars — non-zero exit + stderr (AC3) ===${NC}\n"
ec=0; err_out=$(BACKEND_TOKEN="" forge pr-state MERGED-1 2>&1) || ec=$?
assert_nonzero_exit "$ec" "missing BACKEND_TOKEN exits non-zero (AC3)"
assert_contains "$err_out" "BACKEND_TOKEN" "missing BACKEND_TOKEN names the var in stderr (AC3)"

ec=0; err_out=$(TRACKER_PROJECT="" forge pr-state MERGED-1 2>&1) || ec=$?
assert_nonzero_exit "$ec" "missing TRACKER_PROJECT exits non-zero (AC3)"
assert_contains "$err_out" "TRACKER_PROJECT" "missing TRACKER_PROJECT names the var in stderr (AC3)"

# =============================================================================
echo -e "\n${CYAN}=== Test 4: auth error — non-zero exit + stderr ===${NC}\n"
ec=0; err_out=$(forge pr-state AUTH-FAIL 2>&1 >/dev/null) || ec=$?
assert_nonzero_exit "$ec" "auth failure (401) exits non-zero"
assert_contains "$err_out" "auth" "auth failure writes to stderr mentioning auth"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    echo -e "\n  ${RED}CONFORMANCE FAILED — stdout contract deviation is a Done-gate risk${NC}\n"
    exit 1
fi
echo -e "  Failed: 0"
echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
exit 0
