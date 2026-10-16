#!/bin/bash
# Wrapper for `python -m bridge_monitor.admin` — sets PYTHONPATH so the
# command works from any cwd, not only from apps/bridge-monitor with a
# hand-set PYTHONPATH. Mirrors the service unit's interpreter and path.
#
#   scripts/ops/bridge-admin.sh <command> [args...]
#
# DATA_DIR / AITBC_DATA_DIR / BRIDGE_DEPOSITS_DB / BRIDGE_MONITOR_ENV / --env-file
# behave as in bridge_monitor.admin itself (default ledger:
# /var/lib/aitbc/data/bridge_deposits.db). BRIDGE_DEPOSITS_DB, when set, overrides the
# ledger path outright and is inherited by the child process like any env var.
set -euo pipefail

repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)

PYTHON=${PYTHON:-"$repo_root/venv/bin/python"}
if [ ! -x "$PYTHON" ]; then
    echo "error: $PYTHON not found or not executable (set PYTHON=...)" >&2
    exit 1
fi

export PYTHONPATH="$repo_root/apps/bridge-monitor/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m bridge_monitor.admin "$@"
