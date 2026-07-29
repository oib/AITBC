#!/bin/bash
# =============================================================================
# Pre-Bash Hook: seat-independent merge chokepoint (PILOT-11 / twin ABS-513)
# =============================================================================
# PILOT-11-merge-guard  <- marker: keep this token; docs/tests grep for it.
#
# WHY. PILOT-10 delivered scripts/merge-target-guard.sh (the decision) plus a
# conformance test, but wired it in ONLY as PROSE in the rte duty-step. Prose was
# already ignored once: in v3-pilot #2 (2026-07-21) the RTE seat opened MR !150
# (PILOT-3-auto -> main) and merged it ITSELF, bypassing the ADR-A-0004/0005
# human-merge boundary. A rule a seat can skip is not enforcement. This hook makes
# the guard MECHANICALLY UNSKIPPABLE: it runs on EVERY Bash tool call, before the
# merge command can reach the git host, independent of whether the seat ran the
# duty-step. #PATH_DECISION (spawn-seam vs permission-layer): the spawn seam only
# controls how a seat is LAUNCHED, never the `bb pr merge`/`glab mr merge` it types
# inside its own shell — so it cannot be a merge chokepoint. A PreToolUse Bash
# guard fires on every Bash call regardless of seat cooperation. It is the same
# proven mechanism already shipped for the shared-stash guard, the kill guard, and
# the push-to-main block. Chosen: the permission layer (this hook).
#
# WHAT IT DOES. A Claude Code PreToolUse hook on the Bash tool. It reads the
# command from the stdin JSON payload (.tool_input.command) and, for a merge-API
# call only (`bb pr merge …` / `glab mr merge …`):
#   1. resolves the MR/PR's TARGET branch (see RESOLUTION below);
#   2. runs `scripts/merge-target-guard.sh check <target>`;
#   3. REFUSE (guard exit 1, target on ORCH_PROTECTED_BRANCHES / main) -> BLOCK the
#      tool (exit 2): the merge never runs. The guard's machine-greppable
#      `MERGE-GUARD-REFUSE … action=hitl-handoff` intent line is surfaced to the
#      seat (stderr) and appended to the guard log. Hand off to HITL.
#   4. ALLOW (guard exit 0, e.g. an epic/* target) -> exit 0: the merge proceeds
#      exactly as before (the legitimate ORCH_AUTOMERGE=1 epic-branch auto-merge,
#      ADR-A-0014, is never a false-positive block).
# Any non-merge command (git status, `bb pr view`, `bb pr create`, …) is allowed
# untouched.
#
# RESOLUTION. The target branch is a server-side property of the MR/PR, so the hook
# resolves it, in order:
#   (a) ORCH_MERGE_GUARD_TARGET_CMD — an operator/test resolver run as
#       `$ORCH_MERGE_GUARD_TARGET_CMD <id>`, printing the target branch. This is
#       the host-agnostic test seam (the conformance test injects it) and the
#       operator override for exotic forges.
#   (b) native forge view: `glab mr view <id>` / `bb pr view <id>` JSON.
# If the target cannot be resolved, the hook FAILS CLOSED (blocks, exit 2) on the
# merge boundary — an unverifiable merge is handed to HITL, never waved through
# (#EXPORT_CRITICAL: this hook IS the human-merge boundary). Its blast radius is
# narrow: ONLY `bb pr merge`/`glab mr merge` are ever inspected.
#
# SCOPE. Fires ONLY for orchestrator SEATS — the spawn seam exports the ORCH_SEAT /
# ORCH_TICKET / ORCH_ROLE markers. A human's own interactive shell carries none of
# them and is NEVER guarded (same boundary as the stash / kill / local-main
# guards): the operator keeps full authority over their own repo.
#
# KILL SWITCH (ABS-111 pattern). ORCH_MERGE_GUARD default ON (=1). Set
# ORCH_MERGE_GUARD=0 to restore the legacy unguarded behavior.
#
# OBSERVABILITY (ABS-66). Every blocked merge is appended to the guard log
# (ORCH_MERGE_GUARD_LOG, default $TMPDIR/orchestrator-merge-guard.log) with a UTC
# timestamp, the seat identity, the resolved target, and the offending command.
#
# FAIL-OPEN on infra gaps only. Missing jq, empty command, or a non-seat context
# -> exit 0 (allow); those never touch the merge boundary. A genuine merge whose
# target cannot be resolved fails CLOSED (above).
#
# bash 3.2 + BSD tools only.
# =============================================================================

set -u

# --- Kill switch (ABS-111): default ON. Off -> allow unconditionally. --------
if [ "${ORCH_MERGE_GUARD:-1}" = "0" ]; then
    exit 0
fi

payload=$(cat)

command -v jq >/dev/null 2>&1 || { echo 'hooks: jq not found; skipping merge-guard' >&2; exit 0; }

cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

# --- Seat context only. A human shell carries no seat marker -> never guarded.
if [ -z "${ORCH_SEAT:-}${ORCH_TICKET:-}${ORCH_ROLE:-}" ]; then
    exit 0
fi

# Flatten to a single line so a multi-line command is matched as a whole.
flat=$(printf '%s' "$cmd" | tr '\n' ' ')

# --- Detect a merge-API call and pull its MR/PR id. Only the exact `merge`
#     subcommand counts — `bb pr view` / `glab mr create` are NOT merges.
mergecmd=""
if printf '%s' "$flat" | grep -qE '(^|[^[:alnum:]_./-])bb[[:space:]]+pr[[:space:]]+merge([[:space:]]|$)'; then
    mergecmd="bb pr merge"
    rest=$(printf '%s' "$flat" | sed -E 's/.*bb[[:space:]]+pr[[:space:]]+merge[[:space:]]*//')
elif printf '%s' "$flat" | grep -qE '(^|[^[:alnum:]_./-])glab[[:space:]]+mr[[:space:]]+merge([[:space:]]|$)'; then
    mergecmd="glab mr merge"
    rest=$(printf '%s' "$flat" | sed -E 's/.*glab[[:space:]]+mr[[:space:]]+merge[[:space:]]*//')
fi
[ -n "$mergecmd" ] || exit 0   # not a merge-API call -> allow, untouched.

# First bare integer after `merge` is the MR/PR id (may be empty; the resolver
# decides what to do with that).
id=$(printf '%s' "$rest" | grep -oE '[0-9]+' | head -1)

# --- Resolve the MR/PR TARGET branch (see RESOLUTION in the header). ----------
target=""
if [ -n "${ORCH_MERGE_GUARD_TARGET_CMD:-}" ]; then
    target=$($ORCH_MERGE_GUARD_TARGET_CMD "$id" 2>/dev/null | head -1 | tr -d '[:space:]')
elif [ "$mergecmd" = "glab mr merge" ] && command -v glab >/dev/null 2>&1; then
    target=$(glab mr view "$id" -F json 2>/dev/null | jq -r '.target_branch // empty' 2>/dev/null)
elif [ "$mergecmd" = "bb pr merge" ] && command -v bb >/dev/null 2>&1; then
    target=$(bb pr view "$id" --json 2>/dev/null | jq -r '.destination.branch.name // .destination_branch // empty' 2>/dev/null)
fi

log="${ORCH_MERGE_GUARD_LOG:-${TMPDIR:-/tmp}/orchestrator-merge-guard.log}"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u)
# ABS-294 NB2: flatten newlines so a crafted command cannot inject audit lines.
cmd_log=$(printf '%s' "$cmd" | tr '\n\r' '  ')

_block() {  # $1 = reason line, $2 = optional guard intent line
    printf '%s BLOCKED seat=%s role=%s ticket=%s target=%s mergecmd=%s cmd=%s\n' \
        "$ts" "${ORCH_SEAT:-}" "${ORCH_ROLE:-}" "${ORCH_TICKET:-}" "${target:-<unresolved>}" \
        "$mergecmd" "$cmd_log" >>"$log" 2>/dev/null || true
    {
        echo "❌ BLOCKED (PILOT-11 merge-guard): $mergecmd refused before it reached the git host."
        [ -n "${2:-}" ] && echo "  $2"
        echo "  Reason:   $1"
        echo "  Command:  $cmd"
        echo "  A seat may NEVER merge onto a protected branch (main / ORCH_PROTECTED_BRANCHES);"
        echo "  auto-merge is legitimate ONLY onto an epic integration branch (ADR-A-0014), and"
        echo "  the human-merge boundary (ADR-A-0004/0005) is not a seat's to cross. Hand off to"
        echo "  HITL for this merge — do NOT merge it yourself."
        echo "  Override (operator only): ORCH_MERGE_GUARD=0"
        echo "  Logged to: $log"
    } >&2
}

# Unresolvable target -> fail CLOSED on the merge boundary.
if [ -z "$target" ]; then
    _block "could not resolve the MR/PR target branch — an unverifiable merge is not waved through."
    exit 2
fi

# --- The chokepoint: the guard's decision on the RESOLVED target is authoritative.
guard="${CLAUDE_PROJECT_DIR:-.}/scripts/merge-target-guard.sh"
[ -f "$guard" ] || guard="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." 2>/dev/null && pwd)/scripts/merge-target-guard.sh"
if [ ! -f "$guard" ]; then
    _block "scripts/merge-target-guard.sh not found — cannot verify the merge target."
    exit 2
fi

if ! guard_out=$(bash "$guard" check "$target" 2>/dev/null); then
    # REFUSE: surface the guard's own MERGE-GUARD-REFUSE … action=hitl-handoff line.
    intent=$(printf '%s' "$guard_out" | grep 'MERGE-GUARD-REFUSE' | head -1)
    _block "merge-target-guard REFUSED: target '$target' is protected." "$intent"
    exit 2
fi

# ALLOW: not a protected target -> the merge proceeds untouched.
exit 0
