#!/usr/bin/env bash
# Security-suite nightly tier (#1213, layout approved on #1196 comment 16932).
#
# Runs, in order:
#   1. offline pin tiers:   pytest tests/security/{unit,integration,config}
#   2. live edge probes:    tests/security/live/run_live_probes.sh
#                           (GET-only, skip-graceful; rate-limit probe needs
#                           AITBC_LIVE_GATEWAY_KEY — operator-provisioned,
#                           SKIPs cleanly when unset)
#   3. mutation spots:      scripts/security/mutation_spots.py
#                           (verifies pins actually fail on revert)
#
# Exit 0 = green modulo skips; exit 1 = at least one FAIL.
#
# Scheduling (repo-side wiring only — host install is an ops action):
#   * gitea-runner: systemd timer pair scripts/security/aitbc-security-nightly.{service,timer}
#   * or the nightly.yml workflow step (fires only while the repo Actions
#     unit is enabled — currently disabled by policy)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-$REPO_ROOT/venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="python3"
export PYTHON

FAILED=0

echo "=== [1/3] offline pin tiers (unit + integration + config) ==="
if "$PYTHON" -m pytest tests/security/unit tests/security/integration tests/security/config -q --no-header; then
    echo "offline tiers: PASS"
else
    echo "offline tiers: FAIL"
    FAILED=1
fi

echo "=== [2/3] live edge probes ==="
if bash tests/security/live/run_live_probes.sh; then
    echo "live probes: PASS"
else
    echo "live probes: FAIL"
    FAILED=1
fi

echo "=== [3/3] mutation spots ==="
if "$PYTHON" scripts/security/mutation_spots.py; then
    echo "mutation spots: PASS"
else
    echo "mutation spots: FAIL"
    FAILED=1
fi

echo "=== nightly security suite: $([ $FAILED -eq 0 ] && echo PASS || echo FAIL) ==="
exit "$FAILED"
