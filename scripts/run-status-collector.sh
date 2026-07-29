#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Run-Status Collector (PILOT-41 / epic PILOT-39, twin ABS-550)
# =============================================================================
# Mechanical, read-only, NO LLM. Answers the operator's recurring "Status?"
# question in ONE call by gathering — in a single, stable, line-oriented,
# diffable report — the six facets from the Ops-Sweep plan §5:
#
#   1. ticket board by status          (via $TRACKER_CMD search)
#   2. spawn/cost state                (orchestrator state dir spawn-ledger)
#   3. open MRs, human-gate marked     (via $RUN_STATUS_MR_CMD, opt-in)
#   4. in-flight seats with runtime    (orchestrator state dir locks/)
#   5. sensor findings                 (scripts/ops-sweep-sensors.sh, PILOT-40)
#   6. next expected event             (derived mechanically)
#
# This is the raw-material producer that the `run-status` skill wraps in an
# ISOLATED fork: the fork condenses this into 5-10 prose lines and returns ONLY
# those, so the caller's context grows by lines, not the kilobytes of raw dumps
# (plan §5; falsifying eval #7).
#
# DESIGN INVARIANTS (why every section is ALWAYS printed):
#   - Silence must NEVER read as "all OK" (AC / eval #8). Every facet emits a
#     header line even when empty or unavailable: `humangate.count: 0`,
#     `sensors.status: unavailable`, never nothing.
#   - Output is deterministic and sorted so two runs `diff` to a real progress
#     delta (AC #3 — the signal for the ABS-547 budget auto-extend), not to
#     ordering noise.
#   - Read-only; exit 0 even with findings (same contract as the ops sensors).
#
# Inputs (all optional except a reachable tracker):
#   TRACKER_CMD              board source (default scripts/mock-tracker.sh)
#   ORCH_STATE_DIR           orchestrator run-state dir (spawns, locks, markers).
#                            Unset/missing -> those facets report "unavailable".
#   RUN_STATUS_MR_CMD        command printing one open MR per line as
#                            "<id> <target-branch>". Unset -> MRs "unavailable".
#   RUN_STATUS_SENSOR_CMD    path to the ops-sweep sensor script. Unset/missing
#                            -> autodetect the sibling ops-sweep-sensors.sh; a
#                            non-existent/non-executable path -> sensors report
#                            "unavailable" (test seam for the absent-sensor case).
#   RUN_STATUS_HUMAN_GATE_STATUSES  space/comma list overriding the default
#                            human-gate status set.
#   RUN_STATUS_PROTECTED_BRANCHES   space/comma list of protected merge targets
#                            (default "main master"); an open MR into one is a
#                            human-merge gate.
#
# Usage:  scripts/run-status-collector.sh
# =============================================================================

TRACKER_CMD="${TRACKER_CMD:-scripts/mock-tracker.sh}"

# Statuses that await a HUMAN action (PO decision / human acceptance / human
# merge). A ticket resting here is a human gate, never "in progress".
DEFAULT_HUMAN_GATE_STATUSES="Needs PO Decision|Ready for Human Acceptance|Story Acceptance|Ready for Epic Acceptance|Ready for Merge"
DEFAULT_PROTECTED_BRANCHES="main master"

# --- helpers ----------------------------------------------------------------

# branch_alt <space/comma list> -> a|b|c (for grep -E). Safe for branch names,
# which never contain spaces, so space IS a separator here.
branch_alt() { printf '%s' "$1" | tr ',' ' ' | tr -s ' ' '\n' | sed '/^$/d' | paste -sd'|' -; }

# status_alt <comma/pipe list> -> a|b|c. Statuses CONTAIN spaces (e.g. "Needs PO
# Decision"), so only comma/pipe separate — never space.
status_alt() { printf '%s' "$1" | tr ',' '|' | sed 's/ *| */|/g; s/^ *//; s/ *$//'; }

# mtime_epoch <path> -> seconds since epoch (BSD then GNU stat).
mtime_epoch() { stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0; }

HUMAN_GATE_RE="$(status_alt "${RUN_STATUS_HUMAN_GATE_STATUSES:-$DEFAULT_HUMAN_GATE_STATUSES}")"
PROTECTED_RE="$(branch_alt "${RUN_STATUS_PROTECTED_BRANCHES:-$DEFAULT_PROTECTED_BRANCHES}")"
NOW="$(date +%s)"

# Accumulate human-gate lines here (printed together at the end so the count is
# authoritative), so no facet can add a gate without it being counted.
GATES=""
add_gate() { GATES="${GATES}${GATES:+$'\n'}$1"; }

echo "# run-status $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --- 1. board by status ------------------------------------------------------
# search emits: id<TAB>type<TAB>status<TAB>priority<TAB>title (ABS-389).
board="$($TRACKER_CMD search 2>/dev/null || true)"
if [ -n "$board" ]; then
    # Per-status counts, sorted by status name (deterministic diff).
    printf '%s\n' "$board" | awk -F'\t' 'NF>=3{c[$3]++} END{for(s in c) printf "board.%s: %d\n", s, c[s]}' | sort
    total="$(printf '%s\n' "$board" | grep -c . || true)"
    echo "board.total: $total"
    # Human-gate: any ticket resting in a human-gate status.
    while IFS=$'\t' read -r id _type status _prio _title; do
        [ -n "${status:-}" ] || continue
        printf '%s' "$status" | grep -qE "^($HUMAN_GATE_RE)$" && add_gate "ticket $id — awaiting human ($status)"
    done <<EOF
$board
EOF
else
    echo "board.status: unavailable"
fi

# --- 2. spawns (from the orchestrator state dir) -----------------------------
SD="${ORCH_STATE_DIR:-}"
if [ -n "$SD" ] && [ -d "$SD" ]; then
    ledger_total=0
    for lg in "$SD"/spawn-ledger-*; do
        [ -e "$lg" ] || continue
        n="$(grep -c . "$lg" 2>/dev/null || echo 0)"
        ledger_total=$(( ledger_total + n ))
    done
    echo "spawns.total: $ledger_total"
else
    echo "spawns.status: unavailable"
fi

# --- 3. open MRs (opt-in; human-merge gate marked) ---------------------------
if [ -n "${RUN_STATUS_MR_CMD:-}" ]; then
    mrs="$(eval "$RUN_STATUS_MR_CMD" 2>/dev/null || true)"
    mr_count=0
    while read -r mr_id mr_target _rest; do
        [ -n "${mr_id:-}" ] || continue
        mr_count=$(( mr_count + 1 ))
        gate=no
        if printf '%s' "${mr_target:-}" | grep -qE "^($PROTECTED_RE)$"; then
            gate=yes
            add_gate "MR $mr_id — awaiting human merge into ${mr_target}"
        fi
        echo "mr.$mr_id: target=${mr_target:--} gate=$gate"
    done <<EOF
$mrs
EOF
    echo "mr.count: $mr_count"
else
    echo "mr.status: unavailable (set RUN_STATUS_MR_CMD)"
fi

# --- 4. in-flight seats (live locks) with runtime ----------------------------
inflight_count=0
oldest_ticket=""; oldest_role=""; oldest_age=-1
if [ -n "$SD" ] && [ -d "$SD/locks" ]; then
    for d in "$SD"/locks/*; do
        [ -d "$d" ] || continue
        ticket="$(basename "$d")"
        [ "$ticket" = "merge" ] && continue     # merge token, not a seat
        age=$(( NOW - $(mtime_epoch "$d") ))
        role="-"
        # Best-effort role: newest matching session file <ticket>.<role>.<stage>.
        for s in "$SD"/sessions/"$ticket".*; do
            [ -e "$s" ] || continue
            role="$(basename "$s" | awk -F. '{print $2}')"
        done
        echo "inflight.$ticket: role=$role age=${age}s"
        inflight_count=$(( inflight_count + 1 ))
        if [ "$age" -gt "$oldest_age" ]; then oldest_age=$age; oldest_ticket=$ticket; oldest_role=$role; fi
    done
    echo "inflight.count: $inflight_count"
else
    echo "inflight.status: unavailable"
fi

# --- run-health markers (also human gates when the run is paused) ------------
# Marker files carry CONTENT, not just presence. fastfail is a burst COUNTER the
# orchestrator RESETS to "0" in place (record_spawn_result) and leaves there
# while spawning continues; outage holds a real state line while paused. So a
# pause is a marker with a REAL value (non-empty, not "0") — existence alone is
# NOT (PILOT-74: a fastfail file containing "0" was wrongly read as a human gate
# while the runner kept spawning).
if [ -n "$SD" ] && [ -d "$SD" ]; then
    health="ok"
    for m in fastfail halt outage; do
        [ -e "$SD/$m" ] || continue
        val="$(tr -d '[:space:]' < "$SD/$m" 2>/dev/null || true)"
        case "$val" in
            ''|0) : ;;   # empty / reset-to-"0": cleared, NOT a pause
            *)
                health="paused"
                add_gate "run — paused ($m marker=$val; human restart/account may be required)"
                ;;
        esac
    done
    echo "run.health: $health"
else
    echo "run.health: unavailable"
fi

# --- 5. sensor findings (PILOT-40, optional) ---------------------------------
# Test seam (integration fix, epic PILOT-39): the sensor path is overridable so a
# suite can exercise the "sensors absent" branch. Without it the branch is
# unreachable once PILOT-40 shipped the script next to this one — the collector
# degrades correctly, but no test could prove it. Follows the script's own
# override idiom (RUN_STATUS_MR_CMD, RUN_STATUS_SPAWN_STATE_DIR): a plain seam,
# not an ORCH_* operator knob.
SENSORS="${RUN_STATUS_SENSOR_CMD:-$(dirname "$0")/ops-sweep-sensors.sh}"
if [ -x "$SENSORS" ]; then
    findings="$("$SENSORS" 2>/dev/null || true)"
    if [ -n "$findings" ]; then
        i=0
        while IFS= read -r line; do
            [ -n "$line" ] || continue
            i=$(( i + 1 )); echo "sensors.$i: $line"
        done <<EOF
$findings
EOF
        echo "sensors.count: $i"
    else
        echo "sensors.count: 0"
    fi
else
    echo "sensors.status: unavailable"
fi

# --- human gates (ALWAYS emitted; count is authoritative) --------------------
if [ -n "$GATES" ]; then
    i=0
    while IFS= read -r g; do
        [ -n "$g" ] || continue
        i=$(( i + 1 )); echo "humangate.$i: $g"
    done <<EOF
$GATES
EOF
    echo "humangate.count: $i"
else
    echo "humangate.count: 0"
fi

# --- 6. next expected event (derived) ----------------------------------------
if [ "$inflight_count" -gt 0 ]; then
    echo "next: handoff from $oldest_ticket (role=$oldest_role, running ${oldest_age}s)"
elif [ -n "$GATES" ]; then
    echo "next: human action — $(printf '%s\n' "$GATES" | head -1)"
elif [ -n "$board" ]; then
    echo "next: dispatch of a ready ticket"
else
    echo "next: idle (nothing pending)"
fi
