#!/usr/bin/env bash
# Live edge probes — read-only GET/HEAD checks against a deployed AITBC edge.
# Nightly/ops tier only; never wire into pre-commit or the fast CI gate.
#
#   AITBC_LIVE_BASE_URL   target edge (default https://hub.aitbc.bubuit.net)
#   AITBC_LIVE_GATEWAY_KEY   valid gateway key — enables the rate-limit probe
#                         (never committed; supply via env at run time)
#   AITBC_LIVE_PROBE_RATELIMIT=0   skip the rate-limit burst probe
#   AITBC_LIVE_RATELIMIT_PROBE_COUNT   burst size (default 105)
#
# Exit 0 = all PASS/SKIP, 1 = any FAIL.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON="${PYTHON:-$REPO_ROOT/venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="python3"

exec "$PYTHON" "$REPO_ROOT/tests/security/live/probes.py" "$@"
