# =============================================================================
# ABS-225 progress-based watchdog — idle detection over hard wall-time
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/tooling/test-orchestrator.sh into the
# live harness — NO shebang, NO `set -e`, NO re-sourcing. In scope from the
# parent: assert_contains / assert_not_contains / assert_eq, orch / tracker /
# new_env / cleanup_env / baseline, PASS/FAIL/TOTAL, REPO_ROOT / ORCH / STUB.
#
# A seat is killed on proven INACTIVITY (ORCH_AGENT_IDLE_TIMEOUT), with an
# absolute MAX_LIFETIME backstop, instead of a static wall-time ceiling every
# larger ticket outgrows (ABS-151 turn-caps, ABS-157 static right-sizing,
# ABS-213 killed at min 60 mid-green pre-release-check). Three layers:
#   Part A — pure decision function watchdog_verdict() (AC1/AC2/AC3 logic +
#            MAX_LIFETIME-over-idle precedence, deterministic).
#   Part B — activity helpers: the process-check (AC4 single long Bash call) +
#            transcript-mtime signal.
#   Part C — end-to-end through the real spawn seam + watchdog: AC1 survive +
#            extension log, AC2 idle-kill (earlier than legacy), AC3 lifetime-
#            kill, AC4 long call survive, AC5 run.log visibility, AC6 kill-switch.
# =============================================================================

# Run a pure orchestrator helper in a subshell so the orchestrator's
# `set -euo pipefail` (enabled on source) stays contained and never leaks into
# the parent harness. Assertions run in the parent, so PASS/FAIL/TOTAL roll up.
# $ORCH is passed as $1 (NOT $0): the orchestrator's run-vs-source guard is
# `[ "${BASH_SOURCE[0]}" = "$0" ]`, so a $0 == $ORCH would misfire and run main().
_wd() { bash -c 'source "$1" >/dev/null 2>&1; shift; "$@"' _wd "$ORCH" "$@"; }

# -----------------------------------------------------------------------------
echo -e "\n${CYAN}Part A — watchdog_verdict() decision logic${NC}"
# -----------------------------------------------------------------------------
# AC1: an ACTIVE seat mid-verify (small idle, well under MAX_LIFETIME) continues,
# even when waited exceeds the OLD wall-time — activity, not runtime, decides.
assert_eq "$(_wd watchdog_verdict 3000 5 900 7200)" "continue" \
    "ABS-225 AC1: active seat (idle 5s) past old wall-time still continues"
# AC2: a hung seat (idle >= IDLE_TIMEOUT, still under MAX_LIFETIME) is idle-killed.
assert_eq "$(_wd watchdog_verdict 950 950 900 7200)" "idle-kill" \
    "ABS-225 AC2: idle 950s >= 900s timeout -> idle-kill"
assert_eq "$(_wd watchdog_verdict 100 900 900 7200)" "idle-kill" \
    "ABS-225 AC2: idle exactly at threshold (boundary) -> idle-kill"
# AC3: a dauer-active seat (idle tiny) hits the absolute MAX_LIFETIME cap.
assert_eq "$(_wd watchdog_verdict 7200 1 900 7200)" "lifetime-kill" \
    "ABS-225 AC3: active loop reaching MAX_LIFETIME -> lifetime-kill"
# Precedence: when BOTH thresholds are exceeded, MAX_LIFETIME wins (a looping
# seat is "active" and must still be reaped — ABS-132/151).
assert_eq "$(_wd watchdog_verdict 8000 5000 900 7200)" "lifetime-kill" \
    "ABS-225: lifetime beats idle when both exceeded (loop guard)"
# Disabling knobs (<=0) turns off that limit.
assert_eq "$(_wd watchdog_verdict 999999 5 900 0)" "continue" \
    "ABS-225: max_lifetime<=0 disables the absolute cap"
assert_eq "$(_wd watchdog_verdict 100 999999 0 7200)" "continue" \
    "ABS-225: idle_timeout<=0 disables idle-kill"

# -----------------------------------------------------------------------------
echo -e "${CYAN}Part B — activity helpers: process-check (AC4) + transcript${NC}"
# -----------------------------------------------------------------------------
# AC4 core: a process with a live child (models a single long Bash call that
# writes no telemetry between start and end) reads as active. The check and the
# child live in ONE subshell so they share a process tree. `sleep 5; :` defeats
# bash's single-command exec optimization, so the shell stays alive WITH a
# `sleep` child (a parent-with-child, like claude running a Bash tool).
# `|| true`: the sourced set -e can make the trailing kill exit non-zero AFTER
# the echo already produced the result — neutralize it so set -e doesn't abort.
r=$(bash -c 'source "$1" >/dev/null 2>&1
    bash -c "sleep 5; :" & cp=$!
    sleep 0.5
    if seat_has_live_descendant "$cp"; then echo 0; else echo 1; fi
    kill "$cp" 2>/dev/null; pkill -P "$cp" 2>/dev/null; true' _wd "$ORCH") || true
assert_eq "$r" "0" "ABS-225 AC4: a process with a live child is active (process-check)"

# seat_activity_epoch returns ~now (not the stale floor) while a child is alive.
r=$(bash -c 'source "$1" >/dev/null 2>&1
    bash -c "sleep 5; :" & cp=$!
    sleep 0.5
    now="$(date -u +%s)"
    act="$(seat_activity_epoch "$cp" "/nonexistent-marker" "$((now - 100))")"
    if [ "$act" -ge "$((now - 2))" ]; then echo 0; else echo 1; fi
    kill "$cp" 2>/dev/null; pkill -P "$cp" 2>/dev/null; true' _wd "$ORCH") || true
assert_eq "$r" "0" "ABS-225 AC4: seat_activity_epoch ~now while a child is alive"

# A childless process reads as NOT active (the AC2 hang shape): $! IS the sleep.
r=$(bash -c 'source "$1" >/dev/null 2>&1
    sleep 30 & sp=$!
    if seat_has_live_descendant "$sp"; then echo 0; else echo 1; fi
    kill "$sp" 2>/dev/null; true' _wd "$ORCH") || true
assert_eq "$r" "1" "ABS-225 AC2: a childless process has no live descendant"

# Transcript signal: a JSONL written after the marker is picked up as activity
# (covers Read/Edit/Grep tool calls, which fork no child but append transcript).
_WD_WORK="$(mktemp -d /tmp/wd-idle-XXXXXX)"
export ORCH_TRANSCRIPT_DIR="$_WD_WORK/transcripts"
mkdir -p "$ORCH_TRANSCRIPT_DIR/projslug"
_marker="$_WD_WORK/marker"; : > "$_marker"
sleep 1
printf '{"type":"tool_use","name":"Edit"}\n' > "$ORCH_TRANSCRIPT_DIR/projslug/sess.jsonl"
_tw="$(_wd seat_last_transcript_write "$_marker" || true)"
_mk="$(_wd file_mtime_epoch "$_marker" || true)"
if [ -n "$_tw" ] && [ "$_tw" -ge "$_mk" ]; then r=0; else r=1; fi
assert_eq "$r" "0" "ABS-225: transcript write after the marker is picked up as activity"
# A transcript OLDER than the marker (from a previous run) is NOT counted.
rm -f "$ORCH_TRANSCRIPT_DIR/projslug/sess.jsonl"
touch -t 202001010000 "$ORCH_TRANSCRIPT_DIR/projslug/old.jsonl" 2>/dev/null || true
_tw2="$(_wd seat_last_transcript_write "$_marker" || true)"
assert_eq "${_tw2:-empty}" "empty" "ABS-225: a transcript older than the marker is ignored"
rm -rf "$_WD_WORK"
unset ORCH_TRANSCRIPT_DIR

# -----------------------------------------------------------------------------
echo -e "${CYAN}Part C — end-to-end through the real spawn seam + watchdog${NC}"
# -----------------------------------------------------------------------------
# This include is sourced AFTER the whole monolith body has run, so it inherits
# the LAST shell-level definition of any shared helper. Later monolith sections
# (ABS-210) redefine `tracker()` to a per-id stub bound to a now-deleted temp
# sandbox; restore the canonical adapter-driver here so our create/transition
# calls hit the real mock tracker. (`orch`, `baseline`, `new_env` are not
# redefined downstream, so they are still the harness originals.)
tracker() { bash "$TRACKER" "$@"; }
# run.log reader: new_env drops ORCH_RUN_LOG so the per-test default applies.
_wd_runlog() { cat "$ORCH_STATE_DIR/run.log" 2>/dev/null || true; }

# --- AC1: an ACTIVE seat survives past the OLD wall-time, then hands off -------
# The stub stays busy (a live `sleep` child) for 4s — longer than the 2s LEGACY
# wall-time (ORCH_AGENT_TIMEOUT, what the old watchdog would have killed at).
# Because it is ACTIVE it is NOT killed: the watchdog logs a one-shot "extended"
# decision (AC5 third category) and lets it complete + hand off. IDLE_TIMEOUT
# (10s) never trips and MAX_LIFETIME (20s) is never reached.
new_env
export ORCH_WATCHDOG_POLL=1                   # probe every 1s so the 2s cross is prompt
export STUB_HANG=1 STUB_HANG_SECONDS=4        # a live child => "active"
export ORCH_AGENT_TIMEOUT=2                   # legacy wall-time the old watchdog used
export ORCH_AGENT_IDLE_TIMEOUT=10             # never trips (seat stays active)
export ORCH_AGENT_MAX_LIFETIME=20
T=$(tracker create --type ticket --title "AC1 active survives" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT HANDOFF ticket=$T" "ABS-225 AC1: active seat survives past old wall-time and hands off"
assert_not_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "ABS-225 AC1: active seat is not killed"
assert_not_contains "$(_wd_runlog)" "idle-kill" "ABS-225 AC1: active seat is never idle-killed"
assert_not_contains "$(_wd_runlog)" "lifetime-kill" "ABS-225 AC1: active seat is never lifetime-killed"
assert_contains "$(_wd_runlog)" "extended:" "ABS-225 AC1/AC5: run.log records the extension (Verlängerung) — the WHY it survived"
cleanup_env

# --- AC2: a HUNG seat (no tool-calls, no child) is idle-killed, EARLY ----------
# IDLE_TIMEOUT=2s; the legacy wall-time (MAX_LIFETIME 30s) is far away — proving
# the idle-kill fires EARLIER than today's hard-wall-time kill would.
new_env
export ORCH_WATCHDOG_POLL=1
export STUB_HANG_NOCHILD=1                    # wedged: no child, no CPU
export ORCH_AGENT_IDLE_TIMEOUT=2
export ORCH_AGENT_MAX_LIFETIME=30             # would-be legacy wall-time, far off
T=$(tracker create --type ticket --title "AC2 hung idle-kill" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
_start=$(date -u +%s)
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
_elapsed=$(( $(date -u +%s) - _start ))
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "ABS-225 AC2: hung seat is killed -> crash"
assert_contains "$(_wd_runlog)" "idle-kill" "ABS-225 AC2/AC5: run.log records an idle-kill (the WHY)"
# Killed well before MAX_LIFETIME(30s) — allow generous margin for the retry.
if [ "$_elapsed" -lt 25 ]; then r=0; else r=1; fi
assert_eq "$r" "0" "ABS-225 AC2: idle-kill fires earlier than the 30s legacy wall-time (elapsed=${_elapsed}s)"
cleanup_env

# --- AC3: a dauer-ACTIVE loop dies HARD at MAX_LIFETIME ------------------------
# The loop is always "active" (idle-kill can never fire, IDLE_TIMEOUT=20s), so
# only the absolute MAX_LIFETIME(3s) reaps it — the ABS-132/151 loop guard.
new_env
export ORCH_WATCHDOG_POLL=1
export STUB_LOOP=1                            # endless active loop, no handoff
export ORCH_AGENT_IDLE_TIMEOUT=20             # never trips (seat stays active)
export ORCH_AGENT_MAX_LIFETIME=3
T=$(tracker create --type ticket --title "AC3 loop lifetime-kill" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "ABS-225 AC3: looping seat is reaped -> crash"
assert_contains "$(_wd_runlog)" "lifetime-kill" "ABS-225 AC3/AC5: run.log records a lifetime-kill (the WHY)"
assert_not_contains "$(_wd_runlog)" "idle-kill" "ABS-225 AC3: an active loop is never idle-killed"
cleanup_env

# --- AC4: a single LONG Bash call (one child, no telemetry) survives ----------
# One 4s child call, no transcript writes in between — the process-check keeps
# the seat alive despite an IDLE_TIMEOUT (2s) shorter than the call, then it
# hands off. This is the documented "Prozess-Check" answer to AC4.
new_env
export ORCH_WATCHDOG_POLL=1
export STUB_HANG=1 STUB_HANG_SECONDS=4        # ONE long child call
export ORCH_AGENT_IDLE_TIMEOUT=2              # shorter than the single call
export ORCH_AGENT_MAX_LIFETIME=20
T=$(tracker create --type ticket --title "AC4 long single call" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT HANDOFF ticket=$T" "ABS-225 AC4: single long Bash call survives via the process-check"
assert_not_contains "$(_wd_runlog)" "idle-kill" "ABS-225 AC4: a running child is not idle-killed"
cleanup_env

# --- AC6: kill-switch ORCH_WATCHDOG_IDLE=0 restores legacy hard wall-time ------
# With the idle watchdog OFF, a childless wedged seat is killed at the resolved
# ORCH_AGENT_TIMEOUT wall-time (legacy behavior), logged as a wall-time kill.
new_env
export ORCH_WATCHDOG_IDLE=0                   # legacy wall-time watchdog
export STUB_HANG_NOCHILD=1
export ORCH_AGENT_TIMEOUT=2                   # legacy kill at 2s
T=$(tracker create --type ticket --title "AC6 kill-switch legacy" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po --reason go >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$T" "ABS-225 AC6: kill-switch off -> legacy wall-time still kills a hang"
assert_contains "$(_wd_runlog)" "legacy" "ABS-225 AC6/AC5: run.log marks the legacy wall-time kill"
cleanup_env
