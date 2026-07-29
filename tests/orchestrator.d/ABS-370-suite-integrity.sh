# =============================================================================
# ABS-370 — story-include loop integrity (false-green hole)
# -----------------------------------------------------------------------------
# The include loop must CONTAIN a per-file abort: a `tests/orchestrator.d/*.sh`
# file that dies under `set -e` (an unexpected non-zero command — e.g. a stray
# same-status tracker transition — or a bare `exit`) must be recorded as a
# FAILURE and must NOT kill the loop or silently drop the files after it. Before
# ABS-370 such a death at the ABS-295->296 boundary skipped ~19 later includes
# yet still printed a green-looking tally while the process exited non-zero.
#
# This asserts the _run_d_include isolation contract directly (no full re-run of
# the suite): inject an aborting fixture, run it through the same wrapper the loop
# uses, and prove (a) execution continues past it and (b) it is counted as a
# failure. The injected fixture's bookkeeping is then RESTORED so this expected
# abort does not pollute the real suite tally.
# =============================================================================
echo -e "\n${CYAN}=== ABS-370 suite-integrity: an aborting include is caught, not silently dropped ===${NC}"

_abort_fixture="$(mktemp "${TMPDIR:-/tmp}/orch-abort-XXXXXX")"
cat >"$_abort_fixture" <<'FIX'
# A story include that aborts under set -e — same failure class as the ABS-295
# stray same-status transition: a bare non-zero command at top level.
false
echo "ABS-370 FIXTURE: this line MUST NOT run (set -e should have aborted above)"
FIX

# Snapshot the real counters so the deliberately-failing fixture leaves no trace.
# ABS-525: also SUPPRESS the wrapper's FAIL print — this induced failure is
# rolled back below, and the dispatcher's lost-fail guard enforces that every
# VISIBLE FAIL verdict line is covered by the shard tally. A visible-but-rolled-
# back FAIL would trip that guard; the assertions here read $FAIL, not stdout.
_p_before=$PASS _f_before=$FAIL _t_before=$TOTAL
_survived=0
_run_d_include "$_abort_fixture" >/dev/null 2>&1 || true
_survived=1                                   # reached => the abort was contained
_caught=0; [ "$FAIL" -gt "$_f_before" ] && _caught=1
# Restore: the injected fixture's failure was expected and must not count.
PASS=$_p_before; FAIL=$_f_before; TOTAL=$_t_before
rm -f "$_abort_fixture"

assert_eq "$_survived" "1" \
    "ABS-370: an aborting include does NOT kill the loop (execution continues past it)"
assert_eq "$_caught" "1" \
    "ABS-370: an aborting include is recorded as a FAILURE (no false green)"

unset _abort_fixture _p_before _f_before _t_before _survived _caught
