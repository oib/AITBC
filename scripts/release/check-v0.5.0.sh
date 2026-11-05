#!/usr/bin/env bash
set -euo pipefail

# Pre-tag placeholder gate.
#
# Usage: bash scripts/release/check-v0.5.0.sh [--root DIR] [--tag TAG] [--with-services]
#
# --root DIR       tree to scan (default: the checkout containing this script)
# --tag TAG        base ref for the scope diff (default: last git tag)
# --with-services  also run the live-host checks (systemctl units, redis-cli);
#                  off by default so the gate runs on any checkout
#
# Exit codes: 0 clean, 1 placeholder found / check failed, 2 scan error
# (missing scan dir or grep failure — never silently "no match").

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TAG=""
WITH_SERVICES=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --root) ROOT="$2"; shift 2 ;;
        --tag) TAG="$2"; shift 2 ;;
        --with-services) WITH_SERVICES=1; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

SCAN_DIRS=(apps scripts contracts cli)
SCAN_PATHS=()
for d in "${SCAN_DIRS[@]}"; do
    SCAN_PATHS+=("$ROOT/$d")
done
# A missing scan dir makes grep exit 2 — scan_patterns reports that as an
# error (exit 2), never as "no match".

SELF_NAME="$(basename "$0")"

echo "=== Release placeholder gate ==="
echo "root: $ROOT"

# Scope diff against the last tag (informational).
if [[ -z "$TAG" ]]; then
    TAG=$(git -C "$ROOT" describe --tags --abbrev=0 2>/dev/null || true)
fi
if [[ -n "$TAG" ]]; then
    echo "base tag: $TAG"
    git -C "$ROOT" diff --stat "$TAG" 2>/dev/null | tail -3 || true
else
    echo "base tag: none found (skipping scope diff)"
fi
echo ""

# scan_patterns <label> <grep-pattern> <extra-excludes...>
# Prints matches and fails on rc>=2; exits 1 on any match.
scan_patterns() {
    local label="$1" pattern="$2"; shift 2
    local excludes=(--exclude-dir=tests --exclude="$SELF_NAME" "$@")
    local out rc
    if out=$(grep -rn "$pattern" "${SCAN_PATHS[@]}" \
            --include="*.service" --include="*.py" --include="*.env" --include="*.sh" \
            "${excludes[@]}" 2>&1); then
        rc=0
    else
        rc=$?
    fi
    if [[ $rc -ge 2 ]]; then
        echo "ERROR: grep failed (rc=$rc) scanning for '$pattern':" >&2
        echo "$out" >&2
        exit 2
    fi
    if [[ $rc -eq 0 ]]; then
        echo "$out"
        echo "FAILED: found '$pattern' in $label scan"
        exit 1
    fi
    echo "PASS: no '$pattern' in $label scan"
}

echo "1. Checking for 'change-me-in-production' placeholders..."
scan_patterns "deployable config" "change-me-in-production" \
    --exclude="config_pg.py" --exclude="config.py" --exclude="check-production-readiness.py"
echo ""

echo "2. Checking for 'your_*_here' placeholders..."
scan_patterns "deployable config" "your_.*_here" \
    --exclude="config.py" --exclude="settings.py" \
    --exclude="aitbc_completion.sh"
echo ""

if [[ $WITH_SERVICES -eq 1 ]]; then
    echo "3. Checking hardened services are active (--with-services)..."
    all_active=true
    for service in aitbc-coordinator-api.service aitbc-blockchain-node.service; do
        if systemctl is-active --quiet "$service"; then
            echo "PASS: $service active"
        else
            echo "FAIL: $service not active"
            all_active=false
        fi
    done
    [[ "$all_active" == true ]] || exit 1
    echo ""

    echo "4. Checking Redis connectivity..."
    if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
        echo "PASS: redis connected"
    else
        echo "note: redis not reachable (acceptable if not deployed)"
    fi
    echo ""
fi

echo "=== All checks passed ==="
