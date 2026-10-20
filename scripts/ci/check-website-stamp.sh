#!/bin/bash
# pre-commit guard: stamped website asset references (?v=<content hash>) must
# match what scripts/ops/stamp-website-assets.py would write. Check-only — the
# hook never rewrites pages; on drift it names the fix and exits 1.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"

# Shared resolution: $PYTHON env, checkout venv, then main-checkout venv.
PYTHON="$("$(dirname "${BASH_SOURCE[0]}")/repo-python.sh")" || exit 1

if ! "$PYTHON" scripts/ops/stamp-website-assets.py --check; then
    echo "website asset stamp drift detected — run" >&2
    echo "  $PYTHON scripts/ops/stamp-website-assets.py" >&2
    echo "and restage the restamped pages." >&2
    exit 1
fi
