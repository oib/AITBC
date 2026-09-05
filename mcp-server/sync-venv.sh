#!/bin/bash
# Refresh a dedicated MCP-server venv after a repo pull.
#
# setup.sh and update.sh only maintain <repo>/venv. A dedicated venv running
# the MCP server (e.g. on the IDE host, or a side venv on a live node) drifts:
# new repo-local path packages such as aitbc-errors are never installed into
# it, and `import aitbc` then fails at server start -- the MCP host reports a
# generic "cannot connect" instead of the real error.
#
# This script performs the same three steps the project venv gets:
#   1. mcp-server/requirements.txt
#   2. repo-local path packages (via scripts/utils/install-path-packages.sh)
#   3. a smoke test that `import aitbc` resolves the full package the way the
#      MCP server sees it (PYTHONPATH=<repo>)
#
# Usage: sync-venv.sh <venv-dir>
#
# Hosts that run update.sh can instead list the venv in AITBC_EXTRA_VENVS
# (space-separated, e.g. in /etc/aitbc/node.env or the service environment) --
# install-path-packages.sh then refreshes it automatically on every update.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${1:-}"

if [ -z "$VENV_DIR" ]; then
    echo "Usage: $0 <venv-dir>" >&2
    echo "  e.g. $0 /opt/aitbc/venv-mcp" >&2
    exit 2
fi

PY="$VENV_DIR/bin/python"
if [ ! -x "$PY" ]; then
    echo "[ERROR] No interpreter at $PY -- create the venv first." >&2
    exit 1
fi

echo "[INFO] Installing mcp-server requirements into $VENV_DIR"
"$PY" -m pip install -r "$REPO_ROOT/mcp-server/requirements.txt"

"$REPO_ROOT/scripts/utils/install-path-packages.sh" "$VENV_DIR"

# The MCP server runs with PYTHONPATH=<repo>, so `import aitbc` resolves the
# real package -- including aitbc.exceptions -> aitbc_errors. Prove that chain
# here; a missing path package fails loudly instead of at server start.
echo "[INFO] Verifying the MCP import chain"
if ! PYTHONPATH="$REPO_ROOT" "$PY" -c "import aitbc"; then
    echo "[ERROR] 'import aitbc' failed with PYTHONPATH=$REPO_ROOT." >&2
    exit 1
fi

echo "[OK] MCP venv $VENV_DIR is in sync."
