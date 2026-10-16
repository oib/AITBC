#!/bin/bash
# Bandit gate — same scan the pre-push hook runs (bandit -c pyproject.toml -r .
# --severity-level medium), asserted twice:
#
#   1. exit status: 0 means no medium-or-higher findings;
#   2. zero WARNING lines on stderr: [manager] "Test in comment: X is not a
#      test name" fires when a `# nosec` comment carries prose after the test
#      id (keep `# nosec Bxxx` alone and move the rationale to a comment of its
#      own), and [tester] "nosec encountered ... but no failed test" fires when
#      a named-code suppression does not cover every node on its line — drop
#      the marker when nothing needs suppressing, or use a bare `# nosec` when
#      it does.
#
# Bandit writes these diagnostics to stderr while still exiting 0, so the
# hook's exit code alone lets thousands of warnings accumulate unseen.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
PYTHON="$("$(dirname "${BASH_SOURCE[0]}")/repo-python.sh")" || exit 1

if ! "$PYTHON" -c 'import bandit' >/dev/null 2>&1; then
    echo "bandit is not installed for '$PYTHON'. It checked nothing; this is not a pass."
    exit 1
fi

warnings="$(mktemp)"
findings="$(mktemp)"
trap 'rm -f "$warnings" "$findings"' EXIT

set +e
"$PYTHON" -m bandit -c pyproject.toml -r . --severity-level medium -q -f txt \
    >"$findings" 2>"$warnings"
status=$?
set -e

fail=0
if [ "$status" -ne 0 ]; then
    echo "bandit: medium-or-higher findings present (exit $status)"
    grep "Location:" "$findings" | head -20
    fail=1
fi
if grep -q "WARNING" "$warnings"; then
    echo "bandit: $(grep -c WARNING "$warnings") warning(s) — malformed or dead nosec comments"
    grep "WARNING" "$warnings" | sort -u | head -20
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "bandit: no medium+ findings, no warnings"
fi
exit "$fail"
