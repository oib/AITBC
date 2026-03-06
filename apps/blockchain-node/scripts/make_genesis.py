#!/usr/bin/env python3
"""Generate a deterministic devnet genesis file for the blockchain node."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

DEFAULT_GENESIS = {
    "chain_id": "ait-devnet",
    "timestamp": None,  # populated at runtime
    "params": {
        "mint_per_unit": 1000,
        "coordinator_ratio": 0.05,
        "base_fee": 10,
        "fee_per_byte": 1,
    },
    "accounts": [
        {
            "address": "ait1faucet000000000000000000000000000000000",
            "balance": 1_000_000_000,
            "nonce": 0,
        }
    ],
    "authorities": [
        {
            "address": "ait1devproposer000000000000000000000000000000",
            "weight": 1,
        }
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate devnet genesis data")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/devnet/genesis.json"),
        help="Path to write the generated genesis file (default: data/devnet/genesis.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the genesis file if it already exists.",
    )
    parser.add_argument(
        "--faucet-address",
        default="ait1faucet000000000000000000000000000000000",
        help="Address seeded with devnet funds.",
    )
    parser.add_argument(
        "--faucet-balance",
        type=int,
        default=1_000_000_000,
        help="Faucet balance in smallest units.",
    )
    parser.add_argument(
        "--authorities",
        nargs="*",
        default=["ait1devproposer000000000000000000000000000000"],
        help="Authority addresses included in the genesis file.",
    )
    return parser.parse_args()


def build_genesis(args: argparse.Namespace) -> dict:
    genesis = json.loads(json.dumps(DEFAULT_GENESIS))  # deep copy via JSON
    genesis["timestamp"] = int(time.time())
    genesis["accounts"][0]["address"] = args.faucet_address
    genesis["accounts"][0]["balance"] = args.faucet_balance
    genesis["authorities"] = [
        {"address": address, "weight": 1}
        for address in args.authorities
    ]
    return genesis


def write_genesis(path: Path, data: dict, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"Genesis file already exists at {path}. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[genesis] wrote genesis file to {path}")


def main() -> None:
    args = parse_args()
    genesis = build_genesis(args)
    write_genesis(args.output, genesis, args.force)


if __name__ == "__main__":
    main()
