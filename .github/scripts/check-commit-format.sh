#!/usr/bin/env bash
# Validate SAFe commit-message format over a git range.
#
# ABS-143: replaces the never-matching literal `AITBC` regex that
# lived in .github/workflows/pr-validation.yml (which meant `[ABS-126]` was
# NEVER accepted — only the literal string `[AITBC-1]` matched).
# This uses the REAL `ABS` prefix and is the enforcing gate wired into
# bitbucket-pipelines.yml.
#
# Usage:
#   check-commit-format.sh <git-range>     # every commit in the range (PR gate)
#   check-commit-format.sh <single-ref>    # just that one commit (main push)
# Examples:
#   check-commit-format.sh "origin/main..HEAD"   # all commits a PR adds
#   check-commit-format.sh HEAD                   # only the just-landed commit
#
# The range form is the PR enforcement point (every commit a PR introduces is
# validated before merge). The single-ref form is used on a main push, where
# the commit is already merged and only the landed tip is re-checked — a merge
# commit tip is exempt, so main never reddens on historical/merge commits.
#
# A commit passes if its subject is either:
#   - conventional-commit + ticket ref:  type(scope): description [ABS-123]
#   - a merge / generated commit:        Merge… | Merged in… | 🤖 Generated…
# Exits non-zero if any commit in the range violates the format.

set -euo pipefail

RANGE="${1:?usage: check-commit-format.sh <git-range|single-ref>}"

# A "range" contains "..". Anything else is a single ref: check only that commit.
case "$RANGE" in
  *..*) GIT_LOG_ARGS=("$RANGE") ;;
  *)    GIT_LOG_ARGS=(-1 "$RANGE") ;;
esac

# type(scope): description [ABS-123]   (scope optional)
FORMAT_RE='^(feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert)(\(.+\))?: .+ \[ABS-[0-9]+\]$'
# Merge commits and tool-generated commits are exempt.
EXEMPT_RE='^(Merge|Merged in|🤖 Generated)'

BAD=0
echo "Checking commit messages in range: $RANGE"

OLDIFS="$IFS"
IFS='
'
for msg in $(git log --format='%s' "${GIT_LOG_ARGS[@]}"); do
  [ -z "$msg" ] && continue
  if echo "$msg" | grep -qE "$EXEMPT_RE"; then
    echo "  • (exempt) $msg"
  elif echo "$msg" | grep -qE "$FORMAT_RE"; then
    echo "  ✓ $msg"
  else
    echo "  ✗ $msg"
    BAD=1
  fi
done
IFS="$OLDIFS"

if [ "$BAD" -ne 0 ]; then
  echo "" >&2
  echo "ERROR: one or more commits do not follow SAFe format." >&2
  echo "Expected: type(scope): description [ABS-XXX]" >&2
  exit 1
fi

echo "✅ All commit messages follow SAFe format"
