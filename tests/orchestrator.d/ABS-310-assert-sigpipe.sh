# =============================================================================
# ABS-310 — test-harness: pipefail leak + SIGPIPE-unsafe assert_contains
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/test-orchestrator.sh into the
# live harness — NO shebang, NO `set -e`, NO re-sourcing. In scope from the
# parent: assert_contains / assert_not_contains / assert_eq, PASS/FAIL/TOTAL,
# REPO_ROOT.
#
# Two composing defects made an assertion's verdict a function of input SIZE and
# include ORDER instead of the code under test:
#   D1  `source "$ORCH"` leaks `set -o pipefail` into the parent harness.
#   D2  `echo "$big" | grep -q` makes echo take SIGPIPE (grep short-circuits);
#       with D1 active PIPESTATUS becomes 141 -> a PRESENT match false-FAILs and
#       `set -e` aborts the run before its tally.
# This include proves both stay dead.
# =============================================================================

echo -e "\n${CYAN}ABS-310 — assert helpers are SIGPIPE-proof, pipefail is contained${NC}"

# --- AC1: D1 contained — pipefail is OFF where per-story includes are sourced --
# This file is sourced from the SAME loop that sources every ABS-215 include,
# AFTER the harness sourced scripts/orchestrator.sh. If the leak were live,
# `pipefail` would be ON right here.
if set -o | grep -q '^pipefail[[:space:]]*off$'; then _r310=0; else _r310=1; fi
assert_eq "$_r310" "0" "ABS-310 AC1: pipefail is OFF at the point per-story includes are sourced (D1 contained)"

# A ~256 KB input that DOES contain the needle (well past the ~64 KB pipe buffer
# where the old `echo | reader` shape took SIGPIPE).
_ABS310_NEEDLE="ABS-310-present-marker"
_ABS310_BIG="$(printf 'x%.0s' $(seq 1 262144))${_ABS310_NEEDLE}"

# --- AC2: D2 match path — forced pipefail ON, big present input => PASS --------
# Force the exact hostile condition (pipefail ON) and confirm the hardened
# helper still reports the present match, with no pipeline element exiting 141.
set -o pipefail
_p310_before="$PASS"
assert_contains "$_ABS310_BIG" "$_ABS310_NEEDLE" "ABS-310 AC2: 256KB input containing the needle PASSes under forced pipefail"
# The direct here-string match must also carry status 0 (no SIGPIPE=141).
grep -qF -- "$_ABS310_NEEDLE" <<<"$_ABS310_BIG"; _rc310="${PIPESTATUS[0]}"
set +o pipefail
assert_eq "$((PASS - _p310_before))" "1" "ABS-310 AC2: the big-input assertion counted exactly one PASS (no false FAIL)"
assert_eq "$_rc310" "0" "ABS-310 AC2: the here-string match exits 0, never 141 (no SIGPIPE)"

# --- AC3: D2 dump path — a FAILING assert on a big input does NOT abort --------
# A deliberately-failing assert_contains on a 256KB input must print its dump,
# bump FAIL, and let the suite CONTINUE (no `set -e` abort at exit 141). We run
# it under forced pipefail in a way that keeps the parent counters honest: the
# failing assertion is expected, so we roll the induced FAIL back afterwards.
set -o pipefail
_f310_before="$FAIL"
assert_contains "$_ABS310_BIG" "needle-that-is-absent-$$" "ABS-310 AC3 PROBE (expected to FAIL — dump path)" >/dev/null 2>&1
_f310_after="$FAIL"
set +o pipefail
# Reached this line at all => the suite did NOT abort on the failing big-input
# assert. Roll back the intentional FAIL and its TOTAL so the tally stays clean.
FAIL="$_f310_before"; TOTAL=$((TOTAL - 1))
assert_eq "$((_f310_after - _f310_before))" "1" "ABS-310 AC3: a failing big-input assert increments FAIL and the suite continues (no exit-141 abort)"

# --- AC5: no assertion helper still pipes a string into an early-closing reader
# Grep the hardened helper DEFINITIONS across test-orchestrator.sh + the 13
# file-slurping suites. Any surviving `echo "$X" | grep -q` / `echo "$X" | head`
# in helper code is the exact SIGPIPE shape this story removed.
_ABS310_FILES="test-orchestrator.sh test-migrate-project.sh test-claim-assign.sh \
test-kill-guard.sh e2e-workflow-v3.sh test-enrichment-writelight.sh \
test-epic-join-resting.sh test-local-main-guard.sh test-station-guard.sh \
test-packet-cache.sh test-done-gate.sh test-jira-tracker.sh test-agent-def-overlay.sh"
_hits310=0
for _tf in $_ABS310_FILES; do
    _p="$REPO_ROOT/tests/$_tf"
    [ -f "$_p" ] || continue
    if grep -nE 'echo "\$[A-Za-z_]+" \| grep -q|echo "\$[A-Za-z_]+" \| head' "$_p" >/dev/null 2>&1; then
        _hits310=$((_hits310 + 1))
    fi
done
assert_eq "$_hits310" "0" "ABS-310 AC5: no assertion helper pipes a captured string into an early-closing reader"

unset _ABS310_BIG _ABS310_NEEDLE _ABS310_FILES _r310 _rc310 _p310_before _f310_before _f310_after _hits310 _p310 _tf _p
