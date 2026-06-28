#!/usr/bin/env python3
"""Generate a devnet key pair for blockchain components.

Uses secp256k1 (Ethereum-style) key generation with 0x-prefixed checksum
addresses, compatible with the blockchain node's transaction verifier.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eth_account import Account
from eth_keys import keys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a devnet key pair")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the keypair JSON (prints to stdout if omitted)",
    )
    return parser.parse_args()


def generate_keypair() -> dict:
    account = Account.create()
    return {
        "private_key": account.key.hex(),
        "public_key": keys.PrivateKey(bytes(account.key)).public_key.to_hex(),
        "address": account.address,
    }


def main() -> None:
    args = parse_args()
    keypair = generate_keypair()
    payload = json.dumps(keypair, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"[keygen] wrote keypair to {args.output}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
