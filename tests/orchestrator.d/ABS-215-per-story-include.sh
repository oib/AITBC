# =============================================================================
# Per-story orchestrator test file (ABS-215) — TEMPLATE + self-check
# -----------------------------------------------------------------------------
# This file is `source`d by tests/tooling/test-orchestrator.sh, NOT run standalone.
# It therefore has NO shebang and MUST NOT re-source the harness or re-`set -e`
# — the parent script already did that. Everything below is in scope:
#   * assert helpers ...... assert_contains / assert_not_contains / assert_eq
#   * orchestrator driver .. orch, new_env, cleanup_env
#   * counters ............. PASS / FAIL / TOTAL (do not reset them)
#   * env/paths ............ REPO_ROOT, ORCH, TRACKER, STUB, TRACKER_CMD, ...
#
# HOW TO ADD NEW ORCHESTRATOR TESTS (implementer seats):
#   Copy this file to tests/orchestrator.d/<TICKET>-<slug>.sh and write your
#   asserts. Do NOT append them to the monolith. See docs/sop/TEST_SUITE_LAYOUT.md.
# =============================================================================

# Self-check: prove the include seam wired this file into the live harness.
assert_eq "$(type -t assert_contains)" "function" \
    "ABS-215: per-story include shares the harness (assert_contains in scope)"
assert_eq "$(type -t orch)" "function" \
    "ABS-215: per-story include shares the orch driver"

# A real end-to-end assertion running through the shared driver, to prove a
# story file can exercise the orchestrator exactly like the monolith body does.
new_env
_out=$(orch --dry-run --once 2>&1 || true)
assert_contains "$_out" "instance-id:" \
    "ABS-215: per-story file can drive orch --dry-run --once"
cleanup_env
