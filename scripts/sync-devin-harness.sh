#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Sync the Devin CLI harness (.devin/) from the Claude Code live harness (.claude/)
# =============================================================================
# This is the Devin equivalent of scripts/sync-claude-harness.sh. It regenerates
# .devin/skills/ and .devin/agents/ from .claude/skills/ and .claude/agents/ by
# converting frontmatter and rewriting harness/.claude/ references to .devin/.
#
# Run after any boilerplate upgrade or after editing .claude skills/agents.
#
# Env overrides (same contract as the Claude sync):
#   ORCH_HARNESS_HOME   harness root; live .claude/ and .devin/ live here
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_HARNESS_HOME="${ORCH_HARNESS_HOME:-$REPO_ROOT}"
cd "$ORCH_HARNESS_HOME"

SKILLS_SRC="${DEVIN_SKILLS_SRC:-.claude/skills}"
AGENTS_SRC="${DEVIN_AGENTS_SRC:-.claude/agents}"

# Fall back to the shipped harness source when .claude/ has not been generated.
[ -d "$SKILLS_SRC" ] || SKILLS_SRC="harness/claude/skills"
[ -d "$AGENTS_SRC" ] || AGENTS_SRC="harness/claude/agents"

[ -d "$SKILLS_SRC" ] || { echo "sync-devin: missing skills source $SKILLS_SRC" >&2; exit 1; }
[ -d "$AGENTS_SRC" ] || { echo "sync-devin: missing agents source $AGENTS_SRC" >&2; exit 1; }

exec python3 "$SCRIPT_DIR/mirror-claude-to-devin.py" \
    --skills-src "$SKILLS_SRC" \
    --agents-src "$AGENTS_SRC" \
    --skills-dst .devin/skills \
    --agents-dst .devin/agents
