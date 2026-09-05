#!/bin/bash
# Emit requirements-dev.txt as a pip *constraints* file on stdout.
#
# The dev export cannot be used as a constraints file directly: pip rejects
# constraints carrying extras ("ERROR: Constraints cannot have extras"), and
# the export contains `coverage[toml]==7.13.5`. The extra only selects optional
# dependencies of coverage; it has no bearing on pinning the version, so it is
# safe to drop for constraint purposes.
#
# Kept as one script rather than duplicated sed in both installer paths, so the
# two cannot diverge. tests/test_requirements_tiers.py runs it and asserts the
# output is constraint-legal.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEV_REQ="${1:-$REPO_ROOT/requirements-dev.txt}"

if [ ! -f "$DEV_REQ" ]; then
    echo "dev-constraints.sh: $DEV_REQ not found" >&2
    exit 1
fi

# Strip the extras marker from the distribution name only. Environment markers
# after the ';' contain no brackets, so the anchored match cannot touch them.
sed -E 's/^([A-Za-z0-9._-]+)\[[^]]*\]/\1/' "$DEV_REQ"
