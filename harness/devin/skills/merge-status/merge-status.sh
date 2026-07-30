#!/usr/bin/env bash
# merge-status.sh — one-command PR / CI / merge-drift checks for the RTE seat.
#
# WHY (ABS-221): the RTE polling ritual (git fetch -> git log -> bb pr view ->
# read the output -> interpret it) burns the 60-turn ceiling on STATUS
# QUESTIONS. Each subcommand below answers exactly one question in ONE tool
# call and encodes the answer in the EXIT CODE. Branch on $? — never re-read and
# re-parse the human line. The printed line is for the transcript, not for you.
#
# Env knobs (all optional):
#   GIT_HOST_CLI  host PR CLI              (default: bb   — Bitbucket, this repo)
#   ORIGIN        git remote name          (default: origin)
#
# Subcommands and their exit codes (this is the contract — branch on these):
#
#   on-target <commit> [target=main]
#       0  <commit> IS on origin/<target>        (landed / merged)
#       1  <commit> is NOT on origin/<target> yet
#
#   pr-state <id>
#       0  MERGED
#       3  OPEN
#       4  DECLINED / SUPERSEDED / other terminal-not-merged
#
#   pr-ci <id>
#       0  all green   (>=1 successful, 0 failed, 0 pending)
#       1  a check FAILED
#       2  no checks configured for this PR
#       3  checks still PENDING  (do NOT busy-poll — hand off, see SKILL.md)
#
#   drift <branch> <target=main>
#       0  <branch> is up to date with origin/<target>  (0 commits behind)
#       1  <branch> is BEHIND origin/<target>            (rebase needed)
#
# Usage / not-found / CLI errors exit 64.
set -uo pipefail

GIT_HOST_CLI="${GIT_HOST_CLI:-bb}"
ORIGIN="${ORIGIN:-origin}"

die() { echo "merge-status: $*" >&2; exit 64; }

# strip the surrounding quotes bb's embedded jq puts on string scalars
unquote() { tr -d '"'; }

cmd_on_target() {
    local commit="${1:-}" target="${2:-main}"
    [ -n "$commit" ] || die "on-target needs <commit> [target]"
    git fetch -q "$ORIGIN" "$target" || die "cannot fetch $ORIGIN/$target"
    if git merge-base --is-ancestor "$commit" "$ORIGIN/$target" 2>/dev/null; then
        echo "ON-TARGET: $commit is on $ORIGIN/$target"
        return 0
    fi
    echo "NOT-ON-TARGET: $commit is not on $ORIGIN/$target yet"
    return 1
}

cmd_pr_state() {
    local id="${1:-}" state
    [ -n "$id" ] || die "pr-state needs <id>"
    state="$("$GIT_HOST_CLI" pr view "$id" --json --jq '.state' 2>/dev/null | unquote)"
    [ -n "$state" ] || die "cannot read state for PR $id (not found / not authed?)"
    echo "PR $id: $state"
    case "$state" in
        MERGED)   return 0 ;;
        OPEN)     return 3 ;;
        *)        return 4 ;;
    esac
}

cmd_pr_ci() {
    local id="${1:-}" s f p
    [ -n "$id" ] || die "pr-ci needs <id>"
    read -r s f p < <("$GIT_HOST_CLI" pr checks "$id" --json \
        --jq '.summary | "\(.successful) \(.failed) \(.pending)"' 2>/dev/null | unquote)
    [ -n "${s:-}" ] || die "cannot read CI summary for PR $id"
    echo "PR $id CI: successful=$s failed=$f pending=$p"
    [ "$f" -gt 0 ] && return 1
    [ "$p" -gt 0 ] && return 3
    [ "$s" -eq 0 ] && return 2
    return 0
}

cmd_drift() {
    local branch="${1:-}" target="${2:-main}" behind
    [ -n "$branch" ] || die "drift needs <branch> [target]"
    git fetch -q "$ORIGIN" "$target" || die "cannot fetch $ORIGIN/$target"
    behind="$(git rev-list --count "$branch..$ORIGIN/$target" 2>/dev/null)" \
        || die "cannot compute drift ($branch vs $ORIGIN/$target)"
    echo "DRIFT: $branch is $behind commit(s) behind $ORIGIN/$target"
    [ "$behind" -eq 0 ] && return 0
    return 1
}

case "${1:-}" in
    on-target) shift; cmd_on_target "$@" ;;
    pr-state)  shift; cmd_pr_state "$@" ;;
    pr-ci)     shift; cmd_pr_ci "$@" ;;
    drift)     shift; cmd_drift "$@" ;;
    -h|--help|help|"") sed -n '2,45p' "$0" ;;
    *) die "unknown subcommand '$1' (on-target|pr-state|pr-ci|drift)" ;;
esac
