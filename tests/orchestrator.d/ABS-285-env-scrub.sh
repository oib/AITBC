# =============================================================================
# ABS-285 — test results must be a function of the COMMIT, not of the SEAT
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (no shebang, no re-`set -e`, shared
# assert helpers / counters — see docs/sop/TEST_SUITE_LAYOUT.md).
#
# THE DEFECT THIS PINS
# Tests that drive the real spawn seam did not scrub the ambient ORCH_* env, so
# the calling seat's environment leaked into the seam under test and changed the
# generated --agents JSON the assertions run against. An agent seat exports ~37
# ORCH_* vars, and at least two of them flip results:
#     ORCH_TOOLS=Bash,Read        -> 5 failures in test-agent-def-overlay
#     ORCH_OVERRIDES_DIR=/nowhere -> 6 further failures (disjoint; 11 together)
# So the same commit scored 24/24 or 19/24 depending on WHO ran the suite. That
# silently voids every "no new failures vs. the baseline" comparison in the repo
# — a baseline measured by seat A is not comparable to a branch run by seat B.
#
# It got through because nothing tested for it. This is that test.
#
# WHY A PREFIX-UNSET AND NOT AN ENUMERATED LIST
# ORCH_OVERRIDES_DIR was found only while fixing this; an enumerated unset list
# would have had to name it to catch it. `unset "${!ORCH_@}"` covers every ORCH_*
# that exists now or is added later, by construction.
# =============================================================================

_abs285_overlay="$REPO_ROOT/tests/tooling/test-agent-def-overlay.sh"

# Tally a run format-agnostically: the suite files use four different summary
# formats, so count the PASS/FAIL markers and the exit code instead of parsing
# a "Total: N" line that not every file prints.
_abs285_tally() {
    local out rc
    out=$(env "$@" bash "$_abs285_overlay" 2>&1)
    rc=$?
    out=$(printf '%s' "$out" | sed 's/\x1b\[[0-9;]*m//g')   # strip ANSI once
    printf 'pass=%s fail=%s rc=%s' \
        "$(printf '%s' "$out" | grep -cE '(^|[[:space:]])PASS([[:space:]]|$)')" \
        "$(printf '%s' "$out" | grep -cE '(^|[[:space:]])FAIL([[:space:]]|$)')" \
        "$rc"
}

# Scrubbed: EVERY ORCH_* gone from the child's env (subshell prefix-unset, not a
# list of four names — naming names is the very weakness this ticket removes).
_abs285_clean=$( unset "${!ORCH_@}"; _abs285_tally )

# Hostile: the seat env that actually broke it, both known leakers included.
_abs285_hostile=$(_abs285_tally \
    ORCH_TOOLS=Bash,Read \
    ORCH_MODEL=opus \
    ORCH_MAX_TURNS=1 \
    ORCH_OVERRIDES_DIR=/nonexistent-abs285)

# AC3: identical under both. This is the assertion that was missing.
assert_eq "$_abs285_hostile" "$_abs285_clean" \
    "ABS-285: test-agent-def-overlay scores identically under hostile ambient ORCH_* env"

# ...and identical-but-both-red would satisfy the line above, so pin green too.
# Asserts fail=0/rc=0 WITHOUT pinning the pass count: adding a case to the overlay
# test must not break this file, which does not care how many cases it has.
assert_contains "$_abs285_hostile" "fail=0 rc=0" \
    "ABS-285: test-agent-def-overlay is fully green under hostile ambient ORCH_* env"

# Structural guard for the other seam-/runner-driving files: each must keep its
# prefix-unset. Cheap (a grep), and it stops the scrub being silently dropped
# from a file whose immunity today is only accidental.
for _abs285_f in test-agent-def-overlay test-claim-mutex test-claim test-done-gate \
                 test-merge-wait test-jira-tracker test-kill-guard test-packet-cache \
                 test-resume-cwd test-station-guard; do
    assert_eq \
        "$(grep -cE '^unset "\$\{!ORCH_@\}"' "$REPO_ROOT/tests/tooling/${_abs285_f}.sh")" \
        "1" \
        "ABS-285: tests/tooling/${_abs285_f}.sh scrubs the ambient ORCH_* env"
done

unset _abs285_overlay _abs285_clean _abs285_hostile _abs285_f
