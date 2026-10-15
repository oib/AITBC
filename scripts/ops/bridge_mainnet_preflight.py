#!/usr/bin/env python3
"""Read-only bridge mainnet preflight (BR-5).

Implements the knob checks from the B7 readiness paper
(TOPOLOGY/2026-10-08-b7-bridge-mainnet-readiness.md). Reads configuration
only -- the process environment, or ``--env-file PATH`` for a file of
``KEY=value`` lines (e.g. a staging copy of ``bridge-monitor.env`` /
``blockchain.env``). ``--env-file`` may be repeated; later files override
earlier ones, in the same order rule as a systemd ``EnvironmentFile``
list, and a path prefixed with ``-`` is optional (skipped when missing),
mirroring systemd's ``EnvironmentFile=-`` syntax. No RPC, no network,
no writes.

    python scripts/ops/bridge_mainnet_preflight.py --env-file prod.env
    python scripts/ops/bridge_mainnet_preflight.py \
        --env-file /etc/aitbc/blockchain.env \
        --env-file -/etc/aitbc/blockchain-secrets.env \
        --env-file /etc/aitbc/node.env \
        --env-file /etc/aitbc/aitbc-bridge-monitor.env

Prints one PASS/FAIL line per knob and exits 0 only when all pass.

Profiles (``--profile``, default ``mainnet``):

- ``mainnet`` — on the current Sepolia testnet configuration every knob is
  expected to FAIL -- that is the point: the script must be green before
  mainnet, not after.
- ``sepolia`` — the same seven knobs read against testnet expectations, so
  the live fleet configuration can report PASS. A sepolia PASS proves the
  *testnet* configuration is coherent only; it says nothing about mainnet
  readiness and must never be read as such (the header names the profile).

Knobs (env var -- mainnet rule / sepolia rule):
    ETH_NETWORK                 == "mainnet" / == "sepolia" — strict match;
                                  the oracle maps anything-but-"sepolia"
                                  (including unset) to the mainnet feed map
    ETH/USD feed (derived)      resolves to the mainnet / Sepolia aggregator
    BRIDGE_CONFIRMATIONS        >= 12 / >= 3 (the code's own default depth;
                                  apps/bridge-monitor/main.py reads 3 unset)
    AIT_USD_FIXED_PRICE         unset / allowed — a pin is how testnet sets
                                  its fixed AIT price, so a set pin reports
                                  PASS with an INFO detail naming the value
    AIT_EUR_FIXED_PRICE         unset / allowed (same for the EUR anchor)
    CHAINLINK_MAX_AGE_SECONDS   set and <= 5400 (~1.5x the ~1h mainnet
                                  heartbeat) / set and <= 259200 — the
                                  oracle's own default is already the
                                  deliberately generous bound for Sepolia's
                                  sparse test feeds; a configured value
                                  above it is looser than what the code
                                  itself considers tolerable, so that is
                                  the sepolia bound (still must be set:
                                  an absent knob on testnet means the
                                  operator never reviewed staleness)
    BRIDGE_MAX_PAYOUT_AIT       set / set (absolute per-payout ceiling)

Part B usage — mainnet-style staging env stacked in the real unit order
(synthetic files only; never key-bearing envs):

    python scripts/ops/bridge_mainnet_preflight.py \
        --env-file staging/blockchain.env \
        --env-file -staging/blockchain-secrets.env \
        --env-file staging/node.env \
        --env-file staging/aitbc-bridge-monitor.env
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
# bridge_monitor reads BRIDGE_CONFIRMATIONS default "3"; the oracle reads
# CHAINLINK_MAX_AGE_SECONDS default "259200" (3 days) for sparse Sepolia feeds.
SEPOLIA_MIN_CONFIRMATIONS = 3
SEPOLIA_MAX_STALENESS_SECONDS = 259200


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def check_config(env: dict[str, str], profile: str = "mainnet") -> list[Check]:
    sepolia = profile == "sepolia"
    checks: list[Check] = []

    network = env.get("ETH_NETWORK", "").strip().lower()
    want_network = "sepolia" if sepolia else "mainnet"
    checks.append(
        Check(
            "ETH_NETWORK",
            network == want_network,
            f"ETH_NETWORK={env.get('ETH_NETWORK', '<unset>')!r} — must be {want_network!r} "
            "(anything else selects the " + ("mainnet" if sepolia else "Sepolia/test") + " feed map)",
        )
    )
    feed = MAINNET_ETH_USD_FEED if network == "mainnet" else SEPOLIA_ETH_USD_FEED
    want_feed = SEPOLIA_ETH_USD_FEED if sepolia else MAINNET_ETH_USD_FEED
    checks.append(
        Check(
            "chainlink feed",
            feed == want_feed,
            f"ETH/USD feed resolves to {feed} — must be the {want_network} aggregator",
        )
    )

    raw = env.get("BRIDGE_CONFIRMATIONS", "")
    try:
        confirmations = int(raw)
    except ValueError:
        confirmations = 3  # code default when unset/unparseable
    min_conf = SEPOLIA_MIN_CONFIRMATIONS if sepolia else MIN_CONFIRMATIONS
    checks.append(
        Check(
            "BRIDGE_CONFIRMATIONS",
            confirmations >= min_conf,
            f"effective depth {confirmations} (env={raw or '<unset>'}) — {want_network} needs >= {min_conf}",
        )
    )

    for pin in ("AIT_USD_FIXED_PRICE", "AIT_EUR_FIXED_PRICE"):
        value = env.get(pin)
        if sepolia:
            detail = (
                f"INFO: {pin} pinned at {value!r} — allowed on testnet (fixed AIT price by design)"
                if value
                else f"{pin} unset"
            )
            checks.append(Check(pin, True, detail))
        else:
            checks.append(
                Check(
                    pin,
                    not value,
                    f"{pin}={value!r} — a fixed pin silently bypasses every price feed" if value else f"{pin} unset",
                )
            )

    raw = env.get("CHAINLINK_MAX_AGE_SECONDS", "")
    max_staleness = SEPOLIA_MAX_STALENESS_SECONDS if sepolia else MAX_STALENESS_SECONDS
    try:
        if not raw:
            raise ValueError("unset")
        max_age = int(raw)
        ok = 0 < max_age <= max_staleness
    except ValueError:
        max_age, ok = raw, False
    if sepolia:
        detail = f"effective staleness gate {raw or '<unset>'} s — sepolia needs a set value <= {max_staleness} s"
    else:
        detail = f"effective staleness gate {raw or '<unset, default 259200>'} s — mainnet needs <= {max_staleness} s"
    checks.append(Check("CHAINLINK_MAX_AGE_SECONDS", ok, detail))

    payout_cap = env.get("BRIDGE_MAX_PAYOUT_AIT", "")
    checks.append(
        Check(
            "BRIDGE_MAX_PAYOUT_AIT",
            bool(payout_cap.strip()),
            f"absolute per-payout ceiling {payout_cap or '<unset>'} — must be set and sized for {want_network} deposits",
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


def load_env_files(paths: list[str]) -> dict[str, str]:
    """Merge env files in order, systemd EnvironmentFile style.

    Later files override earlier ones. A path prefixed with ``-`` is
    optional and skipped when missing; any other missing file raises
    FileNotFoundError, as a missing mandatory EnvironmentFile would.
    """
    env: dict[str, str] = {}
    for raw in paths:
        optional = raw.startswith("-")
        path = raw[1:] if optional else raw
        if not os.path.exists(path):
            if optional:
                continue
            raise FileNotFoundError(path)
        env.update(load_env_file(path))
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--env-file",
        action="append",
        metavar="PATH",
        help="env file to check, systemd EnvironmentFile order — repeatable, "
        "later files override; prefix '-' marks an optional file "
        "(default: process environment)",
    )
    parser.add_argument(
        "--profile",
        choices=("mainnet", "sepolia"),
        default="mainnet",
        help="which network profile to evaluate (default: mainnet)",
    )
    # argparse refuses a value starting with '-' after "--env-file" — but the
    # optional-file marker is exactly that ("--env-file -/path"). Fold the pair
    # into "--env-file=-/path" before parsing so the documented form works.
    argv = list(sys.argv[1:] if argv is None else argv)
    folded: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--env-file" and i + 1 < len(argv) and argv[i + 1].startswith("-") and not argv[i + 1].startswith("--"):
            folded.append("--env-file=" + argv[i + 1])
            i += 2
        else:
            folded.append(argv[i])
            i += 1
    argv = folded
    args = parser.parse_args(argv)

    if args.env_file:
        try:
            env = load_env_files(args.env_file)
        except FileNotFoundError as exc:
            parser.error(f"env file not found: {exc.args[0]}")
    else:
        env = dict(os.environ)
    checks = check_config(env, profile=args.profile)

    if args.profile == "sepolia":
        print("BRIDGE SEPOLIA PREFLIGHT (profile=sepolia — a PASS here is testnet coherence only, NOT mainnet readiness)")
    else:
        print("BRIDGE MAINNET PREFLIGHT (read-only; checks config only — no RPC, no chain reads)")
    for check in checks:
        print(f"  {'PASS' if check.passed else 'FAIL'}  {check.name:<26} {check.detail}")

    failed = [c for c in checks if not c.passed]
    if failed:
        if args.profile == "sepolia":
            print(f"\n{len(failed)}/{len(checks)} knob(s) NOT acceptable for sepolia")
        else:
            print(f"\n{len(failed)}/{len(checks)} knob(s) NOT ready for mainnet")
        return 1
    if args.profile == "sepolia":
        print(f"\n{len(checks)}/{len(checks)} knobs acceptable for sepolia")
    else:
        print(f"\n{len(checks)}/{len(checks)} knobs ready for mainnet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
