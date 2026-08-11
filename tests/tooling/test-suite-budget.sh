#!/usr/bin/env bash
# =============================================================================
# Test: scripts/lib/suite-budget.sh — reserve computation + run classification
# (ABS-603). Verifies the pure budget policy shared by pre-release-check.sh:
#   - the reserve sensor (AC4): a passing-but-slow run reads pass-low-reserve;
#   - the operational-vs-test distinction (AC3): a budget overrun (rc 124) reads
#     ops-overbudget, NOT fail, while a real non-zero rc reads fail.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/lib/suite-budget.sh
. "$SCRIPT_DIR/../scripts/lib/suite-budget.sh"

pass=0 fail=0
ok()   { pass=$((pass+1)); }
bad()  { fail=$((fail+1)); echo "FAIL: $1"; }

eq() { # eq <expected> <actual> <label>
    if [ "$1" = "$2" ]; then ok; else bad "$3 — expected [$1], got [$2]"; fi
}

# --- suite_reserve_pct ---------------------------------------------------------
eq 50  "$(suite_reserve_pct 900 1800)"  "half-budget => 50%"
eq 12  "$(suite_reserve_pct 790 900)"   "the Pilot-8 datapoint (790/900) => 12%"
eq 0   "$(suite_reserve_pct 1800 1800)" "at budget => 0%"
eq -10 "$(suite_reserve_pct 1980 1800)" "over budget => negative reserve"
eq 0   "$(suite_reserve_pct 100 0)"     "zero budget guarded => 0%"

# --- classify_suite <rc> <elapsed> <budget> <warn_pct> -------------------------
# healthy pass: rc 0, ample reserve
eq pass             "$(classify_suite 0 900 1800 25)"   "rc0 + 50% reserve => pass"
# AC4 sensor: passing but under the warn threshold
eq pass-low-reserve "$(classify_suite 0 790 900 25)"    "rc0 + 12% reserve => pass-low-reserve"
eq pass-low-reserve "$(classify_suite 0 1400 1800 25)"  "rc0 + 22% reserve => pass-low-reserve"
# boundary: reserve exactly at threshold is NOT low
eq pass             "$(classify_suite 0 1350 1800 25)"  "rc0 + exactly 25% reserve => pass"
# AC3: watchdog overrun is operational, not a test failure
eq ops-overbudget   "$(classify_suite 124 1801 1800 25)" "rc124 => ops-overbudget (AC3)"
# a real test failure still reads as fail (blocks)
eq fail             "$(classify_suite 1 10 1800 25)"     "rc1 => fail"
eq fail             "$(classify_suite 2 10 1800 25)"     "rc2 => fail"

echo "  Passed: $pass  Failed: $fail"
if [ "$fail" -gt 0 ]; then echo "FAIL: test-suite-budget"; exit 1; fi
echo "PASS: test-suite-budget (${pass} assertions)"
exit 0
