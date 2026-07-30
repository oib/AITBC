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

# Determine if the source is already Devin-format (harness/devin) or
# Claude-format (harness/claude / .claude). Devin-format sources use
# passthrough mode to avoid lossy double-conversion.
PASSTHROUGH=""
if [ -f "$SKILLS_SRC" ] || echo "$SKILLS_SRC" | grep -q "harness/devin\|\.devin"; then
    PASSTHROUGH="--passthrough"
elif [ -d "$SKILLS_SRC" ]; then
    # Heuristic: if any SKILL.md in the source has 'triggers:' it's already Devin-format.
    if grep -rl '^triggers:' "$SKILLS_SRC" >/dev/null 2>&1; then
        PASSTHROUGH="--passthrough"
    fi
fi

exec python3 "$SCRIPT_DIR/mirror-claude-to-devin.py" \
    $PASSTHROUGH \
    --skills-src "$SKILLS_SRC" \
    --agents-src "$AGENTS_SRC" \
    --skills-dst .devin/skills \
    --agents-dst .devin/agents
