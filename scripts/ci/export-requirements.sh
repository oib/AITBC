#!/bin/bash
# Regenerate pinned requirements files from poetry.lock.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
header="# Generated from poetry.lock by scripts/ci/export-requirements.sh.\n# Do not edit manually; run this script to regenerate.\n\n"
# Toolchain pins (pip/setuptools/wheel) leak into the lockfile through
# transitive dev deps like pip-api. The toolchain floats -- the install paths
# (install-profiles.sh, update.sh, setup-python-venv.sh) manage pip themselves
# and every installer already filters these lines. Strip them at export too so
# the file does not carry a pin nothing enforces. The same regex lives in
# install-profiles.sh as TOOLCHAIN_FILTER; keep them in sync.
TOOLCHAIN_FILTER='^(pip|setuptools|wheel)[[:space:]]*(==|[<>=!~])'

# Marker serialization is plugin-version-sensitive: the committed exports were
# generated with poetry-plugin-export 1.10.1 (the version install-profiles.sh
# lands in venv-poetry). A different plugin writes differently-shaped markers,
# which is how the committed files drifted from the lock once before (DEPS-1).
# Fail loudly instead of emitting a differently-shaped export.
EXPECTED_EXPORT_PLUGIN="1.10.1"
command -v poetry >/dev/null || {
    echo "error: poetry not on PATH (expected /opt/aitbc/venv-poetry/bin)" >&2
    exit 1
}
plugin_version="$(poetry self show plugins 2>/dev/null \
    | sed -n 's/.*poetry-plugin-export (\(.*\)).*/\1/p')" || true
if [ "$plugin_version" != "$EXPECTED_EXPORT_PLUGIN" ]; then
    echo "error: need poetry-plugin-export $EXPECTED_EXPORT_PLUGIN," \
        "found '${plugin_version:-not installed}'." >&2
    echo "install-profiles.sh installs the plugin unpinned; regenerate with" >&2
    echo "the venv-poetry toolchain or bump EXPECTED_EXPORT_PLUGIN deliberately." >&2
    exit 1
fi

run_export() {
    local group="$1"
    local output="$2"
    shift 2
    poetry export --only "$group" --without-hashes -o "$output" "$@"
    # Path dependencies (e.g. aitbc-shared) are exported as absolute
    # file://$REPO_ROOT/... URLs, which makes the file uninstallable on any
    # checkout not at that path. Rewrite them to repo-relative paths.
    { printf '%b' "$header"; grep -vE "$TOOLCHAIN_FILTER" "$output" \
        | sed "s|-e file://$REPO_ROOT/|-e ./|g"; } > "${output}.tmp"
    mv "${output}.tmp" "$output"
}
# --extras fhe: tenseal is an optional main dependency; CI's FHE tests
# (apps/coordinator-api/tests/test_routers_fhe.py) need the real TenSEAL
# backend, not the mock fallback, so pull it into requirements.txt.
run_export main requirements.txt --extras fhe
run_export dev requirements-dev.txt
echo "Exported requirements.txt and requirements-dev.txt from poetry.lock"
