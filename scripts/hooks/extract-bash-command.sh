#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# extract-bash-command.sh — read a Claude Code PreToolUse payload on stdin and
# print tool_input.command (empty string if absent).
# =============================================================================
# Claude Code PreToolUse matchers match the tool NAME only ("Bash"), never the
# command text. Any hook that must act on a specific command (e.g. "git push")
# therefore matches "Bash" and re-derives the command from stdin via this helper.
# See specs/ABS-12-iteration-guard-spec.md finding #1.
#
# stdout: the command string (may be empty). stderr: nothing. Always exits 0.
# =============================================================================

input="$(cat)"

if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' \
        <<< "$input" 2>/dev/null && exit 0
fi

# ponytail: sed fallback for single-line hook JSON when python3 is absent.
printf '%s' "$input" | sed -n 's/.*"command":"\(.*\)".*/\1/p' | sed 's/\\"/"/g'
