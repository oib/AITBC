#!/bin/bash
# =============================================================================
# commit-msg guard: a SEAT commit on a STORY branch must carry its ticket tag
# (PILOT-79)
# =============================================================================
# PILOT-79-ticket-tag-guard  <- marker: provision_ticket_tag_guard detects its own
# install by grepping for this token; never remove or rename it.
#
# WHY. The `[PREFIX-XXX]` tag is what the RTE Epic-Integration bisect maps a
# culprit commit to its story with (rte.md step 6). An untagged story commit that
# reaches the epic branch can crash the whole epic into `Needs PO Decision` — a
# status with no edge back to the merge path. CONTRIBUTING.md declared the tag
# REQUIRED, but nothing enforced it. This is the MECHANICAL backstop, a sibling of
# the ABS-224 pre-commit local-main guard and the PILOT-66 post-checkout guard.
#
# WHERE IT RUNS (PILOT-79 AC3). commit-msg fires at COMMIT time on the story branch
# — strictly BEFORE the story is merged into the epic branch (the bisect area),
# not only on main. The commit-msg hook (not pre-commit) is used because only it
# receives the commit MESSAGE (as $1), and the tag lives in the message.
#
# SCOPE. Fires ONLY for orchestrator seats (a seat-context env marker is present)
# AND only on a STORY branch. Protected branches (main/master) and epic/* branches
# are the operator's/RTE's territory — release & integration commits live there and
# are never guarded. A human committing outside a seat carries no marker and is
# never blocked. The exempt class (release automation / [no-ticket] marker) is
# honoured by the shared classifier in scripts/commit-tag-guard.sh.
#
# KILL SWITCH (ABS-111 pattern). ORCH_TICKET_TAG_GUARD=0 disables the guard; the
# installer also skips/removes the hook when the switch is off.
#
# INSTALL. provision_ticket_tag_guard (scripts/orchestrator.sh) copies this file to
# <git-common-dir>/hooks/commit-msg at startup (a fresh hook slot).
#
# commit-msg arg: $1 = path to the commit message file. bash 3.2 + BSD tools only.
# =============================================================================
set -u

# Kill switch: default ON. Off -> allow the commit unconditionally.
[ "${ORCH_TICKET_TAG_GUARD:-1}" = "0" ] && exit 0

# Seat-context marker (same family as the local-main / main-head guards). Absent
# all three -> a human commit -> never guarded.
[ -z "${ORCH_SEAT:-}${ORCH_TICKET:-}${ORCH_ROLE:-}" ] && exit 0

command -v git >/dev/null 2>&1 || exit 0

# Branch being committed to. ORCH_GUARD_BRANCH overrides for tests / detached HEAD.
branch="${ORCH_GUARD_BRANCH:-$(git symbolic-ref --short -q HEAD 2>/dev/null || echo "")}"

# Never guard the operator's/RTE's territory: protected branches carry release
# commits, epic/* carries integration commits — both legitimately untagged.
protected="${ORCH_PROTECTED_BRANCHES:-main master}"
for p in $protected; do
    [ "$branch" = "$p" ] && exit 0
done
case "$branch" in
    epic/*) exit 0 ;;
esac

# Delegate the tagged/exempt/untagged decision to the shared classifier. Resolve it
# from the repo's own scripts/ (the installed hook has no sibling copy).
root="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
guard="$root/scripts/commit-tag-guard.sh"
[ -f "$guard" ] || exit 0   # fail open: no classifier -> never block a commit.

if bash "$guard" check-msg "$1" >/dev/null 2>&1; then
    exit 0   # tagged or exempt -> allow.
fi

cat >&2 <<EOF
❌ commit-msg BLOCKED (PILOT-79 ticket-tag guard): commit on story branch '$branch'
   is missing its ticket tag.

   Required format:  type(scope): description [PREFIX-XXX]
   e.g.              feat(api): add subscription webhook [${ORCH_TICKET:-PILOT-79}]

   WHY: the RTE Epic-Integration bisect maps a culprit commit to its story via the
   [PREFIX-XXX] tag. An untagged commit that reaches the epic branch can crash the
   epic into 'Needs PO Decision' (a dead-end status). Amend the message to add the
   tag:  git commit --amend

   Legitimately ticketless (operator/release) commits are exempt — begin the subject
   with 'chore(release):' or add a '[no-ticket]' marker (see CONTRIBUTING.md
   "Exempt commits"). Override (operator only): ORCH_TICKET_TAG_GUARD=0
EOF
exit 1
