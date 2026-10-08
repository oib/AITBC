#!/usr/bin/env python3
"""Read-only bridge mainnet preflight (BR-5).

Implements the knob checks from the B7 readiness paper
(TOPOLOGY/2026-10-08-b7-bridge-mainnet-readiness.md). Reads configuration
only -- the process environment, or ``--env-file PATH`` for a file of
``KEY=value`` lines (e.g. a staging copy of ``bridge-monitor.env`` /
``blockchain.env``). No RPC, no network, no writes.

    python scripts/ops/bridge_mainnet_preflight.py --env-file prod.env

Prints one PASS/FAIL line per knob and exits 0 only when all pass. On the
current Sepolia testnet configuration every knob is expected to FAIL --
that is the point: the script must be green before mainnet, not after.

Knobs (env var -- rule):
    ETH_NETWORK                 == "mainnet" (selects the mainnet Chainlink map)
    ETH/USD feed (derived)      resolves to the mainnet aggregator
    BRIDGE_CONFIRMATIONS        >= 12 (code default is 3, a testnet depth)
    AIT_USD_FIXED_PRICE         unset (a pin silently bypasses every feed)
    AIT_EUR_FIXED_PRICE         unset (same for the EUR anchor)
    CHAINLINK_MAX_AGE_SECONDS   set and <= 5400 (mainnet heartbeats ~1h)
    BRIDGE_MAX_PAYOUT_AIT       set (absolute per-payout ceiling, reviewed
                                for mainnet deposit sizes)
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

# aitbc/oracles/price_oracle.py CHAINLINK_FEEDS_* — kept as literals so the
# script stays dependency-free; the test suite pins them against the oracle.
MAINNET_ETH_USD_FEED = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"
SEPOLIA_ETH_USD_FEED = "0x694AA1769357215DE4FAC081bf1f309aDC325306"

MIN_CONFIRMATIONS = 12
MAX_STALENESS_SECONDS = 5400  # ~1.5x the 1h mainnet Chainlink heartbeat


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def check_config(env: dict[str, str]) -> list[Check]:
    checks: list[Check] = []

    network = env.get("ETH_NETWORK", "").strip().lower()
    checks.append(
        Check(
            "ETH_NETWORK",
            network == "mainnet",
            f"ETH_NETWORK={env.get('ETH_NETWORK', '<unset>')!r} — must be 'mainnet' "
            "(anything else selects the Sepolia/test feed map)",
        )
    )
    feed = MAINNET_ETH_USD_FEED if network == "mainnet" else SEPOLIA_ETH_USD_FEED
    checks.append(
        Check(
            "chainlink feed",
            network == "mainnet" and feed == MAINNET_ETH_USD_FEED,
            f"ETH/USD feed resolves to {feed} — must be the mainnet aggregator",
        )
    )

    raw = env.get("BRIDGE_CONFIRMATIONS", "")
    try:
        confirmations = int(raw)
    except ValueError:
        confirmations = 3  # code default when unset/unparseable
    checks.append(
        Check(
            "BRIDGE_CONFIRMATIONS",
            confirmations >= MIN_CONFIRMATIONS,
            f"effective depth {confirmations} (env={raw or '<unset>'}) — mainnet needs >= {MIN_CONFIRMATIONS}",
        )
    )

    for pin in ("AIT_USD_FIXED_PRICE", "AIT_EUR_FIXED_PRICE"):
        value = env.get(pin)
        checks.append(
            Check(
                pin,
                not value,
                f"{pin}={value!r} — a fixed pin silently bypasses every price feed" if value else f"{pin} unset",
            )
        )

    raw = env.get("CHAINLINK_MAX_AGE_SECONDS", "")
    try:
        max_age = int(raw) if raw else 259200  # code default
        ok = 0 < max_age <= MAX_STALENESS_SECONDS
    except ValueError:
        max_age, ok = raw, False
    checks.append(
        Check(
            "CHAINLINK_MAX_AGE_SECONDS",
            ok,
            f"effective staleness gate {raw or '<unset, default 259200>'} s — mainnet needs <= {MAX_STALENESS_SECONDS} s",
        )
    )

    payout_cap = env.get("BRIDGE_MAX_PAYOUT_AIT", "")
    checks.append(
        Check(
            "BRIDGE_MAX_PAYOUT_AIT",
            bool(payout_cap.strip()),
            f"absolute per-payout ceiling {payout_cap or '<unset>'} — must be set and sized for mainnet deposits",
        )
    )
    return checks


def load_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", help="env file to check (default: process environment)")
    args = parser.parse_args(argv)

    env = load_env_file(args.env_file) if args.env_file else dict(os.environ)
    checks = check_config(env)

    print("BRIDGE MAINNET PREFLIGHT (read-only; checks config only — no RPC, no chain reads)")
    for check in checks:
        print(f"  {'PASS' if check.passed else 'FAIL'}  {check.name:<26} {check.detail}")

    failed = [c for c in checks if not c.passed]
    if failed:
        print(f"\n{len(failed)}/{len(checks)} knob(s) NOT ready for mainnet")
        return 1
    print(f"\n{len(checks)}/{len(checks)} knobs ready for mainnet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
