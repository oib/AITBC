#!/bin/bash
# =============================================================================
# Pre-Bash Hook: shared-stash guard (ABS-272)
# =============================================================================
# ABS-272-stash-guard  <- marker: keep this token; docs/tests grep for it.
#
# WHY. `git stash` writes to ONE `refs/stash` that ALL worktrees of a repo SHARE
# (only HEAD, refs/bisect, refs/worktree and refs/rewritten are per-worktree).
# The runner deliberately operates seats CONCURRENTLY in their own worktrees
# (tmp/<TICKET>-work/). A seat that stashes its work for a baseline comparison and
# then runs `git stash pop` therefore pops whatever landed on top of the SHARED
# stack — which may be a sibling seat's stash — and silently eats that seat's
# uncommitted work. Three incidents in one run window (2026-07-13): ABS-251 popped
# ABS-255's stash; ABS-254 popped ABS-265's stash; an older recovery entry was
# already on the stack. They only survived because the seats NOTICED and repaired
# by hand.
#
# The seats improvised `git stash` because the harness DEMANDS a baseline
# comparison but shipped no safe recipe for it. The recipe now lives in the common
# seat rules (harness/claude/agents/_common-rules.md, "Baseline-Vergleich ohne
# Stash"); this hook is the mechanical backstop that keeps the practice from
# re-emerging.
#
# WHAT IT DOES. A Claude Code PreToolUse hook on the Bash tool. It reads the
# command from the stdin JSON payload (.tool_input.command) and BLOCKS (exit 2,
# stderr fed back to the model) any MUTATING git-stash invocation:
#   git stash · git stash push/save · git stash pop/apply/drop/clear/branch/store
# READ-ONLY stash inspection stays allowed (it never writes refs/stash):
#   git stash list · git stash show
# Git global flags between `git` and `stash` (-C <dir>, -c k=v, --git-dir=…,
# --work-tree=…, -P/--no-pager) are normalized away first, so `git -C <wt> stash
# pop` is caught too — the exact form a seat reaches for from another directory.
#
# SCOPE. Fires ONLY for orchestrator SEATS — the spawn seam exports the
# ORCH_SEAT / ORCH_TICKET / ORCH_ROLE markers (orchestrator-spawn-claude.sh).
# A human's own interactive shell carries none of them and is NEVER guarded (same
# principle as the ABS-224 local-main guard and the ABS-243 kill guard): the
# operator keeps full authority over their own repo, including the stash.
#
# KILL SWITCH (ABS-111 pattern). ORCH_STASH_GUARD default ON (=1). Set
# ORCH_STASH_GUARD=0 to restore the legacy unguarded behavior.
#
# OBSERVABILITY (ABS-66). Every blocked stash is appended to the guard log
# (ORCH_STASH_GUARD_LOG, default $TMPDIR/orchestrator-stash-guard.log) with a UTC
# timestamp, the seat identity, the matched form, and the offending command — and
# echoed to stderr for the seat, together with the allowed recipe.
#
# FAIL-OPEN. Missing jq, empty command, or a non-seat context -> exit 0 (allow),
# so the guard can never wedge a legitimate command flow.
#
# bash 3.2 + BSD tools only.
# =============================================================================

set -u

# --- Kill switch (ABS-111): default ON. Off -> allow unconditionally. --------
if [ "${ORCH_STASH_GUARD:-1}" = "0" ]; then
    exit 0
fi

payload=$(cat)

command -v jq >/dev/null 2>&1 || { echo 'hooks: jq not found; skipping stash-guard' >&2; exit 0; }

cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

# --- Seat context only. A human shell carries no seat marker -> never guarded.
if [ -z "${ORCH_SEAT:-}${ORCH_TICKET:-}${ORCH_ROLE:-}" ]; then
    exit 0
fi

# Normalize git's GLOBAL flags away so `git -C <dir> stash pop` reduces to
# `git stash pop`. Without this the guard would miss the cross-directory form —
# the one a seat reaches for when it stashes from outside its own worktree.
norm=$(printf '%s' "$cmd" | tr '\n' ' ' | sed -E \
    's/(^|[^[:alnum:]_.-])git(([[:space:]]+(-C|-c)[[:space:]]*[^[:space:]]+)|([[:space:]]+(--git-dir|--work-tree|--namespace)=[^[:space:]]+)|([[:space:]]+(-P|--no-pager|--no-replace-objects)))+/\1git/g')

# Decide PER `git stash …` occurrence, on that occurrence's OWN subcommand — a
# read-only `git stash list` elsewhere on the line must never launder a `pop`.
matched=""
while IFS= read -r occurrence; do
    [ -n "$occurrence" ] || continue
    sub=$(printf '%s' "$occurrence" \
        | sed -E 's/.*git[[:space:]]+stash[[:space:]]*//' \
        | awk '{print $1}')
    case "$sub" in
        list|show) continue ;;              # read-only: never writes refs/stash
        "")        matched="git stash" ;;   # bare `git stash` = implicit push
        *)         matched="git stash $sub" ;;
    esac
    break
done <<EOF
$(printf '%s' "$norm" | grep -oE '(^|[^[:alnum:]_.-])git[[:space:]]+stash([[:space:]]+[^[:space:];|&()]+)?')
EOF

[ -n "$matched" ] || exit 0

# --- Blocked. Log (observability) then refuse (exit 2). ----------------------
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u)
log="${ORCH_STASH_GUARD_LOG:-${TMPDIR:-/tmp}/orchestrator-stash-guard.log}"
# ABS-294 NB2 (same form as the kill-guard): flatten newlines so a crafted
# command cannot inject fabricated lines into the audit log.
cmd_log=$(printf '%s' "$cmd" | tr '\n\r' '  ')
printf '%s BLOCKED seat=%s role=%s ticket=%s matched=%s cmd=%s\n' \
    "$ts" "${ORCH_SEAT:-}" "${ORCH_ROLE:-}" "${ORCH_TICKET:-}" "$matched" "$cmd_log" \
    >>"$log" 2>/dev/null || true

cat >&2 <<EOF
❌ BLOCKED (ABS-272 stash-guard): git stash refused in a seat worktree.
  Matched:  $matched
  Reason:   refs/stash is ONE stack SHARED by ALL worktrees of this repo. Sibling
            seats run concurrently in their own worktrees, so your \`git stash pop\`
            can pop THEIR stash and silently eat their uncommitted work (3 incidents
            on 2026-07-13: ABS-251←ABS-255, ABS-254←ABS-265).
  Command:  $cmd

  For a BASELINE comparison use a throwaway worktree on the base commit — it needs
  no stash at all, and your working tree is never touched:

    base=\$(git merge-base HEAD origin/<your-main-branch>)   # e.g. origin/main
    wt=\$(mktemp -d)/base
    git worktree add --detach "\$wt" "\$base"
    ( cd "\$wt" && <run the suite here> )     # baseline result
    git worktree remove --force "\$wt"

  To park work in progress, COMMIT it on your story branch (you own your commits)
  instead of stashing. Read-only \`git stash list\` / \`git stash show\` stay allowed.
  Override (operator only): ORCH_STASH_GUARD=0
  Logged to: $log
EOF
exit 2
