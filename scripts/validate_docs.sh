#!/usr/bin/env bash
# Validate all internal markdown links in the AITBC documentation tree.
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_DIR/venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

exec "$PYTHON" "$REPO_DIR/scripts/docs/check_links.py"
