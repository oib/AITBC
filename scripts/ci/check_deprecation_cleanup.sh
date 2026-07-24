#!/usr/bin/env bash
# Deprecation cleanup verifier for v0.11.0.
# Fails the build if deprecated branding (AIPowerRental), light-theme assets,
# or hardcoded API keys remain in the source tree.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/aitbc}"
# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/ci/setup-job-logging.sh" 2>/dev/null || true

fail=0

check_grep() {
    local name="$1"
    local pattern="$2"
    local matches

    matches=$(
        grep -RInE \
            --exclude-dir=.git \
            --exclude-dir=.venv \
            --exclude-dir=venv \
            --exclude-dir=node_modules \
            --exclude-dir=contracts \
            --exclude-dir=docs \
            --exclude-dir=__pycache__ \
            --exclude="*.pyc" \
            --exclude="*.lock" \
            --exclude="package-lock.json" \
            --exclude="check_deprecation_cleanup.sh" \
            "$pattern" \
            "$REPO_ROOT/aitbc" \
            "$REPO_ROOT/apps" \
            "$REPO_ROOT/cli" \
            "$REPO_ROOT/scripts" \
            2>/dev/null || true
    )

    if [[ -n "$matches" ]]; then
        echo "Found deprecated $name references:"
        echo "$matches"
        fail=1
    fi
}

echo "Checking for deprecated AIPowerRental references..."
check_grep "AIPowerRental" "AIPowerRental"

echo "Checking for light-theme references..."
check_grep "light-theme" "(light[-_]?theme|theme[^\n]{0,20}light|light[-_]?mode|light[-_]?css)"

echo "Running secret scan..."
if ! "${REPO_ROOT}/venv/bin/python" "${REPO_ROOT}/scripts/security/scan_secrets.py" --root "$REPO_ROOT"; then
    fail=1
fi

if [[ "$fail" -eq 0 ]]; then
    echo "Deprecation cleanup checks passed."
else
    echo "Deprecation cleanup checks failed."
    exit 1
fi
