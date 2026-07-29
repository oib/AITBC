#!/usr/bin/env bash
# =============================================================================
# suite-budget.sh — pure classification of a test-suite run against its budget
# -----------------------------------------------------------------------------
# ABS-603. Two pure helpers, no side effects, sourceable and unit-testable
# (tests/test-suite-budget.sh). They encode the gate's budget policy in ONE
# place so scripts/pre-release-check.sh and the tests agree by construction.
#
#   suite_reserve_pct <elapsed> <budget>
#       -> integer reserve percent = (budget - elapsed) * 100 / budget.
#          Negative when the suite ran over budget. Budget <= 0 -> 0.
#
#   classify_suite <rc> <elapsed> <budget> <warn_pct>
#       -> one verdict token on stdout:
#            pass              rc 0, reserve >= warn_pct
#            pass-low-reserve  rc 0, reserve <  warn_pct   (ABS-603 AC4 sensor)
#            ops-overbudget    rc 124 (watchdog killed it) (ABS-603 AC3 — NOT a
#                              test failure; operational, non-blocking)
#            fail              any other non-zero rc       (a real test failure)
# =============================================================================

suite_reserve_pct() {
    local elapsed="$1" budget="$2"
    [ "$budget" -gt 0 ] 2>/dev/null || { echo 0; return; }
    echo $(( (budget - elapsed) * 100 / budget ))
}

classify_suite() {
    local rc="$1" elapsed="$2" budget="$3" warn_pct="$4"
    if [ "$rc" -eq 124 ]; then
        echo ops-overbudget
        return
    fi
    if [ "$rc" -ne 0 ]; then
        echo fail
        return
    fi
    local reserve; reserve="$(suite_reserve_pct "$elapsed" "$budget")"
    if [ "$reserve" -lt "$warn_pct" ]; then
        echo pass-low-reserve
    else
        echo pass
    fi
}
