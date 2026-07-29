#!/usr/bin/env bash
set -uo pipefail

# =============================================================================
# Shadow Dual-Write Tracker Shim (epic ABS-326, story ABS-327 / Koexistenz S1)
# =============================================================================
# A $TRACKER_CMD drop-in for the SHADOW phase of the Jira -> agentic-backend
# migration (docs/sop/TRACKER-MIGRATION-RUNBOOK.md): every tracker operation
# goes PRIMARILY to Jira (scripts/jira-tracker.sh) — its stdout, stderr and
# exit code are the caller's, byte-identical. Mutating operations are
# ADDITIONALLY mirrored to the v3 backend adapter (scripts/backend-tracker.sh).
# Mirror failures are ONLY logged (replay-able, see below), never surfaced to
# the caller — blast radius on the running lane is zero (ADR-A-0010).
#
#     TRACKER_CMD=scripts/shadow-tracker.sh scripts/orchestrator.sh
#
# What gets mirrored (and what not):
#   * Mutating ops — create, update, comment, transition, link, assign — are
#     replayed verbatim against $SHADOW_MIRROR_CMD after the primary op
#     SUCCEEDED (a failed primary op changed no state, so there is nothing to
#     mirror).
#   * Read ops — get, search, children, parent, child-count, packet,
#     capabilities, help — touch no state; mirroring them would only double
#     latency and log noise, so they pass straight through.
#   * `events` is a read WITH adapter-local cursor state; mirroring it would
#     advance the backend's event cursor without a consumer and silently drop
#     events for a later pilot lane. Passthrough only.
#
# Key parity (epic ABS-326 prerequisite: "the backend carries the ABS keys
# 1:1, no mapping"): the backend assigns its own key on `create`, so the shim
# compares the mirror's created key against the primary's. While every create
# flows through the shim the sequences stay in lockstep; a mismatch is logged
# as `key-mismatch` (a divergence-reporter finding, not a caller error).
#
# Mirror log (replay format): every missed/failed mirror op appends ONE line
#     <utc-timestamp> rc=<mirror-exit> [key-mismatch primary=<k> mirror=<k>] -- <argv, %q-quoted>
# plus `#`-prefixed context lines (mirror stderr excerpt). Replay a line by
# feeding everything after " -- " back to the mirror adapter:
#     eval "scripts/backend-tracker.sh <text after ' -- '>"
# (%q quoting makes that eval-safe for multi-line bodies and quotes).
#
# Env:
#   SHADOW_PRIMARY_CMD  primary adapter (default scripts/jira-tracker.sh)
#   SHADOW_MIRROR_CMD   mirror adapter  (default scripts/backend-tracker.sh)
#   SHADOW_MIRROR_LOG   replay log      (default work/.shadow-mirror.log,
#                       gitignored runtime state)
# The mirror adapter reads its own env (BACKEND_URL/BACKEND_TOKEN/
# TRACKER_PROJECT); the shim passes the environment through untouched.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PRIMARY_CMD="${SHADOW_PRIMARY_CMD:-$REPO_ROOT/scripts/jira-tracker.sh}"
MIRROR_CMD="${SHADOW_MIRROR_CMD:-$REPO_ROOT/scripts/backend-tracker.sh}"
MIRROR_LOG="${SHADOW_MIRROR_LOG:-$REPO_ROOT/work/.shadow-mirror.log}"

timestamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# quoted_argv <args...> — emit the argv %q-quoted on one line (eval-safe replay).
quoted_argv() {
    local out="" a
    for a in "$@"; do
        out="$out$(printf '%q' "$a") "
    done
    printf '%s' "${out% }"
}

# log_miss <mirror-rc> <extra> <stderr-file> <args...> — append one replay line
# (+ commented stderr context) to the mirror log. Never fails the caller: the
# log write itself is best-effort (a read-only FS must not break the lane).
log_miss() {
    local rc="$1" extra="$2" errf="$3"; shift 3
    {
        mkdir -p "$(dirname "$MIRROR_LOG")"
        {
            printf '%s rc=%s%s -- %s\n' "$(timestamp)" "$rc" "${extra:+ $extra}" "$(quoted_argv "$@")"
            if [ -s "$errf" ]; then
                sed 's/^/#   /' "$errf"
            fi
        } >> "$MIRROR_LOG"
    } 2>/dev/null || true
}

# mirror_op <primary-stdout-file> <args...> — replay a mutating op against the
# mirror adapter. All mirror output is captured; nothing reaches the caller.
mirror_op() {
    local primary_out="$1"; shift
    local cmd="$1"
    local m_out m_err m_rc=0
    m_out="$(mktemp "${TMPDIR:-/tmp}/shadow-mirror-out.XXXXXX")"
    m_err="$(mktemp "${TMPDIR:-/tmp}/shadow-mirror-err.XXXXXX")"

    if [ -x "$MIRROR_CMD" ] || command -v "$MIRROR_CMD" >/dev/null 2>&1; then
        "$MIRROR_CMD" "$@" > "$m_out" 2> "$m_err" || m_rc=$?
    else
        m_rc=127
        printf 'mirror adapter not found/executable: %s\n' "$MIRROR_CMD" > "$m_err"
    fi

    if [ "$m_rc" -ne 0 ]; then
        log_miss "$m_rc" "" "$m_err" "$@"
    elif [ "$cmd" = "create" ]; then
        # Key-parity check: both adapters print the new id as the first token.
        local p_key m_key
        p_key="$(head -n1 "$primary_out" | awk '{print $1}')"
        m_key="$(head -n1 "$m_out" | awk '{print $1}')"
        if [ -n "$p_key" ] && [ "$p_key" != "$m_key" ]; then
            log_miss 0 "key-mismatch primary=$p_key mirror=$m_key" "$m_err" "$@"
        fi
    fi
    rm -f "$m_out" "$m_err"
}

main() {
    local cmd="${1:-}"

    # Primary op: stdout is buffered to a temp file and re-emitted byte-exact
    # (create's new id is needed for the key-parity check); stderr and exit
    # code pass through untouched. The caller sees exactly what the primary
    # adapter produced — the shim adds nothing on any stream.
    local p_out p_rc=0
    p_out="$(mktemp "${TMPDIR:-/tmp}/shadow-primary-out.XXXXXX")"
    "$PRIMARY_CMD" "$@" > "$p_out" || p_rc=$?
    cat "$p_out"

    if [ "$p_rc" -eq 0 ]; then
        case "$cmd" in
            create|update|comment|transition|link|assign)
                mirror_op "$p_out" "$@"
                ;;
        esac
    fi

    rm -f "$p_out"
    exit "$p_rc"
}

main "$@"
