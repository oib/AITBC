#!/bin/bash
# =============================================================================
# pre-commit guard: harness edits must carry their provider mirror (ABS-317)
# =============================================================================
# ABS-317-mirror-drift-guard  <- marker: never remove or rename it.
#
# WHY. Editing any harness/claude/agents/*.md or harness/claude/skills/* file
# requires `scripts/generate-governor.sh --providers` to regenerate the
# agent_providers/claude_code/ mirror. Seats keep forgetting, and the drift is
# only caught at the Epic-Integration smoke (generate-governor.sh --providers
# --check, via test-harness-parity). On ABS-223 that cost a git-bisect over 18
# commits and a Done->Ready-for-Development bounce of an already-merged story.
# The check exists; it just runs too late. This hook fires it at COMMIT time.
#
# WHAT. When a commit stages any harness/claude/{agents,skills}/** path:
#   (a) the provider mirror on disk must equal generated(harness) — i.e.
#       `generate-governor.sh --providers --check` passes; and
#   (b) there must be NO unstaged/uncommitted change left under
#       agent_providers/claude_code/ (regen output that was never `git add`ed).
# Either miss aborts the commit with the exact one-line fix.
#
# SCOPE. Fires for ANY committer (seat or human) — the mirror discipline is
# universal. Kill switch: ORCH_MIRROR_GUARD=0.
#
# Pure + side-effect-free apart from the abort: invoked directly by
# tests/test-mirror-drift-guard.sh. bash 3.2 + BSD tools only.
# =============================================================================

set -u

# Kill switch: default ON. Off -> allow the commit unconditionally.
if [ "${ORCH_MIRROR_GUARD:-1}" = "0" ]; then
    exit 0
fi

command -v git >/dev/null 2>&1 || exit 0

root="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[ -n "$root" ] || exit 0

# ORCH_MIRROR_GUARD_STAGED lets the test drive the "staged harness paths" set
# without a real index. In normal use it is unset and we read the staged tree.
staged="${ORCH_MIRROR_GUARD_STAGED:-$(git -C "$root" diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)}"

# Any harness agents/skills path staged? (Nothing to check otherwise.)
harness_hit="$(printf '%s\n' "$staged" | grep -E '^harness/claude/(agents|skills)/' || true)"
[ -n "$harness_hit" ] || exit 0

gen="$root/scripts/generate-governor.sh"
if [ ! -x "$gen" ] && [ ! -f "$gen" ]; then
    # Cannot verify — fail OPEN (never block on a missing tool), but say so.
    echo "mirror-drift guard: scripts/generate-governor.sh missing; skipping parity check" >&2
    exit 0
fi

fail() {
    cat >&2 <<EOF
pre-commit BLOCKED (ABS-317): harness edit without its provider mirror.
  Staged harness file(s):
$(printf '%s\n' "$harness_hit" | sed 's/^/    /')
  $1
  Fix (run, then re-stage, then commit):
    bash scripts/generate-governor.sh --providers && git add agent_providers/claude_code
  Override (human/operator only): ORCH_MIRROR_GUARD=0 git commit ...
EOF
    exit 1
}

# (a) disk mirror parity with the harness source.
if ! bash "$gen" --providers --check >/dev/null 2>&1; then
    fail "The agent_providers/claude_code/ mirror has DRIFTED from harness/claude/."
fi

# (b) no regenerated-but-unstaged mirror change left behind.
if ! git -C "$root" diff --quiet -- agent_providers/claude_code 2>/dev/null; then
    fail "The provider mirror has UNSTAGED changes — the regen output was not 'git add'ed."
fi

exit 0
