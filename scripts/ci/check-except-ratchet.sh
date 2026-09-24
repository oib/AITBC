#!/bin/bash
# Exception-handling ratchet — the same "baseline + gate the delta" mechanism as
# scripts/ci/check-c901-ratchet.sh, applied to broad/silent exception handling.
#
# BLE001 (blind `except Exception`) and S110 (try/except/pass) are not in ruff's
# select list, so `ruff check .` never reports them. This script is the real
# gate: it fails if any file gains *new* BLE001/S110 violations relative to
# scripts/ci/except-baseline.txt — i.e. silent exception swallowing cannot grow,
# only shrink. When a cleanup reduces a file below its baseline count,
# regenerate the baseline:
#
#   scripts/ci/check-except-ratchet.sh --update
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
BASELINE="scripts/ci/except-baseline.txt"
PYTHON="${PYTHON:-python3}"

current="$(mktemp)"
trap 'rm -f "$current"' EXIT
{ "$PYTHON" -m ruff check . --select BLE001,S110 --output-format concise 2>/dev/null || true; } \
    | grep -E ':[0-9]+:[0-9]+: (BLE001|S110) ' | cut -d: -f1 | sort | uniq -c > "$current"

if [ "${1:-}" = "--update" ]; then
    sort -k2 "$current" > "$BASELINE"
    echo "except baseline updated: $(wc -l < "$BASELINE") files"
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
        echo "except regression: $file has $count BLE001/S110 violations (baseline: $prev)"
        status=1
    elif [ "$count" -lt "$prev" ]; then
        echo "except improvement: $file dropped to $count (baseline: $prev) — run $0 --update"
    fi
done < "$current"

if [ "$status" -eq 0 ]; then
    echo "except ratchet: no growth ($(wc -l < "$BASELINE") baselined files)"
fi
exit "$status"
