#!/usr/bin/env bash
# =============================================================================
# Devin harness drift guard — mirror parity for harness/devin/ and .devin/
# =============================================================================
# Mirrors the source to a temp tree and compares the real destination, the same
# pattern used by scripts/generate-governor.sh --providers --check.
#
#   harness/claude/ -> harness/devin/  (shipped Devin-format boilerplate)
#   harness/devin/  -> .devin/         (live Devin CLI consumer copy, passthrough)
#
# S3: Also guards the live .claude/ consumer against harness/claude/ so edits
# made directly under .claude/ without backporting to harness/claude/ are
# caught.
#
# S4: Also guards commands/, hooks/, and top-level harness files (README.md,
# TROUBLESHOOTING.md, SETUP.md, AGENT_OUTPUT_GUIDE.md, hooks-config.json,
# settings.template.json) — not just skills/ and agents/.
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

# --- S3+S4: Guard .claude/ against harness/claude/ (all subdirs + top files) -
echo "Checking .claude/ == harness/claude/ (consumer vs shipped source) ..."
for subdir in skills agents commands hooks; do
    if [ -d "$REPO_ROOT/harness/claude/$subdir" ] && [ -d "$REPO_ROOT/.claude/$subdir" ]; then
        if ! diff -rq "$REPO_ROOT/harness/claude/$subdir" "$REPO_ROOT/.claude/$subdir" >/dev/null 2>&1; then
            echo "  DRIFT: .claude/$subdir differs from harness/claude/$subdir" >&2
            rc=1
        fi
    elif [ -d "$REPO_ROOT/harness/claude/$subdir" ] && [ ! -d "$REPO_ROOT/.claude/$subdir" ]; then
        echo "  DRIFT: .claude/$subdir missing (harness/claude/$subdir exists)" >&2
        rc=1
    fi
done

# Top-level files that should be mirrored from harness/claude/ to .claude/
for topfile in README.md TROUBLESHOOTING.md SETUP.md AGENT_OUTPUT_GUIDE.md hooks-config.json settings.template.json; do
    if [ -f "$REPO_ROOT/harness/claude/$topfile" ]; then
        if [ ! -f "$REPO_ROOT/.claude/$topfile" ]; then
            echo "  DRIFT: .claude/$topfile missing (harness/claude/$topfile exists)" >&2
            rc=1
        elif ! diff -q "$REPO_ROOT/harness/claude/$topfile" "$REPO_ROOT/.claude/$topfile" >/dev/null 2>&1; then
            echo "  DRIFT: .claude/$topfile differs from harness/claude/$topfile" >&2
            rc=1
        fi
    fi
done

if [ "$rc" -eq 0 ]; then
    echo "  .claude/ matches harness/claude/ for skills, agents, commands, hooks, and top-level files."
fi

# --- Leg 1: harness/claude/ -> harness/devin/ (conversion) ------------------
echo "Checking harness/devin/ == generated(harness/claude/) ..."
if ! python3 "$MIRROR" \
    --check \
    --skills-src harness/claude/skills \
    --agents-src harness/claude/agents \
    --skills-dst harness/devin/skills \
    --agents-dst harness/devin/agents; then
    rc=1
fi

# --- Leg 2: harness/devin/ -> .devin/ (passthrough, no re-conversion) -------
echo "Checking .devin/ == passthrough(harness/devin/) ..."
if ! python3 "$MIRROR" \
    --check \
    --passthrough \
    --skills-src harness/devin/skills \
    --agents-src harness/devin/agents \
    --skills-dst .devin/skills \
    --agents-dst .devin/agents; then
    rc=1
fi

# --- S2: Semantic lint (YAML validity, tool/model validity, preservation) --
echo "Running semantic lint on harness/devin/ and .devin/ ..."
if ! python3 "$MIRROR" --lint; then
    rc=1
fi

exit "$rc"
