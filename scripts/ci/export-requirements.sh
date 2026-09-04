#!/bin/bash
# Regenerate pinned requirements files from poetry.lock.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
header="# Generated from poetry.lock by scripts/ci/export-requirements.sh.\n# Do not edit manually; run this script to regenerate.\n\n"
run_export() {
    local group="$1"
    local output="$2"
    shift 2
    poetry export --only "$group" --without-hashes -o "$output" "$@"
    { printf '%b' "$header"; cat "$output"; } > "${output}.tmp"
    mv "${output}.tmp" "$output"
}
# --extras fhe: tenseal is an optional main dependency; CI's FHE tests
# (apps/coordinator-api/tests/test_routers_fhe.py) need the real TenSEAL
# backend, not the mock fallback, so pull it into requirements.txt.
run_export main requirements.txt --extras fhe
run_export dev requirements-dev.txt
echo "Exported requirements.txt and requirements-dev.txt from poetry.lock"
