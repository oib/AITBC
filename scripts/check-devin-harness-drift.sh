#!/usr/bin/env bash
# =============================================================================
# Devin harness drift guard — mirror parity for harness/devin/ and .devin/
# =============================================================================
# Mirrors the source to a temp tree and compares the real destination, the same
# pattern used by scripts/generate-governor.sh --providers --check.
#
#   harness/claude/ -> harness/devin/  (shipped Devin-format boilerplate)
#   harness/devin/  -> .devin/         (live Devin CLI consumer copy)
#
# The .devin/ consumer may carry project-specific skills/agents on top of the
# boilerplate; only missing or differing generated files are treated as drift.
#
# Usage: bash scripts/check-devin-harness-drift.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MIRROR="$REPO_ROOT/scripts/mirror-claude-to-devin.py"

rc=0

echo "Checking harness/devin/ == generated(harness/claude/) ..."
if ! python3 "$MIRROR" \
    --check \
    --skills-src harness/claude/skills \
    --agents-src harness/claude/agents \
    --skills-dst harness/devin/skills \
    --agents-dst harness/devin/agents; then
    rc=1
fi

echo "Checking .devin/ == generated(harness/devin/) ..."
if ! python3 "$MIRROR" \
    --check \
    --skills-src harness/devin/skills \
    --agents-src harness/devin/agents \
    --skills-dst .devin/skills \
    --agents-dst .devin/agents; then
    rc=1
fi

exit "$rc"
