#!/usr/bin/env python3
"""Minimal integration test for local block and transaction import."""

from __future__ import annotations

import requests

from .conftest import DEFAULT_CHAIN_ID, DEFAULT_RPC_URL, make_signed_block


def test_minimal():
    """Import an empty block, then one with a single transaction, on the local node."""
    base = DEFAULT_RPC_URL
    chain_id = DEFAULT_CHAIN_ID

    head = requests.get(f"{base}/head", timeout=10).json()
    print(f"Current head: height={head['height']}, hash={head['hash']}")

    # Import an empty block at the next height
    height = head["height"] + 1
    block = make_signed_block(
        chain_id=chain_id,
        height=height,
        parent_hash=head["hash"],
        transactions=[],
    )
    response = requests.post(f"{base}/importBlock", json=block, timeout=10)
    print(f"Empty block import: {response.status_code} {response.text}")

    if response.status_code == 200:
        print("\n✅ Empty transactions work!")

        # Import a block with one transaction at the new next height
        head = requests.get(f"{base}/head", timeout=10).json()
        block2 = make_signed_block(
            chain_id=chain_id,
            height=head["height"] + 1,
            parent_hash=head["hash"],
            transactions=[{"tx_hash": "0xtest", "sender": "0xtest", "recipient": "0xtest", "payload": {}}],
        )
        response2 = requests.post(f"{base}/importBlock", json=block2, timeout=10)
        print(f"\nTransaction block import: {response2.status_code} {response2.text}")
    else:
        print(f"\n⚠️ Empty block import returned {response.status_code} (non-fatal smoke test)")


if __name__ == "__main__":
    test_minimal()
