#!/bin/bash
# Fail if the committed MCP CLI tool module differs from what the generator
# would emit for the current aitbc CLI command tree.
#
# This is the CLI/MCP parity gate: when someone adds, removes, or renames a
# Click command (or changes its options/arguments) without regenerating
# mcp-server/aitbc_mcp_cli_tools_generated.py, the check fails.

set -euo pipefail

cd "$(dirname "$0")/../.."

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x ./venv/bin/python ]; then PYTHON=./venv/bin/python; else PYTHON=python3; fi
fi

RUFF="${RUFF:-}"
if [ -z "$RUFF" ]; then
  if [ -x ./venv/bin/ruff ]; then RUFF=./venv/bin/ruff; else RUFF=ruff; fi
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

generated="$tmpdir/aitbc_mcp_cli_tools_generated.py"
"$PYTHON" scripts/dev/generate_mcp_cli_tools.py --mode all --output "$generated"
"$RUFF" format --quiet "$generated"

if ! diff -q mcp-server/aitbc_mcp_cli_tools_generated.py "$generated" >/dev/null; then
  echo "MCP CLI tool module is out of sync with the current CLI command tree." >&2
  echo "Run: python3 scripts/dev/generate_mcp_cli_tools.py --mode all" >&2
  exit 1
fi
