#!/usr/bin/env python3
"""Generate a production-ready genesis file with fixed allocations.

This replaces the old devnet faucet model. Genesis now defines a fixed
initial coin supply allocated to specific addresses. No admin minting
is allowed; the total supply is immutable after genesis.

v0.6.4: Multi-genesis support. Use --island-id and --chains to generate
genesis files for multiple chains on an island in a single invocation.
Each chain gets its own genesis file under <output_dir>/<chain_id>/genesis.json.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

# Chain parameters - these are on-chain economic settings
CHAIN_PARAMS = {
    "mint_per_unit": 0,  # No new minting after genesis
    "coordinator_ratio": 0.05,
    "base_fee": 36,
    "fee_per_byte": 1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate production genesis data")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/devnet/genesis.json"),
        help="Path to write the genesis file (or output directory when --chains is used)",
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
        help="Chain ID (default: ait-devnet). Ignored when --chains is used.",
    )
    # v0.6.4: Multi-genesis support
    parser.add_argument(
        "--island-id",
        default=None,
        help="Island ID to include in genesis metadata (v0.6.4). When set, genesis files include an 'island_id' field.",
    )
    parser.add_argument(
        "--chains",
        default=None,
        help="Comma-separated list of chain IDs to generate genesis for (v0.6.4). "
        "When set, --output is treated as a directory and a genesis file is "
        "written per chain at <output>/<chain_id>/genesis.json. "
        "All chains share the same allocations and authorities.",
    )
    return parser.parse_args()


def load_allocations(path: Path) -> list[dict[str, Any]]:
    """Load address allocations from a JSON file.
    Expected format:
    [
      {"address": "0x...", "balance": 1000000000, "nonce": 0}
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


def build_genesis(
    chain_id: str,
    allocations: list[dict[str, Any]],
    authorities: list[str],
    island_id: str | None = None,
) -> dict:
    """Construct the genesis block specification."""
    timestamp = int(time.time())
    genesis: dict[str, Any] = {
        "chain_id": chain_id,
        "timestamp": timestamp,
        "params": CHAIN_PARAMS.copy(),
        "allocations": allocations,  # Renamed from 'accounts' to avoid confusion
        "authorities": [{"address": addr, "weight": 1} for addr in authorities],
    }
    if island_id:
        genesis["island_id"] = island_id
    return genesis


def write_genesis(path: Path, data: dict, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"Genesis file already exists at {path}. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[genesis] wrote genesis file to {path}")


def main() -> None:
    args = parse_args()
    allocations = load_allocations(args.allocations)

    if args.chains:
        # Multi-genesis mode: generate one genesis per chain
        chain_ids = [c.strip() for c in args.chains.split(",") if c.strip()]
        if not chain_ids:
            raise SystemExit("--chains specified but no valid chain IDs found")
        output_dir = args.output
        if output_dir.suffix == ".json":
            # User gave a file path, not a directory — use parent
            output_dir = output_dir.parent
        print(f"[genesis] Multi-genesis mode: generating {len(chain_ids)} chain(s) in {output_dir}")
        for chain_id in chain_ids:
            genesis = build_genesis(chain_id, allocations, args.authorities, island_id=args.island_id)
            genesis_path = output_dir / chain_id / "genesis.json"
            write_genesis(genesis_path, genesis, args.force)
        total = sum(a["balance"] for a in allocations)
        print(f"[genesis] Total supply per chain: {total} (fixed, no future minting)")
        if args.island_id:
            print(f"[genesis] Island: {args.island_id}")
        print(f"[genesis] Generated {len(chain_ids)} genesis files for chains: {', '.join(chain_ids)}")
    else:
        # Single-genesis mode (backward compat)
        genesis = build_genesis(args.chain_id, allocations, args.authorities, island_id=args.island_id)
        write_genesis(args.output, genesis, args.force)
        total = sum(a["balance"] for a in allocations)
        print(f"[genesis] Total supply: {total} (fixed, no future minting)")
        if args.island_id:
            print(f"[genesis] Island: {args.island_id}")

    print("[genesis] IMPORTANT: Keep the private keys for these addresses secure!")


if __name__ == "__main__":
    main()
