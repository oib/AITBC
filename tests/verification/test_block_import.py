#!/usr/bin/env python3
"""Integration test for the local /rpc/importBlock endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

import requests

from .conftest import (
    compute_block_hash,
    make_signed_block,
    sign_block,
)


def test_block_import(local_node):
    """Exercise import validation, acceptance, duplicate and conflict handling locally."""
    base = local_node["url"]
    chain_id = local_node["chain_id"]

    print("Testing Block Import Endpoint")
    print("=" * 50)

    head = requests.get(f"{base}/head", timeout=10).json()
    print(f"Current head: height={head['height']}, hash={head['hash']}")

    # Work at the next height so the node accepts the block immediately
    height = head["height"] + 1
    parent_hash = head["hash"]
    timestamp = datetime.now(UTC).isoformat()
    block = make_signed_block(
        chain_id=chain_id,
        height=height,
        parent_hash=parent_hash,
        timestamp=timestamp,
    )

    print("\n1. Testing valid block import...")
    response = requests.post(f"{base}/importBlock", json=block, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    assert response.status_code == 200, "Should accept valid block"
    assert response.json()["success"] is True, "Should return success=True"
    print("✓ Successfully imported valid block")

    print("\n2. Testing import of existing block...")
    response = requests.post(f"{base}/importBlock", json=block, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    # The API might return 200 with success=True for existing blocks, or 409 for conflict
    assert response.status_code in [200, 409], "Should accept existing block or return conflict"
    print("✓ Correctly handled existing block")

    print("\n3. Testing block conflict...")
    other_timestamp = "2026-01-29T10:20:01"
    other_hash = compute_block_hash(chain_id, height, parent_hash, other_timestamp)
    conflict_block = {
        "height": height,
        "hash": other_hash,
        "parent_hash": parent_hash,
        "timestamp": other_timestamp,
        "tx_count": 0,
        "chain_id": chain_id,
        "transactions": [],
    }
    sign_block(conflict_block)
    response = requests.post(f"{base}/importBlock", json=conflict_block, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    assert response.status_code == 409, "Should return conflict for existing height with different hash"
    print("✓ Correctly detected block conflict")

    print("\n4. Testing invalid block hash...")
    response = requests.post(
        f"{base}/importBlock",
        json={
            "height": height + 1,
            "hash": "0xinvalid",
            "parent_hash": parent_hash,
            "proposer": block["proposer"],
            "timestamp": timestamp,
            "tx_count": 0,
            "chain_id": chain_id,
        },
        timeout=10,
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    assert response.status_code == 400, "Should reject invalid hash"
    assert "Invalid block hash" in response.json()["detail"], f"Should mention invalid hash, got: {response.json()}"
    print("✓ Correctly rejected invalid hash")

    print("\n5. Testing parent not found...")
    missing_parent = "0x" + "9" * 64
    no_parent_block = make_signed_block(
        chain_id=chain_id,
        height=height + 1,
        parent_hash=missing_parent,
        timestamp="2026-01-29T10:20:00",
    )
    response = requests.post(f"{base}/importBlock", json=no_parent_block, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    assert response.status_code == 400, "Should reject when parent not found"
    assert "Block rejected" in response.json()["detail"], "Should report block rejection"
    print("✓ Correctly rejected missing parent")

    print("\n" + "=" * 50)
    print("All tests passed! ✅")
    print("\nBlock import endpoint is fully functional with:")
    print("- ✓ Valid block import")
    print("- ✓ Duplicate block handling")
    print("- ✓ Conflict detection")
    print("- ✓ Hash validation")
    print("- ✓ Parent block verification")
    print("- ✓ Proper error handling")


if __name__ == "__main__":
    test_block_import()
