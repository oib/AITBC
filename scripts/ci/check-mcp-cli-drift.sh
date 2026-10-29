#!/bin/bash
# Fail if the committed MCP CLI tool modules differ from what the generator
# would emit for the current aitbc CLI command tree.
#
# This is the CLI/MCP parity gate: when someone adds, removes, or renames a
# Click command (or changes its options/arguments) without regenerating the
# split group modules in mcp-server/, the check fails.

set -euo pipefail

cd "$(dirname "$0")/../.."

# Shared resolution: $PYTHON env, checkout venv, then main-checkout venv.
PYTHON="$("$(dirname "${BASH_SOURCE[0]}")/repo-python.sh")" || exit 1

# ruff must be the pinned one — a PATH ruff at a different version formats the
# generated files differently and reports false drift. `python -m ruff` on the
# resolved interpreter is pinned by construction; RUFF= stays an explicit
# override.
if [ -n "${RUFF:-}" ]; then
  RUFF_CMD=("$RUFF")
else
  RUFF_CMD=("$PYTHON" -m ruff)
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

generated="$tmpdir/aitbc_mcp_cli_tools_generated.py"
"$PYTHON" scripts/dev/generate_mcp_cli_tools.py --mode all --split-by-group --output "$generated"
"${RUFF_CMD[@]}" format --quiet "$generated" "$tmpdir"/aitbc_mcp_cli_tools_generated_*.py

drifted=0
for src in mcp-server/aitbc_mcp_cli_tools_generated*.py; do
  name="$(basename "$src")"
  if [ ! -f "$tmpdir/$name" ]; then
    echo "Missing generated file: $name" >&2
    drifted=1
    continue
  fi
  if ! diff -q "$src" "$tmpdir/$name" >/dev/null; then
    echo "Drift detected: $src" >&2
    drifted=1
  fi
done

if [ "$drifted" -ne 0 ]; then
  echo "MCP CLI tool modules are out of sync with the current CLI command tree." >&2
  echo "Run: $PYTHON scripts/dev/generate_mcp_cli_tools.py --mode all --split-by-group  (self-formats its output)" >&2
  exit 1
fi

# The generated-diff above cannot see the hand-written files' route/command
# literals (the stale `cross-chain/swap` -> 404, `market offers`, and
# `unpin --rental-id` bugs all lived there). Validate them against the live
# Click tree and the FastAPI routers, and keep the inventory doc in sync.
"$PYTHON" scripts/ci/check-mcp-tool-surface.py
"$PYTHON" scripts/dev/gen_mcp_tool_inventory.py --check
