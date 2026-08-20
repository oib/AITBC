#!/usr/bin/env python3
"""Test importing a block with a single transaction on the local node."""

from __future__ import annotations

import json

import requests

from .conftest import DEFAULT_CHAIN_ID, DEFAULT_RPC_URL, make_signed_block


def test_transaction_import():
    """Build and import a block containing one signed transaction."""
    base = DEFAULT_RPC_URL
    chain_id = DEFAULT_CHAIN_ID

    head = requests.get(f"{base}/head", timeout=10).json()
    print(f"Current head: height={head['height']}")

    height = head["height"] + 1
    block = make_signed_block(
        chain_id=chain_id,
        height=height,
        parent_hash=head["hash"],
        transactions=[
            {
                "tx_hash": "0xtx123456789",
                "sender": "0xsender123",
                "recipient": "0xreceiver456",
                "payload": {"to": "0xreceiver456", "amount": 1000000},
            }
        ],
    )

    print("\nTest block data:")
    print(json.dumps(block, indent=2))

    response = requests.post(f"{base}/importBlock", json=block, timeout=10)

    print("\nImport response:")
    print(f"  Status: {response.status_code}")
    print(f"  Body: {response.text}")


if __name__ == "__main__":
    test_transaction_import()
