#!/bin/bash
# The zk circuits exist in two trees: `apps/zk-circuits/` is the build
# workspace (package.json, tests, compile_cached.py) and
# apps/coordinator-api/.../zk-circuits/ is what the service loads at
# runtime (V23-26). Compiled artifacts may legitimately differ between
# trees (separate trusted-setup ceremonies), but the .circom SOURCES must
# stay identical — a source-only drift means the deployed verifier checks
# different constraints than the ones under test.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

BUILD=apps/zk-circuits
PKG=apps/coordinator-api/src/coordinator_api/contexts/zk_applications/zk-circuits

rc=0
for src in "$BUILD"/*.circom; do
    name=$(basename "$src")
    pkg="$PKG/$name"
    if [ ! -f "$pkg" ]; then
        echo "MISSING in deployed tree: $pkg" >&2
        rc=1
    elif ! cmp -s "$src" "$pkg"; then
        echo "SOURCE DRIFT: $name differs between build and deployed trees" >&2
        rc=1
    fi
done
for pkg in "$PKG"/*.circom; do
    name=$(basename "$pkg")
    if [ ! -f "$BUILD/$name" ]; then
        echo "MISSING in build tree: $BUILD/$name" >&2
        rc=1
    fi
done

if [ "$rc" -eq 0 ]; then
    echo "zk circuit sources in sync"
fi
exit $rc
