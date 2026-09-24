"""Canonical test-suite classification shared by Makefile targets and CI.

`testpaths` in pyproject.toml lists every suite pytest can discover, but the
Make targets that CI invokes never ran most of them — exchange, wallet,
market, api-gateway, trading, security and the property suite sat in
`testpaths` for a release cycle without a single CI run. This module is the
one place that decides which discovered suite runs where:

- ``fast``    — offline-safe suites in the required PR gate (make test-critical).
- ``nightly`` — offline-safe but slower/broader suites; the scheduled job runs
                fast + nightly together.
- ``manual``  — need live services, hardware, or external network. Never run
                in CI; documented here so the parity guard knows the omission
                is deliberate.

The parity guard (scripts/ci/check_test_suite_parity.py) fails when a
testpaths entry is missing from this classification or a classified path
stops existing, so a suite cannot silently drop out of every gate again.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# The required PR gate: offline-safe suites, each reachable via a `make`
# target that ci.yml invokes (test-critical plus the pre-existing test /
# test-apps / test-governance / test-cli targets).
FAST_SUITES: tuple[str, ...] = (
    # previously gated via existing Make targets
    "tests/unit",  # make test
    "mcp-server/tests",  # make test
    "apps/coordinator-api/tests",  # make test-apps
    "apps/blockchain-node/tests",  # make test-apps
    "apps/governance/tests",  # make test-governance
    "cli/tests",  # make test-cli
    "tests/cli",  # make test-cli
    # added to the gate by make test-critical
    "apps/exchange/tests",
    "apps/api-gateway/tests",
    "apps/wallet/tests",
    "apps/market/tests",
    "apps/trading/tests",
    "apps/agent-coordinator/tests",
    "apps/bridge-monitor/tests",
    # smoke coverage added for previously zero-test apps (all offline-safe)
    "apps/ffmpeg/tests",
    "apps/hermes_agent/tests",
    "apps/ipfs/tests",
    "apps/monitoring-service/tests",
    "apps/shared-core/tests",
    "apps/shared-domain/tests",
    "apps/whisper/tests",
    "tests/security",
    "tests/core",
    "tests/property_tests",
    "tests/smoke",
)

# Offline-safe but slower or broader — the scheduled run sweeps these plus
# everything in FAST_SUITES.
NIGHTLY_SUITES: tuple[str, ...] = (
    "tests",  # whole dir — root-level modules and unlisted subdirs
    "tests/integration",
    "tests/coordinator",
    "tests/services",
    "apps/ai-engine/tests",
    "apps/gpu/tests",
    "apps/pool-hub/tests",
    "apps/blockchain-explorer/tests",
    "apps/miner/tests",
    "apps/zk-circuits/tests",
    "apps/edge/tests",
    "apps/blockchain-event-bridge/tests",
    "apps/memory/tests",
    "packages/py/aitbc-agent-core/tests",
    "packages/py/aitbc-agent-sdk/tests",
    "packages/py/aitbc-crypto/tests",
    "packages/py/aitbc-sdk/tests",
)

# Never in CI. Each entry documents the dependency that keeps it out. Entries
# not themselves in testpaths still matter: the nightly run sweeps their
# parent (e.g. `tests`) and excludes them via --ignore.
MANUAL_SUITES: dict[str, str] = {
    "tests/e2e": "drives a running fleet end-to-end",
    "tests/load": "load tests — deliberate stress, not correctness",
    "tests/ui-accessibility": "needs a browser/UI harness",
}


def testpaths() -> list[str]:
    """The pytest testpaths from pyproject.toml."""
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["tool"]["pytest"]["ini_options"]["testpaths"]


def classification() -> dict[str, str]:
    """testpaths entry -> fast|nightly|manual, resolving overlaps.

    A testpaths entry that is a parent of more specific entries (``tests``
    vs ``tests/e2e``) inherits the strictest needed treatment: it runs in
    nightly with the manual children excluded via --ignore.
    """
    classes: dict[str, str] = {}
    for entry in testpaths():
        if entry in FAST_SUITES:
            classes[entry] = "fast"
        elif entry in NIGHTLY_SUITES:
            classes[entry] = "nightly"
        elif entry in MANUAL_SUITES:
            classes[entry] = "manual"
        else:
            classes[entry] = "UNCLASSIFIED"
    return classes


def nightly_args() -> list[str]:
    """pytest args for the nightly run: nightly + fast dirs, manual excluded.

    Manual dirs nested under a swept parent (e.g. tests/e2e under tests) are
    excluded with --ignore rather than omitted from the dir list.
    """
    ignores: list[str] = []
    swept = [p for p in (*NIGHTLY_SUITES, *FAST_SUITES) if Path(REPO_ROOT / p).is_dir()]
    for manual in MANUAL_SUITES:
        if any(manual == d or manual.startswith(d + "/") for d in swept):
            ignores += ["--ignore", manual]
    return [*swept, *ignores]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parity"
    if mode == "fast":
        print(" ".join(FAST_SUITES))
    elif mode == "nightly":
        print(" ".join(nightly_args()))
    elif mode == "parity":
        bad = {k: v for k, v in classification().items() if v == "UNCLASSIFIED"}
        if bad:
            print("UNCLASSIFIED:", ", ".join(sorted(bad)))
            sys.exit(1)
        print("all testpaths classified")
