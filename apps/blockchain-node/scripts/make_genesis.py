#!/usr/bin/env python3
"""Generate a production-ready genesis file with fixed allocations.

This replaces the old devnet faucet model. Genesis now defines a fixed
initial coin supply allocated to specific addresses. No admin minting
is allowed; the total supply is immutable after genesis.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List, Dict, Any

# Chain parameters - these are on-chain economic settings
CHAIN_PARAMS = {
    "mint_per_unit": 0,  # No new minting after genesis
    "coordinator_ratio": 0.05,
    "base_fee": 10,
    "fee_per_byte": 1,
}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate production genesis data")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/devnet/genesis.json"),
        help="Path to write the genesis file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing genesis file",
    )
    parser.add_argument(
        "--allocations",
        type=Path,
        required=True,
        help="JSON file mapping addresses to initial balances (smallest units)",
    )
    parser.add_argument(
        "--authorities",
        nargs="*",
        required=True,
        help="List of PoA authority addresses (proposer/validators)",
    )
    parser.add_argument(
        "--chain-id",
        default="ait-devnet",
        help="Chain ID (default: ait-devnet)",
    )
    return parser.parse_args()


def load_allocations(path: Path) -> List[Dict[str, Any]]:
    """Load address allocations from a JSON file.
    Expected format:
    [
      {"address": "ait1...", "balance": 1000000000, "nonce": 0}
    ]
    """
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("allocations must be a list of objects")
    # Validate required fields
    for item in data:
        if "address" not in item or "balance" not in item:
            raise ValueError(f"Allocation missing required fields: {item}")
    return data


def build_genesis(chain_id: str, allocations: List[Dict[str, Any]], authorities: List[str]) -> dict:
    """Construct the genesis block specification."""
    timestamp = int(time.time())
    return {
        "chain_id": chain_id,
        "timestamp": timestamp,
        "params": CHAIN_PARAMS.copy(),
        "allocations": allocations,  # Renamed from 'accounts' to avoid confusion
        "authorities": [
            {"address": addr, "weight": 1} for addr in authorities
        ],
    }


def write_genesis(path: Path, data: dict, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"Genesis file already exists at {path}. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[genesis] wrote genesis file to {path}")


def main() -> None:
    args = parse_args()
    allocations = load_allocations(args.allocations)
    genesis = build_genesis(args.chain_id, allocations, args.authorities)
    write_genesis(args.output, genesis, args.force)
    total = sum(a["balance"] for a in allocations)
    print(f"[genesis] Total supply: {total} (fixed, no future minting)")
    print("[genesis] IMPORTANT: Keep the private keys for these addresses secure!")


if __name__ == "__main__":
    main()
