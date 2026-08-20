#!/usr/bin/env python3
"""Test importing a block with a single transaction on the local node."""

from __future__ import annotations

import json

import requests

from .conftest import (
    make_signed_block,
    unique_address,
    unique_tx_hash,
)


def test_transaction_import(local_node, test_id):
    """Build and import a block containing one deterministic transaction."""
    base = local_node["url"]
    chain_id = local_node["chain_id"]
    prefix = test_id

    head = requests.get(f"{base}/head", timeout=10).json()
    print(f"Current head: height={head['height']}")

    height = head["height"] + 1
    tx = {
        "tx_hash": unique_tx_hash(f"{prefix}.tx1.{height}"),
        "from": unique_address(f"{prefix}.from"),
        "to": unique_address(f"{prefix}.to"),
        "amount": 0,
        "fee": 0,
        "nonce": 0,
        "chain_id": chain_id,
        "signature": "",
        "payload": {"note": "test transaction"},
    }
    block = make_signed_block(
        chain_id=chain_id,
        height=height,
        parent_hash=head["hash"],
        transactions=[tx],
    )

    print("\nTest block data:")
    print(json.dumps(block, indent=2))

    response = requests.post(f"{base}/importBlock", json=block, timeout=10)

    print("\nImport response:")
    print(f"  Status: {response.status_code}")
    print(f"  Body: {response.text}")

    assert response.status_code == 200, f"Block with transaction should be accepted, got {response.status_code}"
    assert response.json()["success"] is True, "Block import should report success"
    print("✅ Block with transaction accepted")

    # Verify the transaction is retrievable by hash
    tx_response = requests.get(f"{base}/transaction/{tx['tx_hash']}", timeout=10)
    assert tx_response.status_code == 200, f"Transaction should be queryable, got {tx_response.status_code}"
    tx_data = tx_response.json()
    assert tx_data["tx_hash"] == tx["tx_hash"], "Transaction hash should match"
    assert tx_data["block_height"] == height, "Transaction should be recorded at the imported height"
    print("✅ Transaction recorded and queryable on-chain")


if __name__ == "__main__":
    test_transaction_import()
