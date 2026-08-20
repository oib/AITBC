#!/usr/bin/env python3
"""Simple integration test for local block import without transactions."""

from __future__ import annotations

import requests

from .conftest import make_signed_block


def test_simple_block_import(local_node):
    """Import a simple, signed block on the local node and verify it can be fetched."""
    base = local_node["url"]
    chain_id = local_node["chain_id"]

    head = requests.get(f"{base}/head", timeout=10).json()
    print(f"Current head: height={head['height']}, hash={head['hash']}")

    height = head["height"] + 1
    block = make_signed_block(
        chain_id=chain_id,
        height=height,
        parent_hash=head["hash"],
    )

    print("\nCreating test block:")
    print(f"  height: {block['height']}")
    print(f"  parent_hash: {block['parent_hash']}")
    print(f"  hash: {block['hash']}")

    response = requests.post(f"{base}/importBlock", json=block, timeout=10)

    print("\nImport response:")
    print(f"  Status: {response.status_code}")
    print(f"  Body: {response.text}")

    assert response.status_code == 200, f"Block import should be accepted, got {response.status_code}"
    assert response.json()["success"] is True, "Block import should report success"
    print("\n✅ Block imported successfully!")

    verify = requests.get(f"{base}/blocks/{height}", timeout=10)
    assert verify.status_code == 200, f"Imported block should be retrievable, got {verify.status_code}"
    imported = verify.json()
    assert imported["height"] == height, "Retrieved height should match"
    assert imported["hash"] == block["hash"], "Retrieved hash should match the imported block"
    assert imported["proposer"] == block["proposer"], "Retrieved proposer should match"
    print("\n✅ Verified imported block:")
    print(f"  height: {imported['height']}")
    print(f"  hash: {imported['hash']}")
    print(f"  proposer: {imported.get('proposer')}")


if __name__ == "__main__":
    test_simple_block_import()
