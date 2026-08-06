#!/bin/bash
# =============================================================================
# S4/PILOT-30 — consumer-side Poll->Push (long-poll) unit tests
# =============================================================================
# Covers the three consumer surfaces the story converts to the event-driven
# long-poll, WITHOUT a live backend (a curl stub records the request; the
# orchestrator functions are sourced and driven with a stub tracker):
#   1. scripts/backend-tracker.sh  events [--wait <sec>]  URL + curl --max-time
#   2. scripts/orchestrator.sh     probe_events_wait_capability / poll_events /
#      reconcile_due  (capability gate, POLL_DID_WAIT pacing, wall-clock cadence,
#      --once + wait-failure fallback -> AC3/AC4/AC7)
#   3. scripts/backend-shipper.sh  command_wait_available / poll_commands ?wait=
#
# Run from repo root: bash tests/test-poll-push-consumer.sh
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

PASS=0; FAIL=0
assert_contains() {
    if printf '%s' "$1" | grep -qF -- "$2"; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS+1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected to find: $2)"; printf '    got: %s\n' "$1" | head -3; FAIL=$((FAIL+1)); fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -qF -- "$2"; then echo -e "  ${RED}FAIL${NC} $3 (did NOT expect: $2)"; FAIL=$((FAIL+1))
    else echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS+1)); fi
}
assert_eq() {
    if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS+1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected '$2', got '$1')"; FAIL=$((FAIL+1)); fi
}

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# A curl stub: records the full arg line to $STUB_ARGS_LOG, writes an (empty or
# fixture) body to the -o file, and prints the HTTP code from $STUB_CODE (def 200).
STUB="$TMP/curl-stub.sh"
cat > "$STUB" <<'STUBEOF'
#!/usr/bin/env bash
out=""; prev=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done
printf '%s\n' "$*" >> "${STUB_ARGS_LOG:-/dev/null}"
[ -n "$out" ] && printf '%s' "${STUB_BODY:-}" > "$out"
printf '%s' "${STUB_CODE:-200}"
STUBEOF
chmod +x "$STUB"

# =============================================================================
echo -e "${CYAN}=== 1. adapter: events [--wait] URL + curl --max-time ===${NC}"
# =============================================================================
LOG="$TMP/adapter-args.log"; : > "$LOG"
run_events() {
    STUB_ARGS_LOG="$LOG" BACKEND_CURL="$STUB" BACKEND_TOKEN=tok TRACKER_PROJECT=P \
        bash "$REPO_ROOT/scripts/backend-tracker.sh" events "$@" >/dev/null 2>&1
}

: > "$LOG"; run_events
line="$(cat "$LOG")"
assert_contains "$line" "/events?since=auto" "events (no flag) hits the immediate feed URL"
assert_not_contains "$line" "wait=" "events (no flag) sends NO wait= query (byte-identical pre-S4)"
assert_not_contains "$line" "--max-time" "events (no flag) sets NO curl --max-time"

: > "$LOG"; run_events --wait 55
line="$(cat "$LOG")"
assert_contains "$line" "wait=55" "events --wait 55 sends wait=55 on the query string"
assert_contains "$line" "since=auto" "events --wait keeps the since=auto cursor"
assert_contains "$line" "--max-time 65" "events --wait 55 sets curl --max-time = cap + buffer (65)"

: > "$LOG"; STUB_ARGS_LOG="$LOG" BACKEND_CURL="$STUB" BACKEND_TOKEN=tok TRACKER_PROJECT=P BACKEND_WAIT_MAX_TIME_BUFFER=3 \
    bash "$REPO_ROOT/scripts/backend-tracker.sh" events --wait 20 >/dev/null 2>&1
assert_contains "$(cat "$LOG")" "--max-time 23" "buffer override BACKEND_WAIT_MAX_TIME_BUFFER feeds --max-time"

ec=0; BACKEND_CURL="$STUB" BACKEND_TOKEN=tok TRACKER_PROJECT=P \
    bash "$REPO_ROOT/scripts/backend-tracker.sh" events --wait >/dev/null 2>&1 || ec=$?
[ "$ec" -ne 0 ] && echo -e "  ${GREEN}PASS${NC} events --wait without a value is rejected" && PASS=$((PASS+1)) \
    || { echo -e "  ${RED}FAIL${NC} events --wait without a value should die"; FAIL=$((FAIL+1)); }

# =============================================================================
echo -e "${CYAN}=== 2. orchestrator: probe / poll_events / reconcile_due ===${NC}"
# =============================================================================
(
  export TRACKER_CMD=scripts/mock-tracker.sh
  cd "$REPO_ROOT"
  source scripts/orchestrator.sh 2>/dev/null
  set +e   # the sourced script enables `set -e`; our probes return non-zero by design
  log() { :; }; runlog() { :; }   # silence logging side effects

  # --- capability probe (3 cases) ------------------------------------------
  CAPS_OUT="packet\nbrief\nevents-wait\ncommands-wait"
  tracker() { case "$1" in capabilities) printf '%b\n' "$CAPS_OUT" ;; esac; }
  ORCH_EVENTS_WAIT=1; unset EVENTS_WAIT_ACTIVE
  probe_events_wait_capability
  assert_eq "${EVENTS_WAIT_ACTIVE}" "1" "probe: events-wait advertised + ORCH_EVENTS_WAIT=1 -> active"

  ORCH_EVENTS_WAIT=0; unset EVENTS_WAIT_ACTIVE
  probe_events_wait_capability
  assert_eq "${EVENTS_WAIT_ACTIVE}" "0" "probe: kill switch ORCH_EVENTS_WAIT=0 -> inactive"

  ORCH_EVENTS_WAIT=1; unset EVENTS_WAIT_ACTIVE
  tracker() { case "$1" in capabilities) printf 'packet\nbrief\n' ;; esac; }   # no events-wait (mock-like)
  probe_events_wait_capability
  assert_eq "${EVENTS_WAIT_ACTIVE}" "0" "probe: adapter without events-wait cap -> inactive (mock/jira fallback)"

  # --- poll_events pacing ---------------------------------------------------
  ONCE=0
  tracker() {
      if [ "$1" = events ] && [ "${2:-}" = --wait ]; then echo "WAITHIT $3"; else echo "IMMHIT"; fi
  }
  EVENTS_WAIT_ACTIVE=1; EVENT_WAIT_CAP_SECONDS=55
  poll_events
  assert_eq "$POLL_DID_WAIT" "1" "poll_events: wait-mode sets POLL_DID_WAIT=1 (skip the between-cycle sleep)"
  assert_contains "$POLL_RAW" "WAITHIT 55" "poll_events: wait-mode issues events --wait <cap>"

  ONCE=1
  poll_events
  assert_eq "$POLL_DID_WAIT" "0" "poll_events: --once never blocks (POLL_DID_WAIT=0, immediate read)"
  assert_contains "$POLL_RAW" "IMMHIT" "poll_events: --once does the immediate read"

  ONCE=0; EVENTS_WAIT_ACTIVE=0
  poll_events
  assert_eq "$POLL_DID_WAIT" "0" "poll_events: fallback mode sleeps (POLL_DID_WAIT=0)"
  assert_contains "$POLL_RAW" "IMMHIT" "poll_events: fallback mode does the immediate read (AC3)"

  # wait FAILURE -> degrade to immediate read + interval sleep this cycle (AC4)
  ONCE=0; EVENTS_WAIT_ACTIVE=1
  tracker() { if [ "$1" = events ] && [ "${2:-}" = --wait ]; then return 7; else echo "IMMHIT"; fi; }
  poll_events
  assert_eq "$POLL_DID_WAIT" "0" "poll_events: a failed wait degrades this cycle to a sleep (no busy-loop, AC4)"
  assert_contains "$POLL_RAW" "IMMHIT" "poll_events: a failed wait still reads the feed immediately (no lost events)"

  # --- reconcile_due cadence -----------------------------------------------
  ORCH_RECONCILE_ON_STARTUP=1; ORCH_RECONCILE_EVERY_N_CYCLES=10; ORCH_RECONCILE_EVERY_SEC=100
  CYCLE=1; reconcile_due && echo -e "  ${GREEN}PASS${NC} reconcile_due: startup cycle always sweeps" && PASS=$((PASS+1)) \
      || { echo -e "  ${RED}FAIL${NC} reconcile_due startup"; FAIL=$((FAIL+1)); }

  # interval mode (EVENTS_WAIT_ACTIVE=0): legacy cycle-count modulo (AC3)
  EVENTS_WAIT_ACTIVE=0; CYCLE=10
  reconcile_due && echo -e "  ${GREEN}PASS${NC} reconcile_due: interval mode sweeps on CYCLE % N == 0 (AC3)" && PASS=$((PASS+1)) \
      || { echo -e "  ${RED}FAIL${NC} reconcile_due interval modulo hit"; FAIL=$((FAIL+1)); }
  CYCLE=7
  reconcile_due && { echo -e "  ${RED}FAIL${NC} reconcile_due interval off-cadence should skip"; FAIL=$((FAIL+1)); } \
      || { echo -e "  ${GREEN}PASS${NC} reconcile_due: interval mode skips off-cadence cycles (AC3)"; PASS=$((PASS+1)); }

  # wait mode (EVENTS_WAIT_ACTIVE=1): WALL-CLOCK, independent of CYCLE count (AC7)
  EVENTS_WAIT_ACTIVE=1; CYCLE=2
  LAST_RECONCILE_TS=$(( $(date +%s) - 200 ))   # 200s ago >= 100s cadence
  reconcile_due && echo -e "  ${GREEN}PASS${NC} reconcile_due: wait mode sweeps once >= ORCH_RECONCILE_EVERY_SEC elapsed (AC7 quiet)" && PASS=$((PASS+1)) \
      || { echo -e "  ${RED}FAIL${NC} reconcile_due wall-clock elapsed"; FAIL=$((FAIL+1)); }
  LAST_RECONCILE_TS=$(( $(date +%s) - 5 ))     # 5s ago < 100s cadence (event-storm: many fast cycles)
  CYCLE=100                                     # high cycle count must NOT force a sweep in wait mode
  reconcile_due && { echo -e "  ${RED}FAIL${NC} reconcile_due wait mode swept too soon (event-storm AC7)"; FAIL=$((FAIL+1)); } \
      || { echo -e "  ${GREEN}PASS${NC} reconcile_due: wait mode does NOT sweep per-cycle under an event storm (AC7)"; PASS=$((PASS+1)); }

  # export counters back to the parent shell
  echo "$PASS $FAIL" > "$TMP/orch-counts"
)
read -r _op _of < "$TMP/orch-counts"; PASS="$_op"; FAIL="$_of"

# =============================================================================
echo -e "${CYAN}=== 3. shipper: command_wait_available / poll_commands ?wait= ===${NC}"
# =============================================================================
(
  export ORCH_STATE_DIR="$TMP/state"; mkdir -p "$ORCH_STATE_DIR"
  export BACKEND_URL="http://backend.test:8420" BACKEND_TOKEN=tok TRACKER_PROJECT=P
  export ORCH_INSTANCE_ID="orch-1"
  cd "$REPO_ROOT"
  # Stub curl: capabilities -> events-wait/commands-wait; command poll -> empty queue.
  SLOG="$TMP/shipper-args.log"; : > "$SLOG"
  export STUB_ARGS_LOG="$SLOG"
  SSTUB="$TMP/shipper-curl.sh"
  cat > "$SSTUB" <<'SEOF'
#!/usr/bin/env bash
out=""; prev=""; url=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; case "$a" in http*) url="$a";; esac; done
printf '%s\n' "$*" >> "${STUB_ARGS_LOG:-/dev/null}"
case "$url" in
  *"/capabilities") body="packet"$'\n'"events-wait"$'\n'"commands-wait" ;;
  *) body='{"commands":[]}' ;;
esac
[ -n "$out" ] && printf '%s' "$body" > "$out"
printf '200'
SEOF
  chmod +x "$SSTUB"
  export BACKEND_CURL="$SSTUB"
  source scripts/backend-shipper.sh 2>/dev/null || true
  set +e   # the sourced script enables `set -e`; command_wait_available returns non-zero by design

  unset _SHIPPER_CMD_WAIT_RESOLVED _SHIPPER_CMD_WAIT_CODE
  ORCH_EVENTS_WAIT=1
  if command_wait_available; then r=0; else r=1; fi
  assert_eq "$r" "0" "command_wait_available: backend advertises commands-wait -> available"

  unset _SHIPPER_CMD_WAIT_RESOLVED _SHIPPER_CMD_WAIT_CODE
  ORCH_EVENTS_WAIT=0
  if command_wait_available; then r=0; else r=1; fi
  assert_eq "$r" "1" "command_wait_available: kill switch ORCH_EVENTS_WAIT=0 -> unavailable"

  : > "$SLOG"
  EVENT_WAIT_CAP_SECONDS=55; ORCH_EVENTS_WAIT_BUFFER=10
  poll_commands 55 >/dev/null 2>&1
  cline="$(grep 'commands?wait' "$SLOG" | tail -1)"
  assert_contains "$cline" "/orchestrators/orch-1/commands?wait=55" "poll_commands 55 long-polls the command queue with ?wait=55"
  assert_contains "$cline" "--max-time 65" "poll_commands 55 sets curl --max-time = cap + buffer (65)"

  : > "$SLOG"
  poll_commands >/dev/null 2>&1
  pline="$(grep '/commands' "$SLOG" | tail -1)"
  assert_not_contains "$pline" "wait=" "poll_commands (no arg) is the byte-identical immediate poll"

  echo "$PASS $FAIL" > "$TMP/ship-counts"
)
read -r _sp _sf < "$TMP/ship-counts"; PASS="$_sp"; FAIL="$_sf"

# =============================================================================
echo -e "\n${CYAN}=== Test summary ===${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}PASS${NC} $PASS/$((PASS+FAIL)) tests passed"; exit 0
else
    echo -e "${RED}FAIL${NC} $FAIL/$((PASS+FAIL)) tests failed"; exit 1
fi
