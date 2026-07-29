#!/usr/bin/env bash
# merge-target-guard.sh — mechanical guard: an RTE seat may NEVER merge onto a
# protected branch (main), independent of ORCH_AUTOMERGE (PILOT-10 / twin ABS-513).
#
# WHY. The rule "Story PRs target the epic branch, never main — no environment
# knob ever changes that" (rte.md) is PROSE, and prose was ignored: in v3-pilot #2
# (2026-07-21) the RTE seat opened MR !150 (PILOT-3-auto -> main) and merged it
# ITSELF, justifying it with `ORCH_AUTOMERGE=1` — a value the launcher had never
# even set. The human-merge gate (ADR-A-0004/0005) was fully bypassed. Auto-merge
# is legitimate ONLY for story MRs onto an epic integration branch (ADR-A-0014),
# never onto main. This guard turns that prose into a MECHANICAL check the seat
# runs before EVERY merge-API call: target on the protected set -> refuse.
#
# The guard NEVER reads ORCH_AUTOMERGE for its decision — a seat's claim about the
# knob can never buy a main merge (AC2). It only inspects the merge TARGET branch.
#
# Env knob (optional):
#   ORCH_PROTECTED_BRANCHES  space-separated protected branch names
#                            (default: "main master"; same knob & default as
#                             hooks/pre-commit-local-main-guard.sh — one contract).
#
# PILOT-21 — stacked-MR loss class. A story/follow-up MR must target ONLY the epic
# integration branch (epic/*) or a protected branch (main, handed to HITL); it must
# NEVER be stacked onto a SIBLING story branch (`<ticket>-auto`). In v3-pilot #3
# (2026-07-23) the PILOT-13 seat opened !163 stacked on PILOT-9-auto and merged it
# there; the later base-rebase of PILOT-9 dropped the stacked commits and the
# delivery (nosniff header + RFC-5987 filename) silently never reached the epic
# branch. This guard also REFUSES a bare story-branch target so the stack can never
# form: valid targets are epic/* or main — a `*-auto` target is the loss signature.
#
# Subcommands and their exit codes (this is the contract — branch on these):
#
#   check <target-branch>
#       0  ALLOW   — target is NOT protected and NOT a sibling story branch (e.g.
#                    epic/*); the normal ORCH_AUTOMERGE=1 auto-merge onto the epic
#                    branch may proceed.
#       1  REFUSE  — target IS a protected branch (main / ORCH_PROTECTED_BRANCHES),
#                    OR a sibling story branch (`<ticket>-auto`, stacked-MR class,
#                    PILOT-21). The seat must NOT merge; hand off to HITL / retarget
#                    the MR. An intent-log line (`MERGE-GUARD-REFUSE ...`) is printed
#                    to stdout for the record.
#
# Usage / bad input exit 64.
#
# Pure + side-effect-free apart from the printed lines: invoked directly by
# tests/test-merge-target-guard.sh. bash 3.2 + BSD tools only.
set -uo pipefail

die() { echo "merge-target-guard: $*" >&2; exit 64; }

# Normalise a ref to a bare branch name: strip refs/heads/, refs/remotes/<r>/,
# and a leading <remote>/ (origin/main -> main), so `check origin/main` is caught.
_bare() {
    local ref="$1"
    ref="${ref#refs/heads/}"
    ref="${ref#refs/remotes/}"
    case "$ref" in
        origin/*|upstream/*) ref="${ref#*/}" ;;
    esac
    printf '%s' "$ref"
}

cmd_check() {
    local target="${1:-}"
    [ -n "$target" ] || die "check needs <target-branch>"
    local bare protected
    bare="$(_bare "$target")"
    # Same knob & default as the local-main-guard: one protected-branch contract.
    protected="${ORCH_PROTECTED_BRANCHES:-main master}"

    for p in $protected; do
        if [ "$bare" = "$p" ]; then
            # Intent-log line — machine-greppable, printed regardless of any
            # ORCH_AUTOMERGE value (AC2). The transcript is the intent log.
            echo "MERGE-GUARD-REFUSE target=$bare automerge=${ORCH_AUTOMERGE:-<unset>} action=hitl-handoff"
            cat >&2 <<EOF
merge-target-guard: REFUSE — a seat may NEVER merge onto protected branch '$bare'.
  ORCH_AUTOMERGE ('${ORCH_AUTOMERGE:-<unset>}') does not apply: auto-merge is legitimate
  ONLY for story MRs onto an epic integration branch (ADR-A-0014), never onto main
  (ADR-A-0004/0005). Hand off to HITL for the merge; do NOT merge this MR yourself.
EOF
            return 1
        fi
    done

    # PILOT-21 stacked-MR guard: a bare story branch (`<ticket>-auto`, no slash) is
    # NEVER a legitimate MR target. Valid targets are the epic integration branch
    # (epic/*, has a slash) or a protected branch (handled above). Stacking a story
    # MR onto a sibling story branch silently loses the delivery when that base is
    # later rebased (v3-pilot #3, !163 -> PILOT-9-auto). Refuse it here so the stack
    # can never form. Epic branches (epic/<parent>-slug) contain a '/', so they are
    # exempt even if the slug ends in '-auto'.
    case "$bare" in
        */*) : ;;                                  # slashed (epic/*) -> not a bare story branch
        *-auto)
            echo "MERGE-GUARD-REFUSE target=$bare reason=stacked-story-branch action=hitl-handoff"
            cat >&2 <<EOF
merge-target-guard: REFUSE — '$bare' is a STORY branch, never a legitimate MR target.
  A story/follow-up MR must target the epic integration branch (epic/*) or main —
  NEVER another story branch. Stacking an MR on a sibling story branch silently
  loses the delivery when that base is later rebased (PILOT-21, v3-pilot #3 !163).
  Retarget the MR to the epic integration branch (or main for a parentless story).
EOF
            return 1
            ;;
    esac

    echo "MERGE-GUARD-ALLOW target=$bare (not protected; ORCH_AUTOMERGE rules apply as normal)"
    return 0
}

case "${1:-}" in
    check) shift; cmd_check "$@" ;;
    -h|--help|help|"") sed -n '2,35p' "$0" ;;
    *) die "unknown subcommand '$1' (check)" ;;
esac
