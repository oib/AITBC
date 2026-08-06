#!/bin/bash
# =============================================================================
# Test: seats may only kill by PID / own process group, never by name-pattern
#       (ABS-243)
# =============================================================================
# Proves the mechanical PreToolUse Bash guard that closes the ABS-225 watch-run
# Restbefund: a seat ran `pkill -9 -f "scripts/orchestrator.sh --live"` in ad-hoc
# cleanup and reaped the operator's LIVE orchestrator twice (session a33f54f8).
# Coverage:
#
#   AC1  a name-pattern kill from a SEAT is BLOCKED (exit 2): pkill -f, pkill
#        <name>, killall, and kill $(pgrep -f …). End-to-end with a DECOY process
#        whose command line carries the pattern — the guard blocks the command so
#        it never runs and the decoy SURVIVES.
#   AC2  PID-/group-/session-scoped kills PASS (exit 0), no false positive:
#        kill "$pid", kill -TERM "$pid", kill -0 "$pid", pkill -P "$pid",
#        pkill -g "$pgid", pgrep -P "$pid" | xargs kill.
#   AC3  kill switch ORCH_KILL_GUARD=0 restores legacy (allows a name-pattern
#        kill); a HUMAN shell (no seat marker) is never guarded.
#   AC4  every blocked kill is logged (timestamp + matched form + command) to
#        ORCH_KILL_GUARD_LOG — the operator sees WHEN and WHAT was blocked.
#
# The guard is invoked directly with a stdin JSON payload (the Claude Code
# PreToolUse contract) and its exit code checked — exit 2 means the command is
# refused and Claude Code never runs it. This test NEVER executes a real
# name-pattern pkill (that would reap a live orchestrator); it only ever kills
# the decoy by its explicit PID.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-kill-guard.sh
# =============================================================================

set -u

# ABS-285: scrub ambient ORCH_* before driving the real seam/runner. A seat
# exports ~37 of them; a non-empty one leaks into the code under test and makes
# the result a function of the calling seat instead of the commit. Prefix-unset
# covers vars added later. This test sets every ORCH_* it needs, below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/harness/claude/hooks/pre-bash-kill-guard.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -8 <<<"$output" | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}

command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not found (guard needs jq); cannot run test"; exit 0; }
[ -f "$HOOK" ] || { echo "FAIL: guard not found at $HOOK"; exit 1; }

TMP="$(mktemp -d /tmp/kg-XXXXXX)"
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

GUARD_LOG="$TMP/kill-guard.log"
LAST_ERR="$TMP/last_err"    # stderr of the most recent run_guard (read via cat)

# Run the guard with a command string; echoes the exit code. Because this is
# called via $(...) (a subshell), stderr is persisted to $LAST_ERR for the
# caller to inspect rather than a variable (which would not survive the subshell).
# Seat context is set from `seat`; pass seat="" to simulate a HUMAN shell (no
# seat marker at all -> never guarded).
run_guard() {
    local cmd="$1" seat="${2-be-developer}" switch="${3-1}"
    local payload; payload=$(jq -n --arg c "$cmd" '{tool_input:{command:$c}}')
    local role="" ticket=""
    if [ -n "$seat" ]; then role="$seat"; ticket="ABS-243"; fi
    ORCH_SEAT="$seat" ORCH_ROLE="$role" ORCH_TICKET="$ticket" \
        ORCH_KILL_GUARD="$switch" ORCH_KILL_GUARD_LOG="$GUARD_LOG" \
        bash "$HOOK" <<<"$payload" 2>"$LAST_ERR" >/dev/null
    local ec=$?
    echo "$ec"
}

echo -e "${CYAN}=== ABS-243 kill-guard test ===${NC}"

# --- AC1: name-pattern kills from a seat are BLOCKED (exit 2) ----------------
echo -e "${CYAN}AC1: name-pattern kills blocked${NC}"
assert_eq "$(run_guard 'pkill -9 -f "scripts/orchestrator.sh --live"')" "2" "pkill -9 -f (the incident) blocked"
assert_eq "$(run_guard 'pkill -f orchestrator')" "2" "pkill -f <pattern> blocked"
assert_eq "$(run_guard 'pkill orchestrator')" "2" "pkill <name> (no scope flag) blocked"
assert_eq "$(run_guard 'killall orchestrator.sh')" "2" "killall blocked"
assert_eq "$(run_guard 'kill $(pgrep -f "orchestrator.sh --live")')" "2" "kill \$(pgrep -f …) blocked"
assert_eq "$(run_guard 'pgrep -f orchestrator | xargs kill -9')" "2" "pgrep -f … | xargs kill blocked"
assert_contains "$(cat "$LAST_ERR" 2>/dev/null)" "BLOCKED (ABS-243 kill-guard)" "block message shown to seat"

# --- AC1 regression (SA Stage-1 Iter 1): a signal flag / compound clause must
#     NOT be misread as scope. Whole-line scanning let these slip through. ------
echo -e "${CYAN}AC1: signal flag / compound clause must not count as scope${NC}"
assert_eq "$(run_guard 'kill -s KILL $(pgrep -f "scripts/orchestrator.sh --live")')" "2" "kill -s KILL \$(pgrep -f …) blocked (incident, one flag changed)"
assert_eq "$(run_guard 'kill -s TERM $(pgrep -f orchestrator)')" "2" "kill -s TERM \$(pgrep -f …) blocked"
assert_eq "$(run_guard 'pgrep -f orchestrator | xargs kill -s KILL')" "2" "pgrep -f … | xargs kill -s KILL blocked"
assert_eq "$(run_guard 'pkill -f orchestrator && kill -s 0 $$')" "2" "pkill -f … && kill -s 0 \$\$ blocked (compound clause)"
assert_eq "$(run_guard 'pkill -f orchestrator -s')" "2" "pkill -f … with trailing -s blocked (-f is pattern mode)"

# --- AC1 end-to-end: a DECOY carrying the pattern SURVIVES -------------------
echo -e "${CYAN}AC1: decoy process survives a blocked pkill${NC}"
DECOY="$TMP/abs243-decoy-orchestrator.sh"
printf '#!/bin/bash\nsleep 300\n' > "$DECOY"
chmod +x "$DECOY"
"$DECOY" --live &
DECOY_PID=$!
kill -0 "$DECOY_PID" 2>/dev/null || echo "  (warn) decoy failed to start"
ec=$(run_guard 'pkill -9 -f "abs243-decoy-orchestrator.sh --live"')
assert_eq "$ec" "2" "seat pkill -f against the decoy pattern is refused"
if kill -0 "$DECOY_PID" 2>/dev/null; then
    assert_eq "alive" "alive" "decoy survives (guard refused; command never ran)"
else
    assert_eq "dead" "alive" "decoy survives (guard refused; command never ran)"
fi
kill "$DECOY_PID" 2>/dev/null || true   # cleanup BY PID (never by pattern)
wait "$DECOY_PID" 2>/dev/null || true

# --- AC2: PID-/group-/session-scoped kills PASS (exit 0), no false positive --
echo -e "${CYAN}AC2: PID-scoped kills allowed (no false positive)${NC}"
assert_eq "$(run_guard 'kill "$pid"')" "0" 'kill "$pid" allowed'
assert_eq "$(run_guard 'kill -TERM 12345')" "0" "kill -TERM <pid> allowed"
assert_eq "$(run_guard 'kill -0 12345')" "0" "kill -0 <pid> allowed"
assert_eq "$(run_guard 'pkill -TERM -P "$spawn_pid"')" "0" "pkill -TERM -P <pid> allowed"
assert_eq "$(run_guard 'pkill -KILL -P 12345')" "0" "pkill -KILL -P <pid> allowed"
assert_eq "$(run_guard 'pkill -g 4242')" "0" "pkill -g <pgid> (own process group) allowed"
assert_eq "$(run_guard 'pkill -s 4242')" "0" "pkill -s <sid> (own session) allowed"
assert_eq "$(run_guard 'pgrep -P 12345 | xargs kill')" "0" "pgrep -P <pid> | xargs kill allowed"
assert_eq "$(run_guard 'kill -s TERM 12345')" "0" "kill -s TERM <pid> (real signal flag, PID-scoped) allowed"
assert_eq "$(run_guard 'kill -s KILL "$pid"')" "0" 'kill -s KILL "$pid" (real signal flag, PID-scoped) allowed'
assert_eq "$(run_guard 'ps aux | grep orchestrator')" "0" "non-kill inspection (ps|grep) allowed"

# --- AC3: kill switch and human shell restore legacy behavior ----------------
echo -e "${CYAN}AC3: kill switch + human shell${NC}"
assert_eq "$(run_guard 'pkill -9 -f orchestrator' be-developer 0)" "0" "ORCH_KILL_GUARD=0 allows name-pattern kill (legacy)"
assert_eq "$(run_guard 'pkill -9 -f orchestrator' '' 1)" "0" "human shell (no seat marker) never guarded"

# --- AC4: blocked kills are logged (timestamp + matched form + command) ------
echo -e "${CYAN}AC4: observability — blocked kills logged${NC}"
LOG_CONTENT="$(cat "$GUARD_LOG" 2>/dev/null)"
assert_contains "$LOG_CONTENT" "BLOCKED" "log records a BLOCKED entry"
assert_contains "$LOG_CONTENT" "matched=pkill" "log records the matched form"
assert_contains "$LOG_CONTENT" "scripts/orchestrator.sh --live" "log records the offending command"
# UTC timestamp shape YYYY-MM-DDTHH:MM:SSZ (or a date fallback) at line start.
if grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z ' "$GUARD_LOG" 2>/dev/null; then
    assert_eq "ts" "ts" "log lines carry a UTC timestamp"
else
    assert_eq "no-ts" "ts" "log lines carry a UTC timestamp"
fi

# =============================================================================
# ABS-244 — defense-in-depth layers added by the SecEng bypassability review.
# Full vector matrix + accepted-risk decisions:
#   docs/security/ABS-244-kill-guard-bypassability-review.md
#   bash tests/probe-kill-guard-bypass.sh   (reproduces the verdict table)
# Only the two vectors INSIDE the guard's charter (careless actor) are mitigated
# here. Deliberate obfuscation (base64/eval, ${K}ll splicing, wrapper script,
# python os.kill) is ACCEPTED RISK by design — see the review.
# =============================================================================

# --- ABS-244 V5b: a ps|grep name-lookup feeding a kill is BLOCKED ------------
# Same class as pgrep|kill, and the natural retry once pkill/pgrep is refused.
echo -e "${CYAN}ABS-244: ps name-lookup feeding a kill blocked${NC}"
assert_eq "$(run_guard "kill \$(ps ax | grep -i orchestrator | awk '{print \$1}')")" "2" "kill \$(ps … | grep …) blocked"
assert_eq "$(run_guard "ps aux | grep orchestrator | awk '{print \$1}' | xargs kill -9")" "2" "ps … | grep … | xargs kill blocked"

# --- ABS-244 V8: the broadcast kill is BLOCKED -------------------------------
# `-1` as a TARGET signals every process of the UID — the live orchestrator too.
echo -e "${CYAN}ABS-244: broadcast kill (-1 target) blocked${NC}"
assert_eq "$(run_guard 'kill -9 -1')" "2" "kill -9 -1 (every process of the user) blocked"
assert_eq "$(run_guard 'kill -TERM -1')" "2" "kill -TERM -1 blocked"
assert_eq "$(run_guard 'kill -s KILL -1')" "2" "kill -s KILL -1 blocked"
assert_eq "$(run_guard 'kill -- -1')" "2" "kill -- -1 blocked"

# --- ABS-244: no false positive — position decides what -1 MEANS -------------
# `kill -1 <pid>` is SIGHUP to ONE pid (-1 in the signal slot) and must survive.
echo -e "${CYAN}ABS-244: legitimate kills still allowed (no false positive)${NC}"
assert_eq "$(run_guard 'kill -1 12345')" "0" "kill -1 <pid> (SIGHUP, -1 is the SIGNAL) allowed"
assert_eq "$(run_guard 'kill -9 -12345')" "0" "kill -9 -<pgid> (own process group) allowed"
assert_eq "$(run_guard 'ps -p "$pid" >/dev/null && kill "$pid"')" "0" "ps -p check then kill by PID (no name lookup) allowed"
assert_eq "$(run_guard 'ps aux | grep orchestrator | head -3')" "0" "ps|grep inspection without a kill allowed"

# --- ABS-244 end-to-end: a DECOY carrying the pattern SURVIVES a ps|grep|kill -
echo -e "${CYAN}ABS-244: decoy survives a blocked ps|grep|kill${NC}"
DECOY2="$TMP/abs244-decoy-orchestrator.sh"
printf '#!/bin/bash\nsleep 300\n' > "$DECOY2"
chmod +x "$DECOY2"
"$DECOY2" --live &
DECOY2_PID=$!
ec=$(run_guard "kill \$(ps ax | grep abs244-decoy-orchestrator | awk '{print \$1}')")
assert_eq "$ec" "2" "seat ps|grep|kill against the decoy pattern is refused"
if kill -0 "$DECOY2_PID" 2>/dev/null; then
    assert_eq "alive" "alive" "decoy survives (guard refused; command never ran)"
else
    assert_eq "dead" "alive" "decoy survives (guard refused; command never ran)"
fi
kill "$DECOY2_PID" 2>/dev/null || true   # cleanup BY PID (never by pattern)
wait "$DECOY2_PID" 2>/dev/null || true

# --- ABS-244 AC4: the new layers honor the kill switch + emit observability ---
echo -e "${CYAN}ABS-244: kill switch + observability parity for the new layers${NC}"
assert_eq "$(run_guard 'kill -9 -1' be-developer 0)" "0" "ORCH_KILL_GUARD=0 allows broadcast kill (legacy)"
assert_eq "$(run_guard "kill \$(ps ax | grep -i orchestrator)" be-developer 0)" "0" "ORCH_KILL_GUARD=0 allows ps|grep|kill (legacy)"
assert_eq "$(run_guard 'kill -9 -1' '' 1)" "0" "human shell (no seat marker) never guarded (broadcast)"
LOG_CONTENT="$(cat "$GUARD_LOG" 2>/dev/null)"
assert_contains "$LOG_CONTENT" "matched=kill -1" "log records the broadcast-kill form"
assert_contains "$LOG_CONTENT" "matched=ps|kill" "log records the ps-name-lookup form"

# --- ABS-294 NB1: the awk/sed half of the ps-lookup vector class --------------
# `has_word grep` was a mandatory condition, so the CLASSIC idiom sailed through.
echo -e "${CYAN}ABS-294 NB1: ps lookup via awk/sed/cut feeding a kill blocked${NC}"
assert_eq "$(run_guard "kill \$(ps ax | awk '/orchestrator/{print \$1}')")" "2" "kill \$(ps | awk …) blocked"
assert_eq "$(run_guard "ps ax | awk '/orchestrator/{print \$1}' | xargs kill -9")" "2" "ps | awk | xargs kill blocked"
assert_eq "$(run_guard "ps ax | sed -n '/orchestrator/s/^ *\\([0-9]*\\).*/\\1/p' | xargs kill")" "2" "ps | sed | xargs kill blocked"
assert_eq "$(run_guard 'ps ax | cut -d" " -f1 | xargs kill')" "2" "ps | cut | xargs kill blocked"
assert_eq "$(run_guard 'ps -p "$pid" && kill "$pid"')" "0" "ps -p PID check + kill by PID still allowed"
assert_eq "$(run_guard "ps ax | awk '{print \$1}' | head -3")" "0" "ps | awk inspection without a kill allowed"

# --- ABS-294 NB2: audit-log lines cannot be forged via embedded newlines ------
echo -e "${CYAN}ABS-294 NB2: log-injection via newline in the command refused${NC}"
: > "$GUARD_LOG"
FORGED='2026-01-01T00:00:00Z ALLOWED seat=forged'
ec=$(run_guard "pkill -f orchestrator
$FORGED")
assert_eq "$ec" "2" "newline-carrying name-pattern kill still blocked"
if grep -qxF "$FORGED" "$GUARD_LOG" 2>/dev/null; then
    assert_eq "forged-line-present" "no-forged-line" "embedded newline cannot mint a standalone log line"
else
    assert_eq "no-forged-line" "no-forged-line" "embedded newline cannot mint a standalone log line"
fi
assert_eq "$(grep -c 'BLOCKED' "$GUARD_LOG")" "1" "the block is still recorded as exactly one line"

# --- ABS-294 NB3: path-qualified kill keeps -1 in the signal slot -------------
echo -e "${CYAN}ABS-294 NB3: /bin/kill -1 <pid> no longer a false positive${NC}"
assert_eq "$(run_guard '/bin/kill -1 12345')" "0" "/bin/kill -1 <pid> (SIGHUP, -1 is the SIGNAL) allowed"
assert_eq "$(run_guard '/bin/kill -9 -1')" "2" "/bin/kill -9 -1 (broadcast) still blocked"

echo ""
echo -e "${CYAN}=== Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, $TOTAL total ===${NC}"
[ "$FAIL" -eq 0 ] || exit 1
