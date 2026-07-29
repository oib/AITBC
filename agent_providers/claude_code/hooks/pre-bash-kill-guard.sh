#!/bin/bash
# =============================================================================
# Pre-Bash Hook: foreign-process kill guard (ABS-243)
# =============================================================================
# ABS-243-kill-guard  <- marker: keep this token; docs/tests grep for it.
#
# WHY. In the ABS-225 watch-run an implementer SEAT ran ad-hoc cleanup commands
# of the form `pkill -9 -f "scripts/orchestrator.sh --live"` and reaped the
# operator's LIVE watch-orchestrator TWICE (2026-07-12 15:38Z / 15:41Z, session
# a33f54f8). A name-pattern kill (`pkill -f` / `killall` / `kill $(pgrep -f …)`)
# matches EVERY process whose name/command-line carries the pattern — including
# processes the seat never started, outside its spawn tree. Nothing stopped the
# seat's shell from doing that. This hook is the mechanical backstop.
#
# WHAT IT DOES. A Claude Code PreToolUse hook on the Bash tool. It reads the
# command from the stdin JSON payload (.tool_input.command) and BLOCKS (exit 2,
# stderr fed back to the model) any name-pattern process kill:
#   * killall …                      (killall matches only by name — no PID mode)
#   * pkill …    without -P/-g/-s, or in -f pattern mode  (matches by name)
#   * kill … $(pgrep …) / pgrep … | … kill   when the pgrep is unscoped
#   * kill … $(ps … | grep/awk/sed/cut …) / ps … | … | … kill   (ABS-244/ABS-294
#     — the name-lookup-feeding-a-kill form, and the natural thing to reach for
#     once pkill/pgrep is refused. Keyed on ps NOT being in -p PID mode, not on
#     the literal `grep`: `ps ax | awk '{print $1}' | xargs kill` is the classic
#     idiom and must block too. `ps -p "$pid" && kill "$pid"` has no name lookup
#     and stays allowed)
#   * kill … -1  — the BROADCAST kill (ABS-244): signals EVERY process of the
#     user, strictly worse than any name pattern, and carries no pkill/pgrep/
#     killall token at all. `-1` is legitimate only in the SIGNAL position
#     (`kill -1 <pid>` = SIGHUP to one PID); as a TARGET it means "everything".
# Scope is decided PER pkill/pgrep invocation, on that invocation's OWN args —
# a signal flag on a neighbouring kill (`kill -s SIGNAL`) or an unrelated
# compound clause never counts as scope (ABS-243 SA Stage-1 fix).
# It ALLOWS every PID- / group- / session-scoped kill unchanged (AC2):
#   kill "$pid" · kill -TERM "$pid" · kill -0 "$pid" · pkill -P "$pid"
#   · pkill -g "$pgid" · pkill -s "$sid" · pgrep -P "$pid" | xargs kill
#
# SCOPE. Fires ONLY for orchestrator SEATS — the spawn seam exports the
# ORCH_SEAT / ORCH_TICKET / ORCH_ROLE markers (orchestrator-spawn-claude.sh).
# A human's own interactive shell carries none of them and is NEVER guarded
# (same principle as the ABS-224 local-main guard): the operator keeps full
# authority over their own processes.
#
# KILL SWITCH (ABS-111 pattern). ORCH_KILL_GUARD default ON (=1). Set
# ORCH_KILL_GUARD=0 to restore the legacy unguarded behavior.
#
# OBSERVABILITY (ABS-66). Every blocked kill is appended to the guard log
# (ORCH_KILL_GUARD_LOG, default $TMPDIR/orchestrator-kill-guard.log) with a UTC
# timestamp, the seat identity, the matched form, and the offending command — so
# the operator sees WHEN and WHAT was blocked — and echoed to stderr for the seat.
#
# FAIL-OPEN. Missing jq, empty command, or a non-seat context -> exit 0 (allow),
# so the guard can never wedge a legitimate command flow.
#
# THREAT MODEL — READ THIS BEFORE TRUSTING THE GUARD (ABS-244 SecEng review).
# This is a GUARDRAIL against the CARELESS actor (the ABS-243 incident was a
# well-intentioned seat doing ad-hoc cleanup), NOT a barrier against a seat that
# deliberately evades it. It cannot be: seats run as the OPERATOR'S OWN UID (no
# privilege separation anywhere in scripts/ or harness/), so the kernel delivers
# any signal a seat sends; and seats hold Write/Edit on this very file, so the
# guard can be edited away without a kill pattern ever reaching a command line.
# A string matcher on the command line is therefore defeated by obfuscation
# (base64/eval, ${K}ll splicing, a wrapper script, python os.kill) BY DESIGN, and
# hardening it further buys false assurance, not security. Those vectors are
# ACCEPTED RISK, and the only durable control (OS-level privilege separation) is
# an architecture decision, not a hook.
#   Full vector matrix + verdicts: docs/security/ABS-244-kill-guard-bypassability-review.md
#   Reproduce:                     bash tests/probe-kill-guard-bypass.sh
#
# CAUTION. Do NOT validate this guard with a real name-pattern `pkill` against
# `orchestrator.sh` — that reaps the operator's live orchestrator. Use a decoy
# process and feed the command THROUGH this hook (see tests/test-kill-guard.sh).
#
# bash 3.2 + BSD tools only (no `setsid`, absent on macOS).
# =============================================================================

set -u

# --- Kill switch (ABS-111): default ON. Off -> allow unconditionally. --------
if [ "${ORCH_KILL_GUARD:-1}" = "0" ]; then
    exit 0
fi

payload=$(cat)

command -v jq >/dev/null 2>&1 || { echo 'hooks: jq not found; skipping kill-guard' >&2; exit 0; }

cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

# --- Seat context only. A human shell carries no seat marker -> never guarded.
if [ -z "${ORCH_SEAT:-}${ORCH_TICKET:-}${ORCH_ROLE:-}" ]; then
    exit 0
fi

# Word-boundary match for a bare command word (so "pkill" does not match inside
# "kill", and a path like ./pkill still matches).
has_word() {
    printf '%s' "$1" | grep -qE '(^|[^[:alnum:]_.-])'"$2"'([[:space:]]|$)'
}

# Split the command into simple-command segments at shell boundaries — pipes,
# &&/||, ;, backgrounding, and command-substitution parens/backticks — so each
# utility's OWN flags are evaluated in isolation. This is the ABS-243 SA Stage-1
# fix: a whole-line scan let a neighbouring `kill -s SIGNAL` (kill's signal flag)
# or an unrelated compound clause count as "scope" and slip a genuine name-
# pattern kill through (e.g. `kill -s KILL $(pgrep -f orchestrator)` — the exact
# incident, one flag changed). Scope MUST be decided on the pkill/pgrep token's
# own arguments, never the rest of the line.
split_segments() {
    printf '%s' "$1" | tr '|&;`()' '\n\n\n\n\n\n'
}

# A pkill/pgrep invocation is PID/group/session scoped (legitimate — the seat can
# only name a PID/group/session it started) only when ITS OWN args carry
# -P/-g/-s AND it is not in -f (match-against-full-command-line = name-pattern)
# mode. `-f` is the dangerous mode by definition, so an -f invocation is never
# treated as scoped even if a stray -s trails it.
seg_is_scoped() {
    local seg="$1"
    if printf '%s' "$seg" | grep -qE '(^|[[:space:]])(-f|--full)([[:space:]]|$)'; then
        return 1
    fi
    printf '%s' "$seg" | grep -qE '(^|[[:space:]])(-P|--parent|-g|--pgroup|-s|--session)([[:space:]=]|$)'
}

# The BROADCAST kill (ABS-244): a `-1` TARGET means "every process this user may
# signal" — the operator's live orchestrator included. Position decides meaning:
# `kill -1 1234` is SIGHUP to one PID (legitimate, -1 sits in the signal slot),
# `kill -9 -1` / `kill -s KILL -1` / `kill -- -1` are broadcasts (-1 sits in a
# target slot). So: a `-1` token that is NOT the one directly after `kill`.
# Globbing is disabled around the split — an unquoted `$seg` would otherwise let
# a `*` in the command line expand against the CWD.
seg_kills_everything() {
    local seg="$1" prev="" tok rc=1
    set -f
    for tok in $seg; do
        # ABS-294 NB3: a path-qualified kill (`/bin/kill -1 12345`) still has
        # `-1` in the SIGNAL slot — compare the basename, not the literal.
        case "$tok" in
            -1) case "$prev" in kill|*/kill) ;; *) rc=0 ;; esac
                [ "$rc" = "0" ] && break ;;
        esac
        prev="$tok"
    done
    set +f
    return "$rc"
}

# ABS-294 NB1: a ps invocation is PID-scoped (legitimate liveness check —
# `ps -p "$pid"`) only when ITS OWN args carry -p/--pid. Any other ps is a
# name/list lookup; feeding one into a kill is the same class as pgrep|kill,
# whatever filter sits in between (grep, awk, sed, cut, …).
seg_ps_is_pid_scoped() {
    printf '%s' "$1" | grep -qE '(^|[[:space:]])(-p|--pid)([[:space:]=]|$)'
}

reason=""
matched=""

if has_word "$cmd" "killall"; then
    matched="killall"
    reason="killall matches processes by name only (no PID scope)"
else
    # Evaluate every pkill / pgrep invocation on its OWN segment. A here-doc (not
    # a pipe) keeps the loop in the current shell so matched/reason survive break.
    while IFS= read -r seg; do
        [ -n "$seg" ] || continue
        if has_word "$seg" "pkill"; then
            if ! seg_is_scoped "$seg"; then
                matched="pkill"
                reason="pkill without -P/-g/-s (or in -f pattern mode) matches processes by name/pattern"
                break
            fi
        elif has_word "$seg" "pgrep"; then
            # A name-based pgrep list is dangerous only when it feeds a kill.
            if has_word "$cmd" "kill" && ! seg_is_scoped "$seg"; then
                matched="pgrep|kill"
                reason="pgrep name-lookup feeding a kill matches processes by name/pattern"
                break
            fi
        elif has_word "$seg" "kill" && seg_kills_everything "$seg"; then
            matched="kill -1"
            reason="kill with a -1 target signals EVERY process of the user (broadcast), not one the seat started"
            break
        fi
    done <<EOF
$(split_segments "$cmd")
EOF

    # ABS-244/ABS-294: `ps … | <any filter> | … kill` (or kill $(ps … | …)) is
    # the same name-lookup-feeding-a-kill form as pgrep|kill — and the natural
    # retry once pkill/pgrep is refused. ABS-294 NB1: keying on the literal
    # `grep` covered only half the vector class — `ps ax | awk '{print $1}' |
    # xargs kill` and the sed/cut variants are the CLASSIC idiom and sailed
    # through. Decide on ps's OWN mode instead: any non-`-p` ps in a command
    # that also carries a kill is a name/list lookup feeding a kill. The
    # legitimate `ps -p "$pid" >/dev/null && kill "$pid"` (a PID check, no
    # name lookup) stays allowed.
    if [ -z "$reason" ] && has_word "$cmd" "kill"; then
        while IFS= read -r seg; do
            [ -n "$seg" ] || continue
            if has_word "$seg" "ps" && ! seg_ps_is_pid_scoped "$seg"; then
                matched="ps|kill"
                reason="ps name/list lookup (ps without -p) feeding a kill matches processes by name/pattern"
                break
            fi
        done <<EOF
$(split_segments "$cmd")
EOF
    fi
fi

[ -n "$reason" ] || exit 0

# --- Blocked. Log (observability, AC4) then refuse (exit 2). -----------------
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u)
log="${ORCH_KILL_GUARD_LOG:-${TMPDIR:-/tmp}/orchestrator-kill-guard.log}"
# ABS-294 NB2: sanitize before logging — a newline embedded in the offending
# command would otherwise inject arbitrary LINES into the security log (a
# blocked seat could fabricate plausible audit entries in the very record an
# operator reads after an incident). The stderr message below keeps the raw
# command; only the audit record is flattened.
cmd_log=$(printf '%s' "$cmd" | tr '\n\r' '  ')
printf '%s BLOCKED seat=%s role=%s ticket=%s matched=%s reason=%s cmd=%s\n' \
    "$ts" "${ORCH_SEAT:-}" "${ORCH_ROLE:-}" "${ORCH_TICKET:-}" "$matched" "$reason" "$cmd_log" \
    >>"$log" 2>/dev/null || true

cat >&2 <<EOF
❌ BLOCKED (ABS-243 kill-guard): name-pattern process kill refused.
  Matched:  $matched
  Reason:   $reason
  Command:  $cmd
  A seat may kill ONLY processes it started — by PID or its own process group:
    kill "\$pid"           # a PID you remember
    pkill -P "\$pid"       # children of a PID you started
    pkill -g "\$pgid"      # your own process group   (pkill -s "\$sid" for session)
  NEVER kill by name/pattern (pkill -f / killall / kill \$(pgrep -f …) / a
  ps … | grep … lookup piped into a kill) — that can reap the operator's LIVE
  orchestrator (the exact incident ABS-243 fixes). NEVER broadcast (kill -9 -1):
  that signals EVERY process you own, the orchestrator included.
  Override (operator only): ORCH_KILL_GUARD=0
  Logged to: $log
EOF
exit 2
