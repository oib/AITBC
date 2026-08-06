#!/bin/bash
# =============================================================================
# Test: staged-suite.sh completeness ledger + gate integrity (PILOT-50)
# =============================================================================
# Proves the HEAD-bound completeness ledger and the --verify gate, using the
# runner's SUITE_SELFTEST plan (trivial no-op stages `alpha beta gamma`) so the
# integrity logic is exercised deterministically in milliseconds — no real suite
# run. The two ticket falsifications are the core assertions here:
#   AC4  a subset of stages must NOT pass the gate (skipped stage => gate RED).
#        (AC5 — each REAL stage under the call limit — is a wall-clock property
#         measured on-box and recorded on the ticket, not asserted here.)
# Run from repo root: bash tests/tooling/test-staged-suite.sh
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNNER="$(cd "$SCRIPT_DIR/.." && pwd)/staged-suite.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/staged-suite-test-XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

# Run the runner in selftest mode with an isolated ledger. Echoes exit code.
run() { # <ledger> <args...>
    local ledger="$1"; shift
    SUITE_SELFTEST=1 SUITE_LEDGER="$ledger" bash "$RUNNER" "$@" >/dev/null 2>&1
    echo "$?"
}
run_fail() { # <ledger> <fail-csv> <args...>
    local ledger="$1" failcsv="$2"; shift 2
    SUITE_SELFTEST=1 SUITE_SELFTEST_FAIL="$failcsv" SUITE_LEDGER="$ledger" bash "$RUNNER" "$@" >/dev/null 2>&1
    echo "$?"
}

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1))
    fi
}

# --- 1. --list prints the deterministic plan ---------------------------------
L="$TEST_DIR/l1"
out=$(SUITE_SELFTEST=1 SUITE_LEDGER="$L" bash "$RUNNER" --list 2>&1)
assert_eq "$(echo "$out" | grep -cE '^\s+(alpha|beta|gamma) ')" "3" "--list shows all 3 plan stages"

# --- 2. all stages green at HEAD => gate GREEN (exit 0) ----------------------
L="$TEST_DIR/l2"
assert_eq "$(run "$L" --stage alpha)" "0" "stage alpha runs green"
assert_eq "$(run "$L" --stage beta)"  "0" "stage beta runs green"
assert_eq "$(run "$L" --stage gamma)" "0" "stage gamma runs green"
assert_eq "$(run "$L" --verify)"      "0" "verify GREEN when all stages pass at HEAD"

# --- 3. AC4 FALSIFICATION: a skipped stage must fail the gate ----------------
L="$TEST_DIR/l3"
run "$L" --stage alpha >/dev/null
run "$L" --stage beta  >/dev/null
# gamma deliberately NOT run
assert_eq "$(run "$L" --verify)" "1" "verify RED when a stage is SKIPPED (AC4)"

# --- 4. a FAILED stage must fail the gate (not just missing) -----------------
L="$TEST_DIR/l4"
run "$L" --stage alpha >/dev/null
run_fail "$L" beta beta --stage beta >/dev/null   # beta recorded as fail
run "$L" --stage gamma >/dev/null
assert_eq "$(run "$L" --verify)" "1" "verify RED when a stage FAILED"

# --- 5. sha-binding: pass records at a DIFFERENT HEAD do not count -----------
# Pre-seed the ledger with all-green at a FAKE sha; verify at the real HEAD must
# still be RED (the recorded passes belong to another commit). This is the
# self-invalidation property: any new commit forces a re-run.
L="$TEST_DIR/l5"
{ echo "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef alpha pass 0 x"
  echo "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef beta pass 0 x"
  echo "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef gamma pass 0 x"; } > "$L"
assert_eq "$(run "$L" --verify)" "1" "verify RED when passes are at a DIFFERENT HEAD (sha-bound)"
# ...and after running the stages at the REAL HEAD, it goes green.
run "$L" --stage alpha >/dev/null
run "$L" --stage beta  >/dev/null
run "$L" --stage gamma >/dev/null
assert_eq "$(run "$L" --verify)" "0" "verify GREEN once stages recorded at the CURRENT HEAD"

# --- 6. latest verdict wins: a re-run pass supersedes an earlier fail --------
L="$TEST_DIR/l6"
run_fail "$L" alpha alpha --stage alpha >/dev/null   # alpha fail first
run "$L" --stage alpha >/dev/null                    # then alpha passes
run "$L" --stage beta  >/dev/null
run "$L" --stage gamma >/dev/null
assert_eq "$(run "$L" --verify)" "0" "verify GREEN when a re-run PASS supersedes an earlier fail"

# --- Summary -----------------------------------------------------------------
echo ""
echo -e "Total: $TOTAL  ${GREEN}Passed: $PASS${NC}  ${RED}Failed: $FAIL${NC}"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "${GREEN}ALL TESTS PASSED${NC}"
exit 0
