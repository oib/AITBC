#!/bin/bash
# C901 complexity ratchet — the same "baseline + gate the delta" mechanism as
# scripts/ci/mypy-baseline.txt, applied to cyclomatic complexity.
#
# C901 is not in ruff's select list (and is globally ignored), so `ruff check .`
# never reports it. This script is the real gate: it fails if any file gains a
# *new* C901 violation relative to scripts/ci/c901-baseline.txt — i.e. complexity
# cannot grow, only shrink. When a refactor reduces a file below its baseline
# count, regenerate the baseline:
#
#   scripts/ci/check-c901-ratchet.sh --update
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
BASELINE="scripts/ci/c901-baseline.txt"
PYTHON="${PYTHON:-python3}"

current="$(mktemp)"
trap 'rm -f "$current"' EXIT
{ "$PYTHON" -m ruff check . --select C901 --output-format concise 2>/dev/null || true; } \
    | grep -E ':[0-9]+:[0-9]+: C901 ' | cut -d: -f1 | sort | uniq -c > "$current"

if [ "${1:-}" = "--update" ]; then
    sort -k2 "$current" > "$BASELINE"
    echo "c901 baseline updated: $(wc -l < "$BASELINE") files"
    exit 0
fi

declare -A base
while read -r count file; do
    [ -n "${file:-}" ] && base["$file"]="$count"
done < "$BASELINE"

status=0
while read -r count file; do
    [ -n "${file:-}" ] || continue
    prev="${base[$file]:-0}"
    if [ "$count" -gt "$prev" ]; then
        echo "C901 regression: $file has $count complex-function violations (baseline: $prev)"
        status=1
    elif [ "$count" -lt "$prev" ]; then
        echo "C901 improvement: $file dropped to $count (baseline: $prev) — run $0 --update"
    fi
done < "$current"

if [ "$status" -eq 0 ]; then
    echo "C901 ratchet: no complexity growth ($(wc -l < "$BASELINE") baselined files)"
fi
exit "$status"
