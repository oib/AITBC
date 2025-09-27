#!/usr/bin/env bash
set -euo pipefail
# Uncomment for debugging
# set -x

PROJECT_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PKG_PATHS="${PROJECT_ROOT}/packages/py/aitbc-crypto/src:${PROJECT_ROOT}/packages/py/aitbc-sdk/src"

cd "${PROJECT_ROOT}"

if command -v poetry >/dev/null 2>&1; then
  RUNNER=(poetry run)
else
  RUNNER=()
fi

run_pytest() {
  local py_path=$1
  shift
  if [ ${#RUNNER[@]} -gt 0 ]; then
    PYTHONPATH="$py_path" "${RUNNER[@]}" python -m pytest "$@"
  else
    PYTHONPATH="$py_path" python -m pytest "$@"
  fi
}

run_pytest "${PROJECT_ROOT}/apps/coordinator-api/src:${PKG_PATHS}" apps/coordinator-api/tests -q
run_pytest "${PKG_PATHS}" packages/py/aitbc-sdk/tests -q
run_pytest "${PROJECT_ROOT}/apps/miner-node/src:${PKG_PATHS}" apps/miner-node/tests -q
run_pytest "${PROJECT_ROOT}/apps/wallet-daemon/src:${PKG_PATHS}" apps/wallet-daemon/tests -q
