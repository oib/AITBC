#!/usr/bin/env bash
# rebase-gate-check.sh — degraded, git-only rebase-gate for the jira/mock profile (ABS-398).
#
# WHY (epic ABS-392, backing lever 2): at Story Acceptance the story branch must
# already sit on the current epic tip, so a late rebase conflict costs only the
# Dev step, not the whole gate chain. The v3-native profile (agentic-backend) has
# a backend-computed `merge_readiness` field and enforces this in the transition
# guard (ABS-397). The jira/mock profile has NO computed fields, so the QAS/PO
# seat runs THIS check by hand against the epic branch — same accept/reject
# outcome, git only, no backend.
#
# THE primitive (identical to merge-status.sh `on-target`, and to the native
# guard's semantics): is the epic tip already an ancestor of the story branch?
#     git merge-base --is-ancestor <epic-ref> <story-ref>
#         exit 0  -> epic tip contained  -> clean         (no rebase needed)
#         exit 1  -> epic advanced past  -> rebase-needed
#
# Subcommands and their exit codes (this is the contract — branch on these):
#
#   readiness <epic-ref> <story-ref>
#       0  clean          (story branch already contains the epic tip)
#       1  rebase-needed  (epic advanced; story must rebase onto the tip)
#
#   gate <epic-ref> <story-ref> [reason...]
#       Mirrors the native Story-Acceptance guard (ABS-397) exactly:
#       0  ACCEPT  — readiness=clean, OR rebase-needed but the move documents a
#                    rebase (reason mentions the word "rebased", case-insensitive)
#       1  REJECT  — rebase-needed and no documented rebase in the reason
#       The reason text is echoed on ACCEPT so the caller records it as the
#       transition's rebase evidence (the degraded stand-in for the native
#       event payload).
#
# Refs: pass any git ref. The epic integration branch is `epic/<parent>-*`
# (ORCHESTRATOR_SOP.md; lexicographic pick on multi-match). Fetch it first if it
# lives only on the remote — a stale local ref lies.
#
# Usage / bad refs / CLI errors exit 64.
set -uo pipefail

die() { echo "rebase-gate-check: $*" >&2; exit 64; }

# clean (0) / rebase-needed (1). Anything else (bad ref) -> 64 via die.
_readiness() {
    local epic="$1" story="$2"
    git rev-parse --verify -q "$epic^{commit}" >/dev/null 2>&1 || die "unknown epic ref '$epic'"
    git rev-parse --verify -q "$story^{commit}" >/dev/null 2>&1 || die "unknown story ref '$story'"
    git merge-base --is-ancestor "$epic" "$story" 2>/dev/null
}

cmd_readiness() {
    local epic="${1:-}" story="${2:-}"
    [ -n "$epic" ] && [ -n "$story" ] || die "readiness needs <epic-ref> <story-ref>"
    if _readiness "$epic" "$story"; then
        echo "clean: $story already contains the tip of $epic (no rebase needed)"
        return 0
    fi
    echo "rebase-needed: $epic has advanced past $story — rebase onto the epic tip"
    return 1
}

cmd_gate() {
    local epic="${1:-}" story="${2:-}"
    [ -n "$epic" ] && [ -n "$story" ] || die "gate needs <epic-ref> <story-ref> [reason]"
    shift 2
    local reason="$*"
    if _readiness "$epic" "$story"; then
        echo "ACCEPT: merge_readiness=clean"
        return 0
    fi
    # rebase-needed — the native guard allows it only when the SAME move documents
    # a rebase. Degraded equivalent: the seat's transition reason says "rebased".
    if printf '%s' "$reason" | grep -qiE 'rebased'; then
        echo "ACCEPT: rebase-needed but rebase documented in the move — evidence: $reason"
        return 0
    fi
    echo "REJECT: merge_readiness=rebase-needed and no documented rebase — rebase onto $epic, then retry (record 'rebased ...' in the move)" >&2
    return 1
}

case "${1:-}" in
    readiness) shift; cmd_readiness "$@" ;;
    gate)      shift; cmd_gate "$@" ;;
    -h|--help|help|"") sed -n '2,45p' "$0" ;;
    *) die "unknown subcommand '$1' (readiness|gate)" ;;
esac
