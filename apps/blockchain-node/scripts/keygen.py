#!/usr/bin/env python3
"""Generate a pseudo devnet key pair for blockchain components."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a devnet key pair")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the keypair JSON (prints to stdout if omitted)",
    )
    return parser.parse_args()


def generate_keypair() -> dict:
    private_key = secrets.token_hex(32)
    public_key = secrets.token_hex(32)
    address = "ait1" + secrets.token_hex(20)
    return {
        "private_key": private_key,
        "public_key": public_key,
        "address": address,
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
