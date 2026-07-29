# =============================================================================
# ABS-525 — shard aggregation: a FAIL in any shard MUST fail the suite
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/test-orchestrator.sh into the
# live harness — NO shebang, NO `set -e`, NO re-sourcing. In scope from the
# parent: assert_contains / assert_eq, PASS/FAIL/TOTAL, REPO_ROOT, RED/NC.
#
# Befund (2026-07-21, worktree ABS-518-batch2, TEST_JOBS=4): one assertion
# printed FAIL yet the aggregate read "Passed: 1231" only and the suite exited
# 0. The committed dispatcher could not be made to lose a fail in any exercised
# class, so ABS-525 hardened it anyway: (1) slices are pre-cut at dispatch time
# (a mid-run edit/checkout of the suite file can no longer tear the shard
# slices), and (2) a LOST-FAIL GUARD in the aggregator counts the VISIBLE FAIL
# verdict lines per shard log and forces a non-green exit when they exceed the
# shard's tallied sentinel FAIL.
#
# This include pins the aggregation contract end-to-end against the REAL
# dispatcher code: it assembles a synthetic mini-suite out of the real file's
# own header (harness + dispatcher), a 4-block toy body, and the real serial
# epilogue — then runs it sharded (TEST_JOBS=2) three times:
#   (A) one counted failing assert    -> exit 1, "Failed: 1"
#   (B) one PRINTED-but-untallied FAIL verdict (the incident's symptom shape,
#       simulated via a bare echo)    -> exit 1 via the lost-fail guard
#   (C) all-green control            -> exit 0, "ALL TESTS PASSED"
# =============================================================================
echo -e "\n${CYAN}=== ABS-525 shard lost-fail guard: a shard FAIL can never aggregate green ===${NC}"

_525_suite="$REPO_ROOT/tests/test-orchestrator.sh"
_525_dir="$(mktemp -d "${TMPDIR:-/tmp}/orch-525-XXXXXX")"

# The synthetic assembly depends on the body markers; fail loudly if they move.
_525_markers=$(grep -cE '^#@SHARD-BODY-(START|END)@$' "$_525_suite" || true)
assert_eq "$_525_markers" "2" "ABS-525: suite body markers present (synthetic assembly precondition)"

# Real header (gate, scrub, assert helpers, dispatcher, BODY-START marker) +
# real serial epilogue (BODY-END marker to EOF). Only the body is synthetic.
sed -n '1,/^#@SHARD-BODY-START@$/p' "$_525_suite" > "$_525_dir/header.sh"
sed -n '/^#@SHARD-BODY-END@$/,$p'   "$_525_suite" > "$_525_dir/epilogue.sh"

# The copied header sources tests/sandbox-guard.sh relative to its OWN location
# (PILOT-46), so the synthetic suite needs the guard beside it. Without this the
# source fails in the temp dir and `set -e` (header line 16) kills the synthetic
# run before it prints anything — all three assertions below then fail for a
# reason that has nothing to do with the shard guard they test.
cp "$REPO_ROOT/tests/sandbox-guard.sh" "$_525_dir/sandbox-guard.sh"

# Toy body: four self-contained blocks with real new_env/cleanup_env boundaries
# (the dispatcher cuts at '^cleanup_env$' lines, so 2 shards get real work).
_525_mkbody() {  # $1 = variant: pass | counted-fail | phantom-fail
    local variant="$1" mid=""
    case "$variant" in
        counted-fail) mid='assert_eq "one" "two" "SYN-525 forced counted FAIL (expected)"' ;;
        phantom-fail) mid='echo -e "  ${RED}FAIL${NC} SYN-525 phantom verdict — printed but never tallied"' ;;
        *)            mid='assert_eq "ok" "ok" "SYN-525 mid block passes"' ;;
    esac
    cat <<SYNBODY
new_env
assert_eq "ok" "ok" "SYN-525 block1 passes"
cleanup_env

new_env
$mid
cleanup_env

new_env
assert_eq "ok" "ok" "SYN-525 block3 passes"
cleanup_env

new_env
assert_eq "ok" "ok" "SYN-525 block4 passes"
cleanup_env

SYNBODY
}

# Run one synthetic variant sharded; sets _525_rc and _525_out.
# _SHARD_SLICE/_SHARD_RANGE are exported into shard children by the outer
# dispatcher and MUST be dropped, or the synthetic run would treat itself as a
# shard child of the OUTER suite. ORCH_STATE_DIR is pinned to a fresh empty dir
# so the ABS-335 live-state gate can never see a live self-hosting run.
_525_run() {
    local variant="$1" syn="$_525_dir/syn-$1.sh"
    { cat "$_525_dir/header.sh"; _525_mkbody "$variant"; cat "$_525_dir/epilogue.sh"; } > "$syn"
    _525_rc=0
    _525_out=$(env -u _SHARD_SLICE -u _SHARD_RANGE -u LIVESTATE_GUARD_SELFTEST \
        ORCH_STATE_DIR="$_525_dir/state-$variant" TEST_JOBS=2 \
        bash "$syn" 2>&1) || _525_rc=$?
}

# --- (A) a counted failing assert in a shard fails the aggregate --------------
_525_run counted-fail
assert_eq "$_525_rc" "1" "ABS-525 A: a failing assert in a shard -> suite exit 1 (TEST_JOBS=2)"
assert_contains "$_525_out" "Failed: 1" "ABS-525 A: the aggregate summary shows the non-zero Failed count"
assert_not_contains "$_525_out" "ALL TESTS PASSED" "ABS-525 A: a failing shard can never print the green banner"

# --- (B) the incident shape: FAIL printed, never tallied -> guard trips -------
_525_run phantom-fail
assert_eq "$_525_rc" "1" "ABS-525 B: a printed-but-untallied FAIL verdict -> suite exit 1 (lost-fail guard)"
assert_contains "$_525_out" "lost-fail guard" "ABS-525 B: the guard names itself in the failure line"
assert_not_contains "$_525_out" "ALL TESTS PASSED" "ABS-525 B: the phantom FAIL can never aggregate green"

# --- (C) control: all-green synthetic run still exits 0 -----------------------
_525_run pass
assert_eq "$_525_rc" "0" "ABS-525 C: all-green sharded run exits 0 (guard has no false positive)"
assert_contains "$_525_out" "ALL TESTS PASSED" "ABS-525 C: the green banner still prints"

rm -rf "$_525_dir"
unset _525_suite _525_dir _525_markers _525_rc _525_out
unset -f _525_mkbody _525_run
