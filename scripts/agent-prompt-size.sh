#!/usr/bin/env bash
# =============================================================================
# agent-prompt-size.sh — per-seat prompt-size SENSOR (PILOT-55 / ABS-566)
# =============================================================================
# Every spawn loads a seat's WHOLE composed prompt on every turn: the shared
# _common-rules.md (prepended by the spawn seam, ABS-174) + the role def + any
# project overlay (ADR-A-0022). That composed payload is the single largest
# controllable cost item in a run (22–60 % of paid input; see
# work/improvement-proposals/2026-07-25-token-efficiency-prefix-amplification.md).
#
# This sensor MEASURES that payload per role and compares it against a declared
# PROMPT-SIZE BUDGET (docs/sop/AGENT_CONFIGURATION_SOP.md → "Prompt Size Budget").
# A role over budget is a DEFECT, not an operating mode: `--check` exits non-zero
# when any role exceeds the budget. The measurement itself is the value — run with
# no arguments to print the current IST sizes for every seat, largest first.
#
# SIZE METHODOLOGY (raw file bytes, env-independent so results are reproducible):
#   composed = wc -c(_common-rules.md) + wc -c(<role>.md) + wc -c(<role>.append.md)
# This matches the numbers in ABS-566 (e.g. qas 37418 B, be-developer 27452 B,
# each incl. _common-rules.md at 13760 B).
#
# Usage:
#   scripts/agent-prompt-size.sh                 # report every seat's size (exit 0)
#   scripts/agent-prompt-size.sh --check         # gate: exit 1 if any seat over budget
#   scripts/agent-prompt-size.sh --budget 30000  # override the budget for this run
#
# Env overrides (for tests / self-hosting):
#   ORCH_PROMPT_SIZE_BUDGET   budget in bytes (default 24000)
#   ORCH_AGENTS_DIR           agent-def dir (default harness/claude/agents)
#   ORCH_OVERRIDES_DIR        overlay dir (default: none — overlays counted as 0)
#
# Bash 3.2 / BSD safe: no `grep -P`, no associative arrays, no `mapfile`.
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUDGET="${ORCH_PROMPT_SIZE_BUDGET:-24000}"
AGENTS_DIR="${ORCH_AGENTS_DIR:-$REPO_ROOT/harness/claude/agents}"
OVERRIDES_DIR="${ORCH_OVERRIDES_DIR:-}"
MODE="report"

while [ $# -gt 0 ]; do
    case "$1" in
        --check)          MODE="check" ;;
        --budget)         BUDGET="$2"; shift ;;
        --budget=*)       BUDGET="${1#--budget=}" ;;
        --agents-dir)     AGENTS_DIR="$2"; shift ;;
        --agents-dir=*)   AGENTS_DIR="${1#--agents-dir=}" ;;
        -h|--help)        sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "agent-prompt-size: unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

case "$BUDGET" in ''|*[!0-9]*) echo "agent-prompt-size: budget must be a positive integer: $BUDGET" >&2; exit 2 ;; esac
[ -d "$AGENTS_DIR" ] || { echo "agent-prompt-size: agents dir not found: $AGENTS_DIR" >&2; exit 2; }

fsize() { if [ -f "$1" ]; then wc -c < "$1" | tr -d '[:space:]'; else echo 0; fi; }

commons_sz="$(fsize "$AGENTS_DIR/_common-rules.md")"

# Collect one "total|role|role_sz|overlay_sz|status" row per spawnable role.
# Spawnable = a *.md def that is not underscore-prefixed (shared fragment) and
# not README.md — the same exclusion the spawn seam applies (ABS-174).
rows=""
count=0
over=0
for f in "$AGENTS_DIR"/*.md; do
    [ -f "$f" ] || continue
    b="$(basename "$f" .md)"
    case "$b" in _*|README) continue ;; esac
    role_sz="$(fsize "$f")"
    overlay_sz=0
    if [ -n "$OVERRIDES_DIR" ]; then
        overlay_sz="$(fsize "$OVERRIDES_DIR/$b.append.md")"
    fi
    total=$(( commons_sz + role_sz + overlay_sz ))
    count=$(( count + 1 ))
    status="ok"
    if [ "$total" -gt "$BUDGET" ]; then status="OVER"; over=$(( over + 1 )); fi
    rows="$rows$total|$b|$role_sz|$overlay_sz|$status
"
done

# Report, largest first.
printf '%-24s %8s %8s %8s  %s\n' "ROLE" "COMPOSED" "ROLE" "OVERLAY" "STATUS"
printf '%s' "$rows" | sort -t'|' -k1,1nr | while IFS='|' read -r total b role_sz overlay_sz status; do
    [ -n "$b" ] || continue
    printf '%-24s %8d %8d %8d  %s\n' "$b" "$total" "$role_sz" "$overlay_sz" "$status"
done
printf 'SUMMARY: %d/%d roles OVER budget (%d B); commons=%d B\n' "$over" "$count" "$BUDGET" "$commons_sz"

if [ "$MODE" = "check" ] && [ "$over" -gt 0 ]; then
    echo "agent-prompt-size: FAIL — $over role(s) exceed the ${BUDGET} B prompt-size budget (see docs/sop/AGENT_CONFIGURATION_SOP.md)" >&2
    exit 1
fi
exit 0
