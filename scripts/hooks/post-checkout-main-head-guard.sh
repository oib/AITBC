#!/bin/bash
# =============================================================================
# post-checkout guard: a seat in the MAIN checkout must not leave its HEAD moved
# off the protected branch (PILOT-66 AC3)
# =============================================================================
# PILOT-66-main-head-guard  <- marker: provision_main_head_guard detects its own
# install by grepping for this token; never remove or rename it.
#
# WHY. The single most expensive failure of two pilots was 131 alarmless
# INTENT-SKIP-NOWORKTREE retries. Root cause (git-reflog, to the minute): a seat
# running in the MAIN checkout (by design, a non-worktree seat) ran
# `git checkout -b <work-branch>` there and left that branch checked out for
# hours — after which NO `git worktree add` can check out the same branch, so
# every dependent implementer fail-closed. Charter prose ("seats don't move the
# main HEAD") did not hold; this hook is the MECHANICAL backstop, a sibling of
# the ABS-224 pre-commit local-main guard.
#
# WHAT. git has no pre-checkout hook, so we cannot veto the switch; instead, the
# moment a seat in the main checkout switches HEAD to a NON-protected branch we
# snap HEAD back to the protected branch — but ONLY when that is provably safe
# (clean working tree AND the new branch points at the same commit as the
# protected branch, i.e. the exact `git checkout -b <br>` root-cause). The new
# branch REF is preserved, so a later `git worktree add <br>` succeeds; the main
# checkout is returned to the protected branch, so it never blocks provisioning
# and the pre-commit guard still forbids a stray commit. When the restore is not
# provably safe (dirty tree / diverged branch) we do NOT touch anything — we only
# warn loudly (fail-open); the PILOT-66 count→backoff→escalate path then catches
# the downstream provisioning block with git's own error text.
#
# SCOPE. Fires ONLY for orchestrator seats (a seat-context env marker is present)
# AND only in the MAIN checkout (git-dir == git-common-dir; a linked worktree is
# never touched) AND only on a branch checkout to a non-protected branch. A human,
# or any worktree seat, is never affected.
#
# INSTALL. provision_main_head_guard (scripts/orchestrator.sh) copies this file to
# <git-common-dir>/hooks/post-checkout at startup. HEAD restore via `git checkout`
# is re-entry-guarded (ORCH_HEAD_GUARD_ACTIVE) so the hook never recurses.
#
# KILL SWITCH (ABS-111 pattern). ORCH_PROTECT_LOCAL_MAIN=0 disables the guard (the
# same family switch as the pre-commit local-main guard); the installer also
# skips/removes the hook when the switch is off.
#
# post-checkout args: $1 = prev HEAD sha, $2 = new HEAD sha, $3 = 1 for a branch
# checkout / 0 for a file checkout. bash 3.2 + BSD tools only.
# =============================================================================

set -u

# Re-entry guard: our own restoring `git checkout` fires post-checkout again.
[ "${ORCH_HEAD_GUARD_ACTIVE:-0}" = "1" ] && exit 0

# Kill switch: default ON. Off -> no-op.
[ "${ORCH_PROTECT_LOCAL_MAIN:-1}" = "0" ] && exit 0

# Only branch checkouts (flag=1) matter; a file checkout never moves HEAD.
[ "${3:-0}" = "1" ] || exit 0

# Seat-context marker (same as the pre-commit guard). Absent -> a human/tool
# checkout -> never guarded.
[ -z "${ORCH_SEAT:-}${ORCH_TICKET:-}${ORCH_ROLE:-}" ] && exit 0

command -v git >/dev/null 2>&1 || exit 0

# MAIN checkout only: in a linked worktree git-dir != git-common-dir.
gitdir="$(git rev-parse --absolute-git-dir 2>/dev/null || echo "")"
commondir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null \
    || git rev-parse --git-common-dir 2>/dev/null || echo "")"
[ -n "$gitdir" ] && [ "$gitdir" = "$commondir" ] || exit 0

# Current branch after the checkout. Detached HEAD (symbolic-ref fails) holds no
# branch, so it can never block `git worktree add` -> nothing to guard.
branch="$(git symbolic-ref --short -q HEAD 2>/dev/null || echo "")"
[ -n "$branch" ] || exit 0

# Protected branches the main checkout is allowed to rest on.
protected="${ORCH_PROTECTED_BRANCHES:-main master}"
for p in $protected; do
    [ "$branch" = "$p" ] && exit 0   # on a protected branch -> fine
done

# The branch to restore to: the first protected branch that exists locally.
main=""
for p in ${ORCH_GUARD_MAIN_BRANCH:-} $protected; do
    if git show-ref --verify --quiet "refs/heads/$p" 2>/dev/null; then main="$p"; break; fi
done

cat >&2 <<EOF
post-checkout WARN (PILOT-66): a seat moved the MAIN checkout's HEAD onto '$branch'.
  Seat context: ORCH_SEAT='${ORCH_SEAT:-}' ORCH_ROLE='${ORCH_ROLE:-}' ORCH_TICKET='${ORCH_TICKET:-}'
  A work branch left checked out in the main checkout blocks 'git worktree add'
  for that branch — the root cause of unbounded SKIP-NOWORKTREE retries. Seats
  that need a branch get an isolated worktree; the main checkout stays on '${main:-main}'.
EOF

# Provably-safe restore only: clean tree AND '$branch' at the same commit as the
# protected branch (the fresh `git checkout -b` case). Otherwise leave everything
# untouched (fail-open) — the downstream provisioning guard will surface it.
[ -n "$main" ] || exit 0
[ -z "$(git status --porcelain 2>/dev/null)" ] || exit 0
if [ "$(git rev-parse HEAD 2>/dev/null)" = "$(git rev-parse "$main" 2>/dev/null)" ]; then
    if ORCH_HEAD_GUARD_ACTIVE=1 git checkout -q "$main" 2>/dev/null; then
        echo "post-checkout: restored the main checkout to '$main'; branch '$branch' kept (use a worktree)." >&2
    fi
fi
exit 0
