#!/usr/bin/env python3
"""Create a new AITBC genesis.json from the available proposer key.

This is intended for hard-fork resets. It reads the hub's block-signing key
from /var/lib/aitbc/keystore/proposer.json, allocates the treasury to its
chain-style address, computes the state root and block hash, and writes a new
genesis.json file (preserving the old one as a timestamped .pre-reset copy).

Usage:
    PYTHONPATH=/opt/aitbc/apps/blockchain-node/src:/opt/aitbc \
        /opt/aitbc/venv/bin/python scripts/ops/create-genesis-block.py \
        --chain-id ait-hub.aitbc.bubuit.net \
        --out /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/genesis.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path


def _derive_ethereum_address(private_key: str) -> str:
    from aitbc.crypto.crypto import derive_ethereum_address as _derive

    return _derive(private_key).lower()


def _canonicalize(address: str) -> str:
    address = address.strip().lower()
    if address.startswith("0x"):
        return address
    if address.startswith("ait1"):
        return "0x" + address[4:]
    if address.startswith("aitbc1"):
        return "0x" + address[6:]
    return address


def _chain_style(address: str) -> str:
    return address.lower().replace("0x", "ait1")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new AITBC genesis.json")
    parser.add_argument(
        "--chain-id",
        default="ait-hub.aitbc.bubuit.net",
        help="Chain identifier for the new genesis",
    )
    parser.add_argument(
        "--keystore",
        default="/var/lib/aitbc/keystore/proposer.json",
        help="Path to the proposer keystore JSON file",
    )
    parser.add_argument(
        "--balance",
        type=int,
        default=3_600_000_000_000,
        help="Treasury balance in compute-seconds",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to write the new genesis.json",
    )
    parser.add_argument(
        "--update-env",
        action="store_true",
        help="Also update /etc/aitbc/blockchain.env and /etc/aitbc/node.env",
    )
    args = parser.parse_args()

    keystore_path = Path(args.keystore)
    if not keystore_path.exists():
        raise SystemExit(f"Keystore not found: {keystore_path}")

    with keystore_path.open() as f:
        proposer = json.load(f)

    private_key_hex = proposer.get("private_key", "")
    if private_key_hex.startswith("0x"):
        private_key_hex = private_key_hex[2:]

    derived_eth = _derive_ethereum_address(proposer["private_key"])
    if not re.fullmatch(r"0x[0-9a-f]{40}", derived_eth):
        raise SystemExit(f"Keystore does not contain a valid Ethereum private key: {args.keystore}")

    treasury_address = _chain_style(derived_eth)
    print(f"treasury address: {treasury_address}")
    print(f"proposer check  : {proposer.get('address')} -> {derived_eth}")
    if _canonicalize(proposer.get("address", "")) != derived_eth:
        print("WARNING: keystore 'address' field does not match derived address", file=os.sys.stderr)

    # Compute state root from the single allocation
    from aitbc_chain.base_models import Account
    from aitbc_chain.state.merkle_patricia_trie import StateManager

    account = Account(chain_id=args.chain_id, address=treasury_address, balance=args.balance, nonce=0)
    state_manager = StateManager()
    state_root = state_manager.compute_state_root({treasury_address: account})
    state_root_hex = "0x" + state_root.hex()

    # Compute genesis hash
    timestamp = datetime.now(UTC)
    payload = f"{args.chain_id}|0|0x00|{timestamp.isoformat()}|".encode()
    genesis_hash = "0x" + hashlib.sha256(payload).hexdigest()

    genesis = {
        "chain_id": args.chain_id,
        "block": {
            "height": 0,
            "hash": genesis_hash,
            "parent_hash": "0x00",
            "proposer": "genesis",
            "timestamp": timestamp.isoformat(),
            "tx_count": 0,
            "chain_id": args.chain_id,
            "state_root": state_root_hex,
            "metadata": {
                "chain_type": "mainnet",
                "purpose": "production",
                "consensus_algorithm": "poa",
            },
        },
        "allocations": [{"address": treasury_address, "balance": args.balance, "nonce": 0}],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        os.rename(out_path, f"{out_path}.pre-reset.{stamp}")
    with out_path.open("w") as f:
        json.dump(genesis, f, indent=2)

    print(f"new genesis hash: {genesis_hash}")
    print(f"new state_root  : {state_root_hex}")
    print(f"wrote           : {out_path}")

    if args.update_env:
        bc_path = Path("/etc/aitbc/blockchain.env")
        if bc_path.exists():
            bc_text = bc_path.read_text()
            bc_text = re.sub(r"^GENESIS_WALLET_ADDRESS=.*$", f"GENESIS_WALLET_ADDRESS={treasury_address}", bc_text, flags=re.M)
            bc_text = re.sub(r"^PROPOSER_ID=.*$", f"PROPOSER_ID={treasury_address}", bc_text, flags=re.M)
            bc_path.write_text(bc_text)
            print(f"updated {bc_path}")

        node_path = Path("/etc/aitbc/node.env")
        if node_path.exists():
            node_text = node_path.read_text()
            node_text = re.sub(r"^GENESIS_ADDRESS=.*$", f"GENESIS_ADDRESS={treasury_address}", node_text, flags=re.M)
            node_text = re.sub(r"^NODE_WALLET_ADDRESS=.*$", f"NODE_WALLET_ADDRESS={treasury_address}", node_text, flags=re.M)
            node_text = re.sub(r"^PROPOSER_ID=.*$", f"PROPOSER_ID={treasury_address}", node_text, flags=re.M)
            node_text = re.sub(
                r"^GENESIS_WALLET_PRIVATE_KEY=.*$", f"GENESIS_WALLET_PRIVATE_KEY={private_key_hex}", node_text, flags=re.M
            )
            node_path.write_text(node_text)
            print(f"updated {node_path}")

        wallet_path = Path("/var/lib/aitbc/wallets/genesis.json")
        wallet_path.parent.mkdir(parents=True, exist_ok=True)
        with wallet_path.open("w") as f:
            json.dump(
                {
                    "wallet_id": "genesis",
                    "address": treasury_address,
                    "private_key": private_key_hex,
                    "chain_id": args.chain_id,
                },
                f,
                indent=2,
            )
            print(f"updated {wallet_path}")


if __name__ == "__main__":
    main()
