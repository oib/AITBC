#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Sync the Devin CLI harness (.devin/) from the shipped Devin harness (harness/devin/)
# =============================================================================
# This is the Devin equivalent of scripts/sync-claude-harness.sh. It regenerates
# .devin/skills/ and .devin/agents/ from the Devin-format harness source.
#
# Run after any boilerplate upgrade or after editing harness/devin/ skills/agents.
#
# Env overrides (same contract as the Claude sync):
#   ORCH_HARNESS_HOME   harness root
#   DEVIN_SKILLS_SRC    override skills source dir
#   DEVIN_AGENTS_SRC    override agents source dir
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_HARNESS_HOME="${ORCH_HARNESS_HOME:-$REPO_ROOT}"
cd "$ORCH_HARNESS_HOME"

SKILLS_SRC="${DEVIN_SKILLS_SRC:-harness/devin/skills}"
AGENTS_SRC="${DEVIN_AGENTS_SRC:-harness/devin/agents}"

# Fall back to the shipped Claude harness source and convert it when no Devin
# harness has been published for this boilerplate version.
[ -d "$SKILLS_SRC" ] || SKILLS_SRC="harness/claude/skills"
[ -d "$AGENTS_SRC" ] || AGENTS_SRC="harness/claude/agents"

# Finally, fall back to a live .claude/ tree if it has already been generated.
[ -d "$SKILLS_SRC" ] || SKILLS_SRC=".claude/skills"
[ -d "$AGENTS_SRC" ] || AGENTS_SRC=".claude/agents"

[ -d "$SKILLS_SRC" ] || { echo "sync-devin: missing skills source $SKILLS_SRC" >&2; exit 1; }
[ -d "$AGENTS_SRC" ] || { echo "sync-devin: missing agents source $AGENTS_SRC" >&2; exit 1; }

# Detect whether each source is already Devin-format (use passthrough) or
# Claude-format (use conversion). The decision is made independently for
# skills and agents to handle mixed-format scenarios.
#
# A source is considered Devin-format if:
#   - Its path contains harness/devin or .devin, OR
#   - Any SKILL.md / agent .md in it has 'triggers:' frontmatter (Devin-specific)
_detect_devin_format() {
    local src_dir="$1"
    local marker="$2"  # SKILL.md for skills, *.md for agents
    if echo "$src_dir" | grep -q "harness/devin\|\.devin"; then
        echo "--passthrough"
        return
    fi
    if grep -rl '^triggers:' "$src_dir" --include="$marker" >/dev/null 2>&1; then
        echo "--passthrough"
        return
    fi
    echo ""
}

SKILLS_PT="$(_detect_devin_format "$SKILLS_SRC" "SKILL.md")"
AGENTS_PT="$(_detect_devin_format "$AGENTS_SRC" "*.md")"

# In practice both sources are always the same format. If they disagree, warn
# and use the skills detection (the more common case).
if [ "$SKILLS_PT" != "$AGENTS_PT" ]; then
    echo "sync-devin: WARNING — skills and agents sources have different formats; using skills detection" >&2
fi

exec python3 "$SCRIPT_DIR/mirror-claude-to-devin.py" \
    $SKILLS_PT \
    --skills-src "$SKILLS_SRC" \
    --agents-src "$AGENTS_SRC" \
    --skills-dst .devin/skills \
    --agents-dst .devin/agents
