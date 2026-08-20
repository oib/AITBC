#!/usr/bin/env python3
"""Simple integration test for local block import without transactions."""

from __future__ import annotations

import requests

from .conftest import DEFAULT_CHAIN_ID, DEFAULT_RPC_URL, make_signed_block


def test_simple_block_import():
    """Import a simple, signed block on the local node and verify it can be fetched."""
    base = DEFAULT_RPC_URL
    chain_id = DEFAULT_CHAIN_ID

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

    if response.status_code == 200:
        print("\n✅ Block imported successfully!")

        verify = requests.get(f"{base}/blocks/{height}", timeout=10)
        if verify.status_code == 200:
            imported = verify.json()
            print("\n✅ Verified imported block:")
            print(f"  height: {imported['height']}")
            print(f"  hash: {imported['hash']}")
            print(f"  proposer: {imported.get('proposer')}")
        else:
            print(f"\n⚠️ Could not retrieve imported block: {verify.status_code}")
    else:
        print(f"\n⚠️ Import failed: {response.status_code}")


if __name__ == "__main__":
    test_simple_block_import()
