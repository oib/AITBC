# =============================================================================
# ABS-312 — liveness watchdog: full-standstill detection + one-shot self-heal
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/tooling/test-orchestrator.sh. In scope:
# assert_*, orch / tracker / new_env / cleanup_env / baseline, PASS/FAIL/TOTAL.
#
# The runner can go fully idle — 0 live seats while actionable work waits — with
# no single mechanism noticing (STUCK-DETECT is per-ticket/NOTIFY-only, backoffs
# are silent, parked tickets rest by design). The watchdog runs at the end of
# each reconcile sweep; after ORCH_STANDSTILL_SWEEPS standstill sweeps it
# self-heals ONCE per episode (resets expired/exhausted backoffs, reclaims
# orphaned locks) and, if still stuck, escalates loudly — never lifting a budget
# brake or a human gate.
# =============================================================================

tracker() { bash "$TRACKER" "$@"; }   # restore the real adapter (ABS-225 idiom)

# Multi-cycle dry-run: reconcile every cycle, no sleeps, bounded cycles.
# `|| true`: the capture must never abort the set -e harness on a non-zero
# runner exit (the assertions below judge the OUTPUT, not the exit code).
_ll_run() { ORCH_RECONCILE_ON_STARTUP=1 ORCH_RECONCILE_EVERY_N_CYCLES=1 \
            ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES="$1" orch --dry-run 2>/dev/null || true; }
_ll_runlog() { cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true; }

echo -e "\n${CYAN}ABS-312 — liveness watchdog${NC}"

# --- AC(a): 0 seats + a Ready-for-Development ticket behind an EXHAUSTED backoff
#     -> after N sweeps exactly one backoff reset (self-heal), and the spawn fires.
new_env
export ORCH_STANDSTILL_SWEEPS=3
T=$(tracker create --type ticket --title "ABS-312 backoff standstill" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
baseline   # drain the creation event
# Seed an exhausted backoff (delay at the max, deadline far ahead) so the ticket
# cannot dispatch and no seat is alive — a total standstill.
printf '%s\t%s\t%s\n' "Ready for Development" "$(( $(date -u +%s) + 1800 ))" "1800" \
    > "$ORCH_STATE_DIR/backoff-$T"
out="$(_ll_run 5)"
assert_contains "$(_ll_runlog)" "STANDSTILL-SELFHEAL" "ABS-312 AC(a): the watchdog self-heals once the standstill threshold is hit"
assert_eq "$(_ll_runlog | grep -c 'STANDSTILL-SELFHEAL')" "1" "ABS-312 AC(a)/(d): exactly ONE backoff reset per standstill episode"
assert_contains "$out" "INTENT SPAWN ticket=$T" "ABS-312 AC(a): after the backoff reset the ticket finally spawns"
[ -f "$ORCH_STATE_DIR/backoff-$T" ] && _bk=present || _bk=gone
assert_eq "$_bk" "gone" "ABS-312 AC(a): the exhausted backoff marker is cleared by the self-heal"
cleanup_env

# --- AC(b): 0 seats + every open ticket behind a HUMAN gate -> no self-heal, but
#     INTENT-STANDSTILL + an escalation naming the gate.
new_env
export ORCH_STANDSTILL_SWEEPS=3
T=$(tracker create --type ticket --title "ABS-312 human-gated" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "Blocked" --actor human --reason "waiting on external dependency" >/dev/null
baseline
out="$(_ll_run 4)"
assert_contains "$out" "INTENT STANDSTILL" "ABS-312 AC(b): a human-gated standstill escalates (INTENT STANDSTILL)"
assert_contains "$out" "Blocked" "ABS-312 AC(b): the escalation NAMES the blocking human gate"
assert_not_contains "$(_ll_runlog)" "STANDSTILL-SELFHEAL" "ABS-312 AC(b): a human gate is never self-healed (no budget/gate lifted)"
assert_eq "$(printf '%s' "$out" | grep -c 'INTENT STANDSTILL')" "1" "ABS-312 AC(b)/(d): the loud escalation fires once per episode, not every sweep"
cleanup_env

# --- AC(c): the queue is moving (a plain actionable ticket spawns each sweep) ->
#     the watchdog NEVER fires.
new_env
export ORCH_STANDSTILL_SWEEPS=3
T=$(tracker create --type ticket --title "ABS-312 healthy" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
baseline
out="$(_ll_run 5)"
assert_not_contains "$(_ll_runlog)" "STANDSTILL" "ABS-312 AC(c): a moving queue never triggers the watchdog"
assert_contains "$out" "INTENT SPAWN ticket=$T" "ABS-312 AC(c): the healthy ticket keeps spawning"
cleanup_env

# --- Off-switch: ORCH_LIVENESS_WATCHDOG=0 disables the watchdog entirely.
new_env
export ORCH_STANDSTILL_SWEEPS=3 ORCH_LIVENESS_WATCHDOG=0
T=$(tracker create --type ticket --title "ABS-312 off" --role be-developer)
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$T" "Blocked" --actor human --reason "gate" >/dev/null
baseline
out="$(_ll_run 4)"
assert_not_contains "$(_ll_runlog)" "STANDSTILL" "ABS-312: ORCH_LIVENESS_WATCHDOG=0 disables the watchdog (off-switch)"
unset ORCH_LIVENESS_WATCHDOG
cleanup_env

unset T out _bk
