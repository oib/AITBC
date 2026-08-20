#!/usr/bin/env python3
"""Minimal integration test for local block and transaction import."""

from __future__ import annotations

import requests

from .conftest import (
    make_signed_block,
    unique_address,
    unique_tx_hash,
)


def test_minimal(local_node, test_id):
    """Import an empty block, then one with a single transaction, on the local node."""
    base = local_node["url"]
    chain_id = local_node["chain_id"]
    prefix = test_id

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
    assert response.status_code == 200, f"Empty block should be accepted, got {response.status_code}"
    assert response.json()["success"] is True, "Empty block import should report success"
    print("\n✅ Empty transactions work!")

    # Import a block with one transaction at the new next height
    head = requests.get(f"{base}/head", timeout=10).json()
    height2 = head["height"] + 1
    block2 = make_signed_block(
        chain_id=chain_id,
        height=height2,
        parent_hash=head["hash"],
        transactions=[
            {
                "tx_hash": unique_tx_hash(f"{prefix}.tx1.{height2}"),
                "from": unique_address(f"{prefix}.from"),
                "to": unique_address(f"{prefix}.to"),
                "amount": 0,
                "fee": 0,
                "nonce": 0,
                "chain_id": chain_id,
                "signature": "",
                "payload": {},
            }
        ],
    )
    response2 = requests.post(f"{base}/importBlock", json=block2, timeout=10)
    print(f"\nTransaction block import: {response2.status_code} {response2.text}")
    assert response2.status_code == 200, f"Block with transaction should be accepted, got {response2.status_code}"
    assert response2.json()["success"] is True, "Block with transaction should report success"
    print("✅ Transaction block accepted")

    # Verify the transaction can be retrieved
    tx_url = f"{base}/transaction/{block2['transactions'][0]['tx_hash']}"
    tx_response = requests.get(tx_url, timeout=10)
    assert tx_response.status_code == 200, f"Transaction should be queryable, got {tx_response.status_code}"
    tx_data = tx_response.json()
    assert tx_data["tx_hash"] == block2["transactions"][0]["tx_hash"], "Transaction hash should match"
    assert tx_data["block_height"] == block2["height"], "Transaction should be recorded at the imported height"
    print("✅ Transaction recorded on-chain")


if __name__ == "__main__":
    test_minimal()
