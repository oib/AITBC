#!/usr/bin/env bash
# =============================================================================
# ci-capacity-probe.sh — tell "the CI can't RUN" apart from "the CI FAILED",
# and bound the wait on a pipeline so a stuck one is a NAMED state, not a
# silent budget burn (ABS-595).
# -----------------------------------------------------------------------------
# WHY. v2.33.0 shipped `.gitlab-ci.yml` (ABS-559). An epic branch inherited it,
# but the project has NO registered runner (ABS-593), so every pipeline dies in
# the stuck-timeout: status=failed, failure_reason=stuck_or_timeout_failure,
# duration=None. The RTE seat then WAITED on a pipeline that structurally CANNOT
# finish, burning its turn budget, and five of twelve stories rested at
# `Ready for Merge` overnight (Pilot 8, 2026-07-26/27). A CI config without
# execution capacity is worse than no CI config: without it the automerge lane
# moves; with it the lane stops.
#
# Two mechanically-checkable GitLab facts fix this (ABS-595 AC2): the pipeline's
# `failure_reason` and the project runner list. `stuck_or_timeout_failure` with
# zero available runners is INFRASTRUCTURE — not the story's fault, and it must
# NOT block the merge. A `script_failure` with runners present is a REAL red.
#
# CONTRACT — the pure `classify` is the heart; branch on its EXIT CODE:
#
#   classify <status> <failure_reason> <runner_count>
#       0  GREEN         pipeline succeeded
#       1  RED           a real job failure (runners present) — a true signal, BLOCK
#       2  NO-CAPACITY   infra can't run it (0 runners, or stuck_or_timeout /
#                        runner_system_failure) — NOT the story's fault, do NOT block
#       3  PENDING       still running / queued — keep waiting (bounded, see `wait`)
#     ( 64 usage error )
#     failure_reason / runner_count may be "-" or "" when unknown.
#
#   wait <deadline_secs> <interval_secs> <poll_cmd...>
#       polls <poll_cmd> (which must print "<status> <failure_reason> <runner_count>")
#       every <interval_secs>; returns the classify code the moment the pipeline
#       reaches a terminal verdict (GREEN/RED/NO-CAPACITY). If it is still PENDING
#       when <deadline_secs> elapses, prints PIPELINE-WAIT-TIMEOUT and exits 124
#       (124 == GNU timeout's code, the ABS-573 per-suite-watchdog contract) — a
#       NAMED timeout, never an unbounded wait.
#
#   verdict <project> <mr_iid>     (live; needs glab) — read the MR's latest
#       pipeline status + failed-job failure_reason + online-runner count off the
#       GitLab API, classify them, print the verdict, exit with the classify code.
#
#   runners <project>              (live; needs glab) — count runners that could
#       actually pick up a job (active AND online). Prints the integer.
# =============================================================================
set -uo pipefail

GLAB="${GLAB_CMD:-glab}"

die() { echo "ci-capacity-probe: $*" >&2; exit 64; }

# ---- the heart: pure classifier (no I/O, fixture-testable) ------------------
# classify <status> <failure_reason> <runner_count>
classify() {
    local status="${1:-}" reason="${2:--}" runners="${3:--}"
    [ -n "$status" ] || die "classify needs <status> <failure_reason> <runner_count>"
    # normalise the "unknown" sentinels
    [ "$reason" = "-" ] && reason=""
    case "$runners" in ''|-|*[!0-9]*) runners="" ;; esac   # blank unless a plain integer

    # 1. Success stands on its own — a cached/allowed green is green even if the
    #    project has since lost its runners.
    if [ "$status" = "success" ]; then
        echo "GREEN"; return 0
    fi
    # 2. Hard infra fact: zero runners that can pick up a job. Nothing non-green
    #    can EVER progress, so this is capacity, not a story defect (AC2).
    if [ "$runners" = "0" ]; then
        echo "NO-CAPACITY runners=0"; return 2
    fi
    # 3. A failed pipeline whose reason is a runner/stuck class is infra too —
    #    the exact stuck_or_timeout_failure the incident produced (AC2).
    if [ "$status" = "failed" ]; then
        case "$reason" in
            stuck_or_timeout_failure|runner_system_failure|scheduler_failure|no_matching_runner)
                echo "NO-CAPACITY reason=$reason"; return 2 ;;
            *)
                echo "RED reason=${reason:-unknown}"; return 1 ;;   # a genuine red signal — BLOCK
        esac
    fi
    # 4. Still in flight — the caller keeps waiting, but bounded (see `wait`).
    case "$status" in
        running|pending|created|scheduled|preparing|waiting_for_resource)
            echo "PENDING status=$status"; return 3 ;;
    esac
    # 5. Anything else (canceled/skipped/manual/blank/unknown) is not a real red
    #    and not green — treat as still-pending so a bounded wait, not a block.
    echo "PENDING status=${status:-unknown}"; return 3
}

# ---- bounded wait (AC1) — a stuck pipeline becomes a NAMED timeout -----------
# wait <deadline_secs> <interval_secs> <poll_cmd...>
cmd_wait() {
    local deadline="${1:-}" interval="${2:-}"; shift 2 || true
    case "$deadline" in ''|*[!0-9]*) die "wait needs <deadline_secs> <interval_secs> <poll_cmd...>" ;; esac
    case "$interval" in ''|*[!0-9]*) die "wait needs a numeric <interval_secs>" ;; esac
    [ "$#" -gt 0 ] || die "wait needs a <poll_cmd>"
    local -a poll=( "$@" )                        # keep the poll cmd out of $@ (re-run each loop)
    local start now line status reason runners rc verdict
    start="$(date +%s)"
    while :; do
        # poll_cmd prints "<status> <failure_reason> <runner_count>"
        line="$( "${poll[@]}" 2>/dev/null )" || true
        read -r status reason runners <<<"$line"
        rc=0; verdict="$(classify "${status:-unknown}" "${reason:--}" "${runners:--}")" || rc=$?
        [ "$rc" -ne 3 ] && { echo "$verdict"; return "$rc"; }   # terminal verdict — stop waiting
        now="$(date +%s)"
        if [ $((now - start)) -ge "$deadline" ]; then
            echo "PIPELINE-WAIT-TIMEOUT after=${deadline}s status=${status:-unknown} (bounded wait, ABS-595 AC1 — not a silent budget burn)"
            return 124
        fi
        sleep "$interval"
    done
}

# ---- live GitLab reads (best-effort; needs glab) ----------------------------
# runners <project> — count of runners that can actually pick up a job.
cmd_runners() {
    local proj="${1:-}"
    [ -n "$proj" ] || die "runners needs <project>"
    command -v "$GLAB" >/dev/null 2>&1 || die "glab not found (set GLAB_CMD)"
    "$GLAB" api "projects/${proj//\//%2F}/runners?per_page=100" 2>/dev/null \
        | tr ',' '\n' | grep -c '"online":true' 2>/dev/null || echo 0
}

# verdict <project> <mr_iid> — classify the MR's latest pipeline live.
cmd_verdict() {
    local proj="${1:-}" iid="${2:-}" pid status reason runners
    [ -n "$proj" ] && [ -n "$iid" ] || die "verdict needs <project> <mr_iid>"
    command -v "$GLAB" >/dev/null 2>&1 || die "glab not found (set GLAB_CMD)"
    local p="projects/${proj//\//%2F}"
    # latest pipeline id + status for the MR
    read -r pid status < <("$GLAB" api "$p/merge_requests/$iid/pipelines?per_page=1" 2>/dev/null \
        | tr ',' '\n' | awk -F: '
            /"id":/    && !have_id  { gsub(/[^0-9]/,"",$2); id=$2; have_id=1 }
            /"status":/&& !have_st  { gsub(/[^a-z_]/,"",$2); st=$2; have_st=1 }
            END { print id, st }')
    status="${status:-unknown}"
    reason="-"
    if [ "$status" = "failed" ] && [ -n "${pid:-}" ]; then
        reason="$("$GLAB" api "$p/pipelines/$pid/jobs?per_page=100" 2>/dev/null \
            | tr ',' '\n' | grep '"failure_reason":' | head -1 \
            | sed -E 's/.*"failure_reason":"?([a-z_]*)"?.*/\1/')"
        [ -n "$reason" ] || reason="-"
    fi
    runners="$(cmd_runners "$proj")"
    classify "$status" "$reason" "$runners"
}

case "${1:-}" in
    classify) shift; classify "$@" ;;
    wait)     shift; cmd_wait "$@" ;;
    runners)  shift; cmd_runners "$@" ;;
    verdict)  shift; cmd_verdict "$@" ;;
    -h|--help|help|"") sed -n '2,60p' "$0" ;;
    *) die "unknown subcommand '$1' (classify|wait|runners|verdict)" ;;
esac
