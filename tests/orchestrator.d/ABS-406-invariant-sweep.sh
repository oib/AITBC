# =============================================================================
# ABS-406 — degraded wait-state-watchdog: invariant sweep on the jira/mock lane
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/tooling/test-orchestrator.sh into the
# live harness — NO shebang, NO `set -e`, NO re-sourcing. In scope from the
# parent: assert_contains / assert_eq / assert_not_contains, PASS/FAIL/TOTAL,
# REPO_ROOT / ORCH / TRACKER, new_env / cleanup_env, and every exported env var.
#
# The ABS-391 watchdog is v3-backend-native; on the jira/mock profiles the same
# silent wait-state mis-booking class (ABS-354 `Ready for Merge` with no PR;
# ABS-333 `Docs` released before the human merge) was unguarded. invariant_sweep
# is the degraded parity port: it reads the SHARED declarative rule table
# (ORCH_INVARIANT_RULES), judges evidence over the forge seam + seat lock, and on
# a violation raises ONE loud `kind: invariant-violation` comment — detection
# only, never a transition (AC5 / ADR-A-0004). This suite drives real tickets to
# each wait-state status through the REAL mock adapter (sourced inside a `bash -c`
# subprocess, like ABS-284, so the harness shell is never clobbered) and asserts
# the tracker comment, the unchanged status, and the sweep's tracker call set.
# =============================================================================

# _abs406_sweep <target-status> <forge-state> [extra] — drive a fresh ticket to
# <target-status> on the REAL mock adapter, run invariant_sweep LIVE with the
# forge seam stubbed to <forge-state> ("OPEN #7" / "MERGED #7" / "NONE"), and
# print four structured lines the parent asserts on:
#   STATUS=<status re-read from the adapter>  VIOL=<# invariant-violation comments>
#   CALLS=<space-joined tracker subcommands the sweep issued>  REASON=<signal body>
# [extra] tokens (space-joined): `seat` = hold an active seat lock during the
# sweep; `twice` = run the sweep twice (idempotency); `aged` = advance ORCH_NOW
# far past the grace window. All inside one subprocess so a sourced
# orchestrator.sh cannot leak into the harness shell.
_abs406_sweep() {
    ABS406_STATUS="$1" ABS406_FORGE="$2" ABS406_EXTRA="${3:-}" \
    bash -c '
        source "$1" >/dev/null 2>&1
        MODE="live"; FORGE_CMD="stub"
        export ORCH_RUN_LOG="$ABS406_RUNLOG"; : > "$ORCH_RUN_LOG" 2>/dev/null || true
        forge() { printf "%s\n" "$ABS406_FORGE"; }
        id="$(tracker create --type ticket --title "ABS-406 $ABS406_STATUS")"
        steps="Ready for Development
In Progress
In Review
In Test
Ready for Human Acceptance"
        case "$ABS406_STATUS" in
          "Ready for Merge") steps="$steps
Ready for Merge" ;;
          "Merging") steps="$steps
Story Acceptance
Merging" ;;
          "Docs") steps="$steps
Story Acceptance
Merging
Docs" ;;
        esac
        while IFS= read -r s; do [ -n "$s" ] || continue
            tracker transition "$id" "$s" --actor test --reason step >/dev/null 2>&1
        done <<STEPS
$steps
STEPS
        case " $ABS406_EXTRA " in *" seat "*) mkdir -p "$(lock_dir_for "$id")" ;; esac
        case " $ABS406_EXTRA " in *" aged "*) export ORCH_NOW=$(( $(date -u +%s) + 100000 )) ;; esac
        st="$(ticket_status "$id")"
        rows="$(printf "%s\t%s\t%s\t%s" "$id" "ticket" "$st" "title")"
        # Spy: record every tracker subcommand the sweep issues (AC5 proof).
        _calls=""; tracker() { _calls="$_calls $1"; bash "$TRACKER_CMD" "$@"; }
        invariant_sweep "$rows" >/dev/null 2>&1
        case " $ABS406_EXTRA " in *" twice "*) invariant_sweep "$rows" >/dev/null 2>&1 ;; esac
        dump="$(bash "$TRACKER_CMD" get "$id")"
        printf "STATUS=%s\n" "$(printf "%s\n" "$dump" | awk -F": " "/^status: /{print \$2; exit}")"
        printf "VIOL=%s\n" "$(printf "%s\n" "$dump" | grep -c "kind: invariant-violation")"
        printf "CALLS=%s\n" "$_calls"
        printf "REASON=%s\n" "$(printf "%s\n" "$dump" | grep -A2 "kind: invariant-violation" | tr "\n" " ")"
    ' _abs406 "$ORCH"
}

echo -e "\n${CYAN}=== ABS-406 degraded wait-state invariant sweep ===${NC}"

# --- AC2: replayed ABS-354 — `Ready for Merge` with NO open MR -> loud signal.
new_env
export ABS406_RUNLOG="$TEST_DIR/ac354.log"
out="$(_abs406_sweep "Ready for Merge" "NONE")"
assert_contains "$out" "VIOL=1" "ABS-406 AC2 (ABS-354): Ready for Merge with no MR raises exactly one invariant-violation signal"
assert_contains "$out" "no PR mirrored" "ABS-406 AC2: the signal names the missing evidence"
assert_contains "$out" "STATUS=Ready for Merge" "ABS-406 AC2/AC5: the ticket did NOT move — detection only"
cleanup_env

# --- AC3: replayed ABS-333 — `Docs` with an MR still OPEN (unmerged) -> signal.
new_env
export ABS406_RUNLOG="$TEST_DIR/ac333.log"
out="$(_abs406_sweep "Docs" "OPEN #7")"
assert_contains "$out" "VIOL=1" "ABS-406 AC3 (ABS-333): Docs with an unmerged MR raises an invariant-violation signal"
assert_contains "$out" "not merged" "ABS-406 AC3: the signal names why (PR open, not merged)"
assert_contains "$out" "STATUS=Docs" "ABS-406 AC3/AC5: the ticket rests in Docs — never transitioned"
cleanup_env

# --- AC4: NO false positive on the regular cases (evidence present each time).
new_env
export ABS406_RUNLOG="$TEST_DIR/ac4.log"
out="$(_abs406_sweep "Ready for Merge" "OPEN #7")"
assert_contains "$out" "VIOL=0" "ABS-406 AC4: Ready for Merge WITH an open MR raises NO signal"
out="$(_abs406_sweep "Merging" "NONE" "seat")"
assert_contains "$out" "VIOL=0" "ABS-406 AC4: Merging with an active seat (within grace) raises NO signal"
out="$(_abs406_sweep "Docs" "MERGED #7")"
assert_contains "$out" "VIOL=0" "ABS-406 AC4: Docs WITH a merged MR raises NO signal"
cleanup_env

# --- AC1 (Merging/branch-or-seat-after-grace): no branch, no seat, WITHIN grace
#     -> no signal; the SAME state past the grace window -> a signal.
new_env
export ABS406_RUNLOG="$TEST_DIR/acgrace.log"
out="$(_abs406_sweep "Merging" "NONE")"
assert_contains "$out" "VIOL=0" "ABS-406 AC1: Merging with no branch/seat but within grace raises NO signal (just-entered story)"
out="$(_abs406_sweep "Merging" "NONE" "aged")"
assert_contains "$out" "VIOL=1" "ABS-406 AC1: Merging with no branch/seat PAST grace raises a signal"
assert_contains "$out" "no branch (PR) and no active seat" "ABS-406 AC1: the grace-expired signal names the missing branch-or-seat evidence"
cleanup_env

# --- AC5: the sweep NEVER calls a transition op (detect-only, ADR-A-0004).
new_env
export ABS406_RUNLOG="$TEST_DIR/ac5.log"
out="$(_abs406_sweep "Ready for Merge" "NONE")"
calls="$(printf '%s\n' "$out" | sed -n 's/^CALLS=//p')"
assert_contains "$calls" "comment" "ABS-406 AC5: the sweep DID act (posted a comment) on the violation"
assert_not_contains "$calls" "transition" "ABS-406 AC5: the sweep issued NO transition op — human-only boundary intact"
cleanup_env

# --- AC6: idempotent — repeated sweeps on the same unchanged violation raise
#     ONE signal per episode, not one per sweep.
new_env
export ABS406_RUNLOG="$TEST_DIR/ac6.log"
out="$(_abs406_sweep "Ready for Merge" "NONE" "twice")"
assert_contains "$out" "VIOL=1" "ABS-406 AC6: two sweeps over the same unchanged violation still leave exactly ONE signal"
cleanup_env

# --- Off-switch: ORCH_INVARIANT_SWEEP=0 disables the sweep entirely.
new_env
export ABS406_RUNLOG="$TEST_DIR/acoff.log"
export ORCH_INVARIANT_SWEEP=0
out="$(_abs406_sweep "Ready for Merge" "NONE")"
assert_contains "$out" "VIOL=0" "ABS-406: ORCH_INVARIANT_SWEEP=0 disables the sweep (off-switch)"
unset ORCH_INVARIANT_SWEEP
cleanup_env

unset out calls
