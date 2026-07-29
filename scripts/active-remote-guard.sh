#!/usr/bin/env bash
# active-remote-guard.sh — mechanical guard: a seat's push / MR-open follows the
# ACTIVE-REMOTE PIN, never the "origin" convention (PILOT-25, twin ABS-539).
#
# WHY. Remote doctrine (Operator, 2026-07-23): GitLab (gitlab.haemosan.at) is the
# permanent LIVE remote for the MR-flow, story branches and the runner. Bitbucket
# (`origin`) is a RELEASE MIRROR only — it receives finished versions (main + tag)
# at release time, nothing else. Two reachable remotes without a pin are a silent
# divergence source: in v3-pilot #3 an RTE seat resolved the push remote to `origin`
# by convention, pushed the recovery branch to Bitbucket and opened PR #236 there —
# GitLab got nothing, and the Operator had to move branch + MR (!165) by hand. This
# guard turns "push/MR host ALWAYS follows the active-remote pin, never origin"
# (rte.md / safe-workflow) from prose into a MECHANICAL check a seat runs before a
# push or MR-open: target remote != the pin -> refuse.
#
# The pin is $ORCH_MAIN_REMOTE (same knob orchestrator.sh already reads to resolve
# the active main ref, ABS-493). Unset pin = legacy single-remote repo -> the guard
# is inert (ALLOW), so a fork with one `origin` is unchanged.
#
# Env:
#   ORCH_MAIN_REMOTE   the pinned ACTIVE remote name (e.g. "gitlab"). Unset/empty =
#                      no pin in force -> guard is inert (every target ALLOWED).
#
# Subcommands and their exit codes (this is the contract — branch on these):
#
#   check <target-remote>
#       0  ALLOW   — no pin in force, OR target IS the pinned active remote.
#       1  REFUSE  — a pin is set and target is a DIFFERENT remote (e.g. `origin`
#                    while pin=gitlab). The seat must NOT push/open there; retarget
#                    the active remote. A machine-greppable intent line
#                    (`ACTIVE-REMOTE-GUARD-REFUSE ...`) is printed to stdout.
#
# Usage / bad input exit 64.
#
# Pure + side-effect-free apart from the printed lines: invoked directly by
# tests/test-remote-doctrine.sh. bash 3.2 + BSD tools only.
set -uo pipefail

die() { echo "active-remote-guard: $*" >&2; exit 64; }

# Normalise a target to a bare remote NAME: a plain remote ("origin") passes
# through; a "remote/branch" ref ("origin/main") is reduced to its remote
# ("origin") so `check origin/main` resolves to the remote `origin`.
_remote_name() {
    local t="$1"
    case "$t" in
        */*) printf '%s' "${t%%/*}" ;;   # origin/main -> origin
        *)   printf '%s' "$t" ;;
    esac
}

cmd_check() {
    local target="${1:-}"
    [ -n "$target" ] || die "check needs <target-remote>"
    local pin remote
    pin="${ORCH_MAIN_REMOTE:-}"
    remote="$(_remote_name "$target")"

    # No pin in force -> single-remote / legacy repo. Guard is inert.
    if [ -z "$pin" ]; then
        echo "ACTIVE-REMOTE-GUARD-ALLOW target=$remote pin=<unset> (no pin in force; legacy single-remote)"
        return 0
    fi

    if [ "$remote" = "$pin" ]; then
        echo "ACTIVE-REMOTE-GUARD-ALLOW target=$remote pin=$pin (target IS the active remote)"
        return 0
    fi

    # Machine-greppable intent line — the transcript is the intent log.
    echo "ACTIVE-REMOTE-GUARD-REFUSE target=$remote pin=$pin action=retarget-active-remote"
    cat >&2 <<EOF
active-remote-guard: REFUSE — push/MR target '$remote' is NOT the pinned active remote '$pin'.
  Remote doctrine (PILOT-25): the LIVE remote is '$pin' (GitLab); '$remote' (Bitbucket
  'origin') is a RELEASE MIRROR that only ever receives 'main' + the release tag at
  release time (scripts/release-mirror-push.sh). Retarget your push / MR-open at '$pin'
  (e.g. \`git push $pin ...\`, open the MR on the '$pin' host). Do NOT push/open on '$remote'.
EOF
    return 1
}

case "${1:-}" in
    check) shift; cmd_check "$@" ;;
    -h|--help|help|"") sed -n '2,40p' "$0" ;;
    *) die "unknown subcommand '$1' (check)" ;;
esac
