#!/bin/bash
# Check that provider skills directories stay synchronized
#
# Skills are stored in three provider directories:
# - harness/claude/skills/ is the canonical SOURCE (ABS-97: shipped-harness
#   namespace; may include provider-specific docs). The live .claude/skills/
#   is a byte-identical copy of this (verified by tests/test-harness-parity.sh)
#   until Phase 2b generates it — either points at the same canonical content.
# - .agents/skills/ must have all canonical skills (SKILL.md only)
# - .gemini/skills/ must have all canonical skills (SKILL.md + README.md)
#
# Skills intentionally provider-specific (not requiring propagation):
ALLOWLIST=""

# Get canonical skill list from harness/claude/skills/ (exclude README.md)
CLAUDE_SKILLS=$(ls -1d harness/claude/skills/*/ 2>/dev/null | xargs -n1 basename | sort)
AGENTS_SKILLS=$(ls -1d .agents/skills/*/ 2>/dev/null | xargs -n1 basename | sort)
GEMINI_SKILLS=$(ls -1d .gemini/skills/*/ 2>/dev/null | xargs -n1 basename | sort)

MISSING_FROM_AGENTS=""
MISSING_FROM_GEMINI=""

# Check .agents/skills/ has all canonical skills (using -x for exact match)
for skill in $CLAUDE_SKILLS; do
  if [ -n "$ALLOWLIST" ] && echo "$ALLOWLIST" | grep -x "$skill" >/dev/null; then
    continue
  fi
  if ! echo "$AGENTS_SKILLS" | grep -x "$skill" >/dev/null; then
    MISSING_FROM_AGENTS="$MISSING_FROM_AGENTS $skill"
  fi
done

# Check .gemini/skills/ has all canonical skills (using -x for exact match)
for skill in $CLAUDE_SKILLS; do
  if [ -n "$ALLOWLIST" ] && echo "$ALLOWLIST" | grep -x "$skill" >/dev/null; then
    continue
  fi
  if ! echo "$GEMINI_SKILLS" | grep -x "$skill" >/dev/null; then
    MISSING_FROM_GEMINI="$MISSING_FROM_GEMINI $skill"
  fi
done

# Report results
if [ -n "$MISSING_FROM_AGENTS" ] || [ -n "$MISSING_FROM_GEMINI" ]; then
  if [ -n "$MISSING_FROM_AGENTS" ]; then
    echo "ERROR: Missing from .agents/skills/:$MISSING_FROM_AGENTS" >&2
  fi
  if [ -n "$MISSING_FROM_GEMINI" ]; then
    echo "ERROR: Missing from .gemini/skills/:$MISSING_FROM_GEMINI" >&2
  fi
  echo "" >&2
  echo "Provider skills parity check failed." >&2
  exit 1
fi

echo "✅ Provider skills are in sync (harness/claude/ → .agents/, .gemini/)"
echo "  • harness/claude/skills: $(echo "$CLAUDE_SKILLS" | wc -w) skills"
echo "  • .agents/skills: $(echo "$AGENTS_SKILLS" | wc -w) skills"
echo "  • .gemini/skills: $(echo "$GEMINI_SKILLS" | wc -w) skills"
