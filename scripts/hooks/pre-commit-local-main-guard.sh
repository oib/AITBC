#!/bin/bash
# =============================================================================
# pre-commit guard: seats must never commit to the local main (ABS-224)
# =============================================================================
# ABS-224-local-main-guard  <- marker: provision_local_main_guard detects its own
# install by grepping for this token; never remove or rename it.
#
# WHY. Charter prose alone did not hold: in the v2.24.0 watch-run two QAS seats
# committed QA reports straight onto the local `main` of the MAIN checkout
# (dc8449f, cccfbd5). Those commits reached NO story PR and never origin — silent
# work loss, and a poisoned branch base for every future branch off local main.
# This hook is the MECHANICAL backstop: a seat commit landing on the protected
# local main branch is aborted with a pointer to the story branch / worktree.
#
# SCOPE. It fires ONLY for orchestrator seats (a seat-context env marker is
# present) AND only on a protected branch (main/master by default). A human
# committing to their own local main outside a seat carries no marker and is
# never blocked (AC1). Worktree seats commit on `<ticket>-auto` branches, so the
# branch check passes them through untouched.
#
# INSTALL. provision_local_main_guard (scripts/orchestrator.sh) copies this file
# to <git-common-dir>/hooks/pre-commit at startup. Worktrees share that common
# hooks dir, so one install covers the main checkout and every worktree. The
# guard deliberately lives in .git/hooks / spawn-provisioning, NOT in .claude/
# (governor-generated, would be overwritten — scope candidate 1 on the ticket).
#
# KILL SWITCH (ABS-111 pattern). ORCH_PROTECT_LOCAL_MAIN=0 disables the guard.
# The installer also skips/removes the hook when the switch is off, so toggling
# it off at the orchestrator level truly disables enforcement.
#
# Pure + side-effect-free apart from the abort: sourced/invoked directly by
# tests/test-local-main-guard.sh. bash 3.2 + BSD tools only.
# =============================================================================

set -u

# --- ABS-317: chain the harness->provider mirror-drift guard first -----------
# This file IS the installed .git/hooks/pre-commit (one hook per repo). The
# mirror-drift guard is a SEPARATE concern with its own kill switch, so it lives
# in its own script and is chained here rather than copied inline. Resolve it
# from the repo's own scripts/ (the installed hook has no sibling copy). A
# non-zero exit aborts the commit; a missing guard is a silent no-op (fail open).
_mdg_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [ -n "$_mdg_root" ] && [ -f "$_mdg_root/scripts/hooks/pre-commit-mirror-drift-guard.sh" ]; then
    bash "$_mdg_root/scripts/hooks/pre-commit-mirror-drift-guard.sh" || exit $?
fi

# Kill switch: default ON. Off -> allow the commit unconditionally.
if [ "${ORCH_PROTECT_LOCAL_MAIN:-1}" = "0" ]; then
    exit 0
fi

# Seat-context marker. The spawn seam exports ORCH_SEAT; ORCH_TICKET / ORCH_ROLE
# are also present in every seat's environment (belt-and-suspenders). Absent all
# three, this is a human commit -> never guarded.
if [ -z "${ORCH_SEAT:-}${ORCH_TICKET:-}${ORCH_ROLE:-}" ]; then
    exit 0
fi

# Branch being committed to. ORCH_GUARD_BRANCH overrides for tests / detached
# scenarios; otherwise read the current branch from git in the commit's cwd.
branch="${ORCH_GUARD_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}"

# Protected local branches (space-separated). Default: main + master.
protected="${ORCH_PROTECTED_BRANCHES:-main master}"

for p in $protected; do
    if [ "$branch" = "$p" ]; then
        cat >&2 <<EOF
pre-commit BLOCKED (ABS-224): a seat may not commit to the local '$branch'.
  Seat context: ORCH_SEAT='${ORCH_SEAT:-}' ORCH_ROLE='${ORCH_ROLE:-}' ORCH_TICKET='${ORCH_TICKET:-}'
  Commit your work on the STORY branch / worktree instead (e.g. <TICKET>-auto).
  QA/docs artefacts belong on the story branch that carries the work, never on
  the local main — those commits never reach a PR or origin and are lost.
  Override (human/operator only): ORCH_PROTECT_LOCAL_MAIN=0 git commit ...
EOF
        exit 1
    fi
done

exit 0
