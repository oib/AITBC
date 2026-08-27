#!/bin/bash
# pre-commit / CI guard: cli docs must match the live command tree.
#
# Running the full pytest suite just for these two tests is heavy, so this
# script runs the focused pair and then checks that the generator would not
# rewrite the docs. Either guard alone could miss a case; together they cover
# both the test assertions and the generation contract.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x ./venv/bin/python ]; then
    PYTHON=./venv/bin/python
  else
    PYTHON=python3
  fi
fi

echo "==> Running CLI doc sync tests"
"$PYTHON" -m pytest -q tests/test_cli_docs_sync.py tests/test_syspath_hygiene.py

echo "==> Checking cli docs generator would not change output"
"$PYTHON" scripts/generate_cli_docs.py --check
