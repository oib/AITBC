#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Stub spawn command (spec §8.1) — test double for ORCH_SPAWN_CMD
# =============================================================================
# Implements the §3.1 provider contract without invoking a real model:
#   "$ORCH_SPAWN_CMD" <role> <ticket-id> <packet-file>
#     stdin:  the context packet   env: ORCH_ROLE, ORCH_TICKET, ORCH_PACKET_FILE
#     stdout: the agent's final structured result incl. the handoff record
#     exit 0 on success.
#
# It reads (drains) the packet on stdin, echoes a canned handoff record to
# stdout, and exits 0. Behavior knobs via env (to exercise every §6 branch):
#   STUB_FAIL=1        exit non-zero (spawn failure)
#   STUB_HANG=1        sleep past the runner watchdog (timeout path); the sleep
#                      is a live CHILD, so the ABS-225 idle watchdog reads it as
#                      "active" (only MAX_LIFETIME reaps it)
#   STUB_HANG_NOCHILD=1  block with NO child + NO CPU (a wedged seat) — the
#                      ABS-225 idle watchdog idle-kills it (AC2)
#   STUB_LOOP=1        active endless loop (a live sleep child every tick) — only
#                      the ABS-225 MAX_LIFETIME cap reaps it (AC3)
#   STUB_NO_HANDOFF=1  print output WITHOUT a parseable handoff record
#   STUB_FAIL_RESULT_SUBTYPE=<subtype>  print a Result-JSON carrying this error
#                      `subtype` to stdout, THEN exit non-zero (STUB_FAIL_RC, def 7)
#                      — ABS-265: models the idle-kill crash class where the CLI
#                      emitted its Result-JSON before dying (stderr uninformative)
#   STUB_MAX_TURNS_EXIT=1  exit 0 with a CLI `error_max_turns` result and NO
#                      handoff (ABS-151: models the turn-ceiling abort — the
#                      operator's named root cause; a fresh session only, like
#                      STUB_NO_HANDOFF)
#   STUB_HANG_SECONDS  sleep duration when hanging (default: 30)
#   STUB_RECORD_FILE   append "<role> <ticket>" here (test observability)
#   STUB_PACKET_COPY   append the drained context packet here (ABS-135: lets a
#                      test assert the packet header, e.g. from_status)
#   STUB_TOOLS_FILE    append "<role>\t<ORCH_TOOLS>" here (ABS-57: assert the
#                      read-only toolset the runner hands a review spawn)
#   STUB_TRANSITION_TO transition the ticket to this status via the tracker
#                      (lets the E2E drive the lifecycle deterministically)
#   STUB_HANDOFF_TO    emit a declarative `- to: <status>` line in the handoff
#                      record WITHOUT moving the ticket (ABS-132: models a seat
#                      that declares a target but leaves the transition to the
#                      runner)
#   STUB_TRACKER       tracker command for the transition (default: mock-tracker.sh)
#   STUB_HANDOFF_COMMITS  emit a `- commits: <sha> [<sha> ...]` line in the handoff
#                      record (ABS-255: models a seat CLAIMING commits — real,
#                      fabricated, or unreachable — for the runner's verification
#                      gate). Value is used verbatim.
#   STUB_HANDOFF_PROSE additional prose line in the handoff body (ABS-255: lets a
#                      test make the handoff claim a commit in PROSE with no
#                      `commits:` field — the non-blocking CLAIM-NOHASH advisory)
#   STUB_PERMISSION_DENIALS  emit a result JSON with a `permission_denials` array:
#                      0=empty (a clean spawn). 1 (or "mutating")=a denied MUTATING
#                      tool (Write) — the transcript is poisoned, the runner must
#                      not store the session (ABS-254). "readonly"=a denied READ-only
#                      tool (Read) — leaves nothing inconsistent, so the session is
#                      STILL stored (ABS-598 AC1). The spawn always delivers its
#                      handoff regardless; the denial rides alongside it.
#   STUB_ORPHAN_PIDFILE  background a long `sleep` (a detached child) and write its
#                      PID here, THEN emit the canned handoff and exit — models a
#                      seat that backgrounds a task and ends its turn (ABS-601 AC5).
#                      The runner must reap the orphaned process at spawn end.
#   STUB_ASYNC_WAIT=1  append the async-wait idiom ("I'll wait for the background
#                      task completion notification …") to the handoff body WITHOUT
#                      moving the ticket (ABS-601 AC3/AC4): the runner must NAME this
#                      ASYNC-WAIT-STALL instead of a generic HANDOFF-NOMOVE.
#   STUB_MAX_TURNS_DENIALS=1  on the FRESH birth spawn (STUB_MAX_TURNS=1), emit a
#                      result JSON that carries BOTH `error_max_turns` AND a
#                      non-empty `permission_denials` array — a denial loop that
#                      burns turns to the ceiling (ABS-254). The salvage resume
#                      then falls through to the CLEAN canned handoff, so the
#                      denial state exists ONLY on the birth spawn; this exercises
#                      the salvage-store poison path where the salvage's own
#                      output is clean.
# =============================================================================

ROLE="${1:-${ORCH_ROLE:-unknown}}"
TICKET="${2:-${ORCH_TICKET:-unknown}}"

# Drain the packet from stdin (a real provider consumes it).
PACKET="$(cat || true)"

# ABS-135: expose the packet for assertions (from_status must match THIS ticket).
if [ -n "${STUB_PACKET_COPY:-}" ]; then
    printf '%s\n' "$PACKET" >> "$STUB_PACKET_COPY"
fi

# Record the invocation for test assertions. ABS-111 A2: when the runner asks
# for a session RESUME, a third field carries the resumed id (legacy runs with
# no resume keep the exact two-field shape).
if [ -n "${STUB_RECORD_FILE:-}" ]; then
    if [ -n "${ORCH_RESUME_SESSION_ID:-}" ]; then
        printf '%s\t%s\t%s\n' "$ROLE" "$TICKET" "resume=$ORCH_RESUME_SESSION_ID" >> "$STUB_RECORD_FILE"
    elif [ -n "${ORCH_MODEL:-}" ]; then
        # ABS-121: surface the model the runner resolved (env/label) for tests.
        printf '%s\t%s\t%s\n' "$ROLE" "$TICKET" "model=$ORCH_MODEL" >> "$STUB_RECORD_FILE"
    else
        printf '%s\t%s\n' "$ROLE" "$TICKET" >> "$STUB_RECORD_FILE"
    fi
fi

# ABS-111 A1 (async overlap assertions): record wall-clock start/end epochs.
if [ -n "${STUB_TIMING_FILE:-}" ]; then
    STUB_T0="$(date +%s)"
fi

# Record the toolset the runner handed this spawn (ABS-57 separation-of-duties).
if [ -n "${STUB_TOOLS_FILE:-}" ]; then
    printf '%s\t%s\n' "$ROLE" "${ORCH_TOOLS:-}" >> "$STUB_TOOLS_FILE"
fi

# Record the turn ceiling the runner resolved for this spawn (ABS-156: lets a
# test assert per-role default / override precedence).
if [ -n "${STUB_TURNS_FILE:-}" ]; then
    printf '%s\t%s\n' "$ROLE" "${ORCH_MAX_TURNS:-}" >> "$STUB_TURNS_FILE"
fi

# Optional failure injections.
if [ "${STUB_FAIL:-0}" = "1" ]; then
    echo "stub-spawn: forced failure" >&2
    exit 7
fi
# ABS-265: crash WITH a Result-JSON on stdout — the CLI printed its --output-format
# json result object (carrying an error `subtype`) and THEN exited non-zero (e.g.
# an idle-kill during execution). Models the idle-kill crash class (ABS-251/254/255)
# where stderr is empty/uninformative but the Result-JSON holds the error class.
if [ -n "${STUB_FAIL_RESULT_SUBTYPE:-}" ]; then
    printf '{"type": "result", "subtype": "%s", "is_error": true, "result": "crashed mid-execution", "session_id": "%s", "total_cost_usd": 0}\n' \
        "$STUB_FAIL_RESULT_SUBTYPE" "${STUB_SESSION_ID:-stub}"
    exit "${STUB_FAIL_RC:-7}"
fi
if [ "${STUB_HANG:-0}" = "1" ]; then
    sleep "${STUB_HANG_SECONDS:-30}"
fi
# ABS-225: block with NO child process and NO CPU — a wedged seat (models AC2:
# "keine Tool-Calls, kein laufender Kind-Prozess"). `read` is a bash builtin so
# it forks nothing; the fifo is opened read-write (non-blocking open) and never
# written, so `read` blocks until the idle watchdog kills us. Distinct from
# STUB_HANG, whose `sleep` IS a live child the process-check reads as "active".
if [ "${STUB_HANG_NOCHILD:-0}" = "1" ]; then
    _wd_fifo="$(mktemp -u 2>/dev/null || echo "/tmp/stub-wd.$$.fifo")"
    mkfifo "$_wd_fifo" 2>/dev/null || true
    exec 9<>"$_wd_fifo" 2>/dev/null || true
    rm -f "$_wd_fifo" 2>/dev/null || true
    read -r _ <&9   # blocks forever (nothing is ever written)
fi
# ABS-225: an ACTIVE endless loop — the ABS-132/151 loop class (models AC3). The
# short `sleep` child keeps the seat reading as "active" (a live descendant), so
# ONLY MAX_LIFETIME can reap it — never an idle-kill. Never emits a handoff.
if [ "${STUB_LOOP:-0}" = "1" ]; then
    while :; do sleep 0.3; done
fi

# ABS-175 turn-cap salvage: on a FRESH session, emit a result JSON that signals
# the turn cap was hit (subtype=error_max_turns) and exit 0 — models a spawn
# truncated mid-work. The runner must NOT discard it; it salvage-resumes. On the
# RESUME (the salvage), fall through to the canned handoff below (models
# "committed what was done + wrote the handoff"), UNLESS STUB_SALVAGE_FAIL=1,
# which exits non-zero to model a salvage crash. Needs a UUID-shaped
# STUB_SESSION_ID so the runner can resume (short "stub" ids are not extracted).
if [ "${STUB_MAX_TURNS:-0}" = "1" ]; then
    if [ -z "${ORCH_RESUME_SESSION_ID:-}" ]; then
        # ABS-254: the birth spawn can hit the cap AND carry denials in ONE result
        # JSON (a denial loop that burns turns to the ceiling). The salvage resume
        # is clean, so this is the ONLY place the denial state exists.
        if [ "${STUB_MAX_TURNS_DENIALS:-0}" = "1" ]; then
            # ABS-598: a MUTATING denial in the birth spawn poisons the salvage carry.
            printf '{"subtype": "error_max_turns", "is_error": true, "result": "hit the turn cap mid-work", "session_id": "%s", "permission_denials": [{"tool_name": "Write", "tool_use_id": "toolu_stub", "tool_input": {"file_path": "/etc/hosts"}}], "total_cost_usd": 0}\n' "${STUB_SESSION_ID:-stub}"
        else
            printf '{"subtype": "error_max_turns", "is_error": true, "result": "hit the turn cap mid-work", "session_id": "%s", "total_cost_usd": 0}\n' "${STUB_SESSION_ID:-stub}"
        fi
        exit 0
    elif [ "${STUB_SALVAGE_FAIL:-0}" = "1" ]; then
        echo "stub-spawn: forced salvage failure" >&2
        exit 9
    fi
fi

# Optional lifecycle transition performed "by the agent".
if [ -n "${STUB_TRANSITION_TO:-}" ]; then
    STUB_TRACKER="${STUB_TRACKER:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/scripts/mock-tracker.sh}"
    bash "$STUB_TRACKER" transition "$TICKET" "$STUB_TRANSITION_TO" \
        --actor "$ROLE" --reason "stub-spawn: $ROLE completed, advancing" >/dev/null 2>&1 || true
fi

# ABS-601 AC5: background a long-lived process (a detached child) and record its
# PID, then continue to the handoff and exit — models a seat that starts a
# background task and ends its turn. The child reparents to init on our exit but
# keeps our process group, so the runner's group-scoped reap must terminate it.
if [ -n "${STUB_ORPHAN_PIDFILE:-}" ]; then
    sleep 300 &
    printf '%s\n' "$!" > "$STUB_ORPHAN_PIDFILE"
fi

# ABS-111 A1: optional sleep to make spawns overlap measurably, + timing record.
if [ -n "${STUB_SLEEP:-}" ]; then
    sleep "$STUB_SLEEP"
fi
if [ -n "${STUB_TIMING_FILE:-}" ]; then
    printf '%s\t%s\t%s\n' "$TICKET" "${STUB_T0:-0}" "$(date +%s)" >> "$STUB_TIMING_FILE"
fi

# ABS-111 A2: a resumed session ALWAYS produces the handoff — this models the
# handoff-repair contract ("emit only the ## Handoff block"), so STUB_NO_HANDOFF
# applies to fresh sessions only.
# ABS-151: turn-ceiling abort — the CLI hit --max-turns and returns a result
# object with `"subtype":"error_max_turns"` and no usable final message. Like
# STUB_NO_HANDOFF this models a FRESH session only (a resumed repair session
# still produces the handoff). tokens_out is truncated, matching the operator's
# observed signature.
if [ "${STUB_MAX_TURNS_EXIT:-0}" = "1" ] && [ -z "${ORCH_RESUME_SESSION_ID:-}" ]; then
    echo '{"type": "result", "subtype": "error_max_turns", "is_error": true, "num_turns": '"${ORCH_MAX_TURNS:-25}"', "result": "", "session_id": "'"${STUB_SESSION_ID:-stub}"'", "total_cost_usd": 0, "usage": {"input_tokens": 5000, "output_tokens": 125}}'
    exit 0
fi
if [ "${STUB_NO_HANDOFF:-0}" = "1" ] && [ -z "${ORCH_RESUME_SESSION_ID:-}" ]; then
    # Structured-ish output that carries NO handoff record (no ## Handoff section
    # and the `result` field does not mention a handoff). The session id is
    # configurable (ABS-111): a UUID-shaped STUB_SESSION_ID lets the runner's
    # repair path find it; the legacy default "stub" is deliberately too short.
    echo '{"result": "did some work but produced no record", "session_id": "'"${STUB_SESSION_ID:-stub}"'", "total_cost_usd": 0}'
    exit 0
fi

# Canned handoff record (matches the .claude/AGENT_OUTPUT_GUIDE handoff contract:
# a "## Handoff" / kind: handoff-shaped section). The optional session-id line
# precedes it so handoff extraction (which grabs from "## Handoff" to EOF) does
# not swallow it.
[ -n "${STUB_SESSION_ID:-}" ] && printf '{"session_id": "%s"}\n' "$STUB_SESSION_ID"
# ABS-254: the CLI result JSON reports refused tool calls in `permission_denials`
# (empty array when nothing was denied). A denial-hit spawn still hands off — the
# poison is its transcript, not its output — so this rides alongside the handoff.
if [ -n "${STUB_PERMISSION_DENIALS:-}" ]; then
    case "$STUB_PERMISSION_DENIALS" in
        0)
            printf '{"permission_denials": []}\n' ;;
        readonly)
            # ABS-598: a denied READ-only tool does NOT poison the session.
            printf '{"permission_denials": [{"tool_name": "Read", "tool_use_id": "toolu_stub", "tool_input": {"file_path": "/Users/sahan/boilerplate-stable/tests/staged-suite.sh", "limit": 80}}]}\n' ;;
        *)
            # 1 / "mutating": a denied MUTATING tool poisons the session (ABS-254).
            printf '{"permission_denials": [{"tool_name": "Write", "tool_use_id": "toolu_stub", "tool_input": {"file_path": "/etc/hosts"}}]}\n' ;;
    esac
fi
# ABS-120/ABS-165: optional cost/usage fields like the real CLI JSON result
# carries — incl. the cache_* input-token fields where the real input volume
# lives (STUB_CACHE_READ / STUB_CACHE_CREATE, default 0 for legacy callers).
if [ -n "${STUB_USAGE:-}" ]; then
    printf '{"total_cost_usd": %s, "usage": {"input_tokens": %s, "cache_read_input_tokens": %s, "cache_creation_input_tokens": %s, "output_tokens": %s}}\n' \
        "${STUB_COST:-0.05}" "${STUB_TOKENS_IN:-1000}" "${STUB_CACHE_READ:-0}" "${STUB_CACHE_CREATE:-0}" "${STUB_TOKENS_OUT:-200}"
fi
cat <<EOF
## Handoff

- role: $ROLE
- ticket: $TICKET
- summary: stub-spawn canned handoff for $ROLE on $TICKET.
- status: work simulated; see the packet for context.${STUB_HANDOFF_PROSE:+
- evidence: $STUB_HANDOFF_PROSE}
- next: proceed per the status machine.
EOF
# ABS-601 AC3/AC4: emit the async-wait idiom into the handoff — a seat promising to
# wait for a background completion notification a one-shot spawn never delivers.
[ "${STUB_ASYNC_WAIT:-0}" = "1" ] && printf '%s\n' "- note: Running. I'll wait for the background task completion notification before proceeding." || true
# ABS-255: optional claimed commit hashes the runner must verify.
[ -n "${STUB_HANDOFF_COMMITS:-}" ] && printf -- '- commits: %s\n' "$STUB_HANDOFF_COMMITS" || true
# ABS-132: optional declarative target status the runner should apply itself.
[ -n "${STUB_HANDOFF_TO:-}" ] && printf -- '- to: %s\n' "$STUB_HANDOFF_TO" || true
