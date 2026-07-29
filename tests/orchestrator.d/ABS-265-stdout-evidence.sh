# =============================================================================
# Per-story orchestrator test (ABS-265) — retain crashed-spawn stdout as evidence
# -----------------------------------------------------------------------------
# `source`d by tests/test-orchestrator.sh into the live harness (no shebang, no
# re-`set -e`, no re-source of the harness). Shares assert_*, PASS/FAIL/TOTAL,
# and REPO_ROOT / ORCH / STUB.
#
# Goal (ABS-265): on a crashed spawn the runner keeps the Result-JSON (stdout)
# as evidence — not just stderr — and records the CLI error `subtype` in the
# per-packet diag file, so the crash marker can NAME the failure class.
#
# run_spawn_cmd is exercised DIRECTLY (via `bash -c 'source $ORCH; …'`, the
# ABS-225 pattern) because attempt_spawn deletes `$pf.diag` right after reading
# it — so AC2 (the diag subtype line) is only observable at the spawn seam. The
# spawn's dependencies that would need a live tracker / worktree
# (resolve_spawn_model, resolve_seat_cwd) are overridden after the source.
# =============================================================================

echo -e "\n${CYAN}=== ABS-265 crashed-spawn stdout evidence (Result-JSON / subtype) ===${NC}"

# Drive run_spawn_cmd in isolation and report observable end state as markers.
#   $1 ORCH  $2 work-dir  $3 stub  $4 STUB_FAIL_RESULT_SUBTYPE (empty => success)
_abs265_probe() {
    bash -c '
        source "$1" >/dev/null 2>&1
        # Hermetic stub: drop any STUB_* knob an earlier monolith test leaked
        # into the environment, so only THIS probe controls the stub behavior.
        for _v in $(compgen -v STUB_ 2>/dev/null); do unset "$_v"; done
        # Neutralize deps that would reach a live tracker / worktree.
        resolve_spawn_model() { echo ""; }
        resolve_seat_cwd()    { echo ""; }
        workdir="$2"
        export ORCH_RUN_LOG="$workdir/run.log"
        export ORCH_WATCHDOG_IDLE=0      # legacy wall-time path — the stub exits at once
        export ORCH_AGENT_TIMEOUT=60     # generous; never trips
        export ORCH_SPAWN_CMD="$3"
        [ -n "$4" ] && export STUB_FAIL_RESULT_SUBTYPE="$4" STUB_FAIL_RC=7
        pf="$workdir/pkt.txt"; printf "context packet\n" > "$pf"
        rc=0
        run_spawn_cmd "be-developer" "ABS-265" "$pf" "Ready for QAS" >/dev/null 2>&1 || rc=$?
        echo "rc=$rc"
        ls "$pf".out.* >/dev/null 2>&1 && echo "OUT_KEPT" || echo "OUT_GONE"
        grep -q "^subtype=" "$pf.diag" 2>/dev/null && echo "DIAG_SUBTYPE=$(sed -n "s/^subtype=//p" "$pf.diag" | head -1)" || echo "DIAG_NO_SUBTYPE"
        grep -q "spawn stdout kept:" "$ORCH_RUN_LOG" 2>/dev/null && echo "LOG_STDOUT_KEPT" || echo "LOG_STDOUT_NONE"
    ' _abs265 "$1" "$2" "$3" "${4:-}" 2>/dev/null || true
}

# --- Crash path: rc!=0 WITH a Result-JSON on stdout (idle-kill crash class) ---
_abs265_crashdir="$(mktemp -d /tmp/abs265-crash-XXXXXX)"
_abs265_crash="$(_abs265_probe "$ORCH" "$_abs265_crashdir" "$STUB" "error_during_execution")"
assert_contains "$_abs265_crash" "rc=7" \
    "ABS-265: crashed spawn returns the stub's non-zero exit"
assert_contains "$_abs265_crash" "OUT_KEPT" \
    "ABS-265 AC1: crashed spawn's stdout (.out.*) file is retained, not deleted"
assert_contains "$_abs265_crash" "LOG_STDOUT_KEPT" \
    "ABS-265 AC1: run.log records a 'spawn stdout kept:' line"
assert_contains "$_abs265_crash" "DIAG_SUBTYPE=error_during_execution" \
    "ABS-265 AC2: \$pf.diag carries the Result-JSON subtype= line"
rm -rf "$_abs265_crashdir"

# --- Success path: rc=0 WITH a parseable handoff -> stdout removed as before ---
_abs265_okdir="$(mktemp -d /tmp/abs265-ok-XXXXXX)"
_abs265_ok="$(_abs265_probe "$ORCH" "$_abs265_okdir" "$STUB" "")"
assert_contains "$_abs265_ok" "rc=0" \
    "ABS-265 AC3: clean spawn returns exit 0"
assert_contains "$_abs265_ok" "OUT_GONE" \
    "ABS-265 AC3: success path (rc=0 + handoff) still removes the stdout file"
assert_contains "$_abs265_ok" "LOG_STDOUT_NONE" \
    "ABS-265 AC3: no 'spawn stdout kept:' line on a healthy run"
rm -rf "$_abs265_okdir"

unset -f _abs265_probe
