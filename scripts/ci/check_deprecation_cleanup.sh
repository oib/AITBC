#!/usr/bin/env bash
# Deprecation cleanup verifier for v0.11.0.
# Fails the build if deprecated branding (AIPowerRental), light-theme assets,
# or hardcoded API keys remain in the source tree.

set -euo pipefail

# The checkout this script lives in — a hardcoded /opt/aitbc scans the
# reference clone and never the change being committed (#986).
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/ci/setup-job-logging.sh" 2>/dev/null || true

fail=0

# Shared resolution: $PYTHON env, checkout venv, then main-checkout venv — a
# hardcoded $REPO_ROOT/venv/bin/python fails outright inside a linked worktree.
PYTHON="$("$(dirname "${BASH_SOURCE[0]}")/repo-python.sh")" || exit 1

check_grep() {
    local name="$1"
    local pattern="$2"
    local matches

    local grc=0
    set +e
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
            "$REPO_ROOT/website" \
            2>&1
    )
    grc=$?
    set -e

    if [[ "$grc" -gt 1 ]]; then
        # grep rc 2 is a real error (unreadable/missing tree) — the old
        # `|| true` folded it into "no matches" and hid a broken scan.
        echo "grep failed (rc=$grc) scanning for $name:"
        echo "$matches"
        fail=1
        return
    fi

    if [[ -n "$matches" ]]; then
        echo "Found deprecated $name references:"
        echo "$matches"
        fail=1
    fi
}

# The deprecated *branding* is the spaced/dashed product name and the old
# domain — the single-token AIPowerRental is a live contract
# (contracts/contracts/AIPowerRental.sol) and legitimately referenced in
# code, so it is deliberately not the pattern (#986).
echo "Checking for deprecated AIPowerRental branding..."
check_grep "AIPowerRental branding" "AI[ -]Power[ -]Rental|aipowerrental"

echo "Checking for light-theme references..."
check_grep "light-theme" "(light[-_]?theme|theme[^\n]{0,20}light|light[-_]?mode|light[-_]?css)"

echo "Running secret scan..."
if ! "$PYTHON" "${REPO_ROOT}/scripts/security/scan_secrets.py" --root "$REPO_ROOT"; then
    fail=1
fi

if [[ "$fail" -eq 0 ]]; then
    echo "Deprecation cleanup checks passed."
else
    echo "Deprecation cleanup checks failed."
    exit 1
fi
