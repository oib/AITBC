#!/bin/bash
# Fail if the committed MCP CLI tool modules differ from what the generator
# would emit for the current aitbc CLI command tree.
#
# This is the CLI/MCP parity gate: when someone adds, removes, or renames a
# Click command (or changes its options/arguments) without regenerating the
# split group modules in mcp-server/, the check fails.

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
"$PYTHON" scripts/dev/generate_mcp_cli_tools.py --mode all --split-by-group --output "$generated"
"$RUFF" format --quiet "$generated" "$tmpdir"/aitbc_mcp_cli_tools_generated_*.py

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
  echo "Run: python3 scripts/dev/generate_mcp_cli_tools.py --mode all --split-by-group" >&2
  exit 1
fi
