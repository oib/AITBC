#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Orchestrator cost report (ABS-120)
# =============================================================================
# SUPERSEDED (ABS-353, ABS-230 S8) — the agentic backend now serves these same
# aggregates as a board report view over the ingested telemetry (run_event):
#
#     GET /api/v1/projects/<project>/report?agent=<role>&run_id=<id>
#     Board view URL: /projects/<project>/report
#
# The board view reproduces every section below (per seat / per story / per epic /
# tools used) with the same numbers for the same input, and adds agent + run-ID
# filters. Prefer the board view; this script is retained (NOT deleted) for
# offline / no-backend use against a local run.log.
# -----------------------------------------------------------------------------
# Aggregates the SPAWN-USAGE lines the runner writes into the structured run
# log (one per spawn attempt: tokens_in= tokens_out= cost_usd=) per SEAT
# (role), per STORY (ticket) and — when a tracker is configured — per EPIC
# (ticket parent, resolved through the adapter, one `get` per distinct ticket).
#
# Usage:
#   scripts/orchestrator-report.sh [run.log]
#     default log: $ORCH_RUN_LOG, else $ORCH_STATE_DIR/run.log, else
#     <repo>/work/.orchestrator/run.log
#   TRACKER_CMD   task-tracking adapter for the epic section (optional; the
#                 section prints a notice and is skipped when unset/unusable)
#
# Zero-dependency bash+awk, like the runner. Lines with empty fields (crashes,
# foreign providers) count as a spawn but contribute 0 to the sums.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_STATE_DIR="${ORCH_STATE_DIR:-$REPO_ROOT/work/.orchestrator}"
RUN_LOG="${1:-${ORCH_RUN_LOG:-$ORCH_STATE_DIR/run.log}}"

[ -f "$RUN_LOG" ] || { echo "orchestrator-report: no run log at $RUN_LOG" >&2; exit 1; }

# usage_rows — TSV: ticket role tokens_in tokens_out cost
usage_rows() {
    awk -F'\t' '$2 == "SPAWN-USAGE" {
        ti = 0; to = 0; c = 0
        n = split($6, kv, " ")
        for (i = 1; i <= n; i++) {
            if (kv[i] ~ /^tokens_in=[0-9]+$/)  { sub(/^tokens_in=/, "", kv[i]);  ti = kv[i] }
            if (kv[i] ~ /^tokens_out=[0-9]+$/) { sub(/^tokens_out=/, "", kv[i]); to = kv[i] }
            if (kv[i] ~ /^cost_usd=[0-9.]+$/)  { sub(/^cost_usd=/, "", kv[i]);  c  = kv[i] }
        }
        printf "%s\t%s\t%s\t%s\t%s\n", $3, $4, ti, to, c
    }' "$RUN_LOG"
}

# aggregate <key-field(1=ticket,2=role)> <heading>
aggregate() {
    local field="$1" heading="$2"
    printf '\n%s\n' "$heading"
    printf '%-28s %8s %12s %12s %10s\n' "" "spawns" "tokens_in" "tokens_out" "cost_usd"
    usage_rows | awk -F'\t' -v f="$field" '
        {
            k = (f == 1 ? $1 : $2)
            n[k]++; ti[k] += $3; to[k] += $4; c[k] += $5
            tn++; tti += $3; tto += $4; tc += $5
        }
        END {
            for (k in n) printf "%-28s %8d %12d %12d %10.4f\n", k, n[k], ti[k], to[k], c[k] | "sort"
            close("sort")
            printf "%-28s %8d %12d %12d %10.4f\n", "TOTAL", tn, tti, tto, tc
        }'
}

epic_section() {
    printf '\nPer epic\n'
    if [ -z "${TRACKER_CMD:-}" ]; then
        echo "  (no TRACKER_CMD configured — epic aggregation skipped)"
        return 0
    fi
    # Resolve each distinct ticket's parent once, through the adapter only.
    # The ticket->parent map goes through a temp FILE: BSD awk rejects -v
    # values containing newlines, so multi-row data must never ride a -v.
    local tickets t parent map
    map="$(mktemp "${TMPDIR:-/tmp}/orch-report-map.XXXXXX")"
    tickets="$(usage_rows | cut -f1 | sort -u)"
    for t in $tickets; do
        parent="$(bash $TRACKER_CMD get "$t" 2>/dev/null | sed -n 's/^parent: //p' | head -1 || true)"
        printf '%s\t%s\n' "$t" "${parent:-<none>}" >> "$map"
    done
    usage_rows | awk -F'\t' -v mapfile="$map" '
        BEGIN {
            while ((getline line < mapfile) > 0) {
                split(line, m, "\t")
                parent[m[1]] = (m[2] == "" ? "<none>" : m[2])
            }
            close(mapfile)
            printf "%-28s %8s %12s %12s %10s\n", "", "spawns", "tokens_in", "tokens_out", "cost_usd"
        }
        {
            k = ($1 in parent ? parent[$1] : "<none>")
            n[k]++; ti[k] += $3; to[k] += $4; c[k] += $5
        }
        END {
            for (k in n) printf "%-28s %8d %12d %12d %10.4f\n", k, n[k], ti[k], to[k], c[k] | "sort"
            close("sort")
        }'
    rm -f "$map"
}

# --- ABS-125: per-role tools used vs granted ---------------------------------
# Mirrors the seam's ABS-96/ABS-92 resolution (ORCH_HARNESS_HOME, not the
# report's own repo — in self-hosting mode the defs live in the harness).
agents_dir() {
    local home="${ORCH_HARNESS_HOME:-$REPO_ROOT}"
    if [ -n "${ORCH_AGENTS_DIR:-}" ]; then echo "$ORCH_AGENTS_DIR"
    elif [ -d "$home/harness/claude/agents" ]; then echo "$home/harness/claude/agents"
    # Pre-v2.23.0 stable checkouts still use the dotted namespace.
    elif [ -d "$home/harness/.claude/agents" ]; then echo "$home/harness/.claude/agents"
    else echo "$home/.claude/agents"; fi
}

telemetry_section() {
    printf '\nPer role: tools used vs granted (ABS-125)\n'
    local rows
    rows="$(awk -F'\t' '$2 == "TELEMETRY" && $6 != "unavailable" && $6 != "" {print $4 "\t" $6}' "$RUN_LOG")"
    if [ -z "$rows" ]; then
        echo "  (no telemetry lines in this run log)"
        return 0
    fi
    local role used granted unused t
    for role in $(printf '%s\n' "$rows" | cut -f1 | sort -u); do
        used="$(printf '%s\n' "$rows" | awk -F'\t' -v r="$role" '
            $1 == r { n = split($2, kv, " "); for (i = 1; i <= n; i++) { split(kv[i], p, "="); sum[p[1]] += p[2] } }
            END { for (k in sum) printf "%s=%d\n", k, sum[k] }' | LC_ALL=C sort)"
        printf '  %s\n    used:    %s\n' "$role" "$(printf '%s' "$used" | tr '\n' ' ')"
        granted="$(sed -n 's/^tools:[[:space:]]*\[\(.*\)\]/\1/p' "$(agents_dir)/$role.md" 2>/dev/null | tr ',' '\n' | tr -d ' ' || true)"
        if [ -n "$granted" ]; then
            unused=""
            for t in $granted; do
                printf '%s\n' "$used" | grep -q "^$t=" || unused="$unused $t"
            done
            printf '    granted but never used:%s\n' "${unused:- (none)}"
        fi
    done
}

echo "Orchestrator cost report — $RUN_LOG"
aggregate 2 "Per seat (role)"
aggregate 1 "Per story (ticket)"
epic_section
telemetry_section
