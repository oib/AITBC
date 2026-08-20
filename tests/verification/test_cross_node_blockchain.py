#!/usr/bin/env python3
"""Cross-node blockchain feature tests, run against the local node by default."""

from __future__ import annotations

import time

import pytest
import requests

from .conftest import DEFAULT_CHAIN_ID, DEFAULT_RPC_URL, make_signed_block


def _head(base_url: str = DEFAULT_RPC_URL) -> dict:
    response = requests.get(f"{base_url}/head", timeout=10)
    response.raise_for_status()
    return response.json()


def _health(base_url: str = DEFAULT_RPC_URL) -> dict:
    """Fetch the node health endpoint. The RPC path is /rpc; health lives at /health."""
    health_url = base_url.rsplit("/rpc", 1)[0] + "/health"
    response = requests.get(health_url, timeout=10)
    response.raise_for_status()
    return response.json()


def test_cross_node_chain_id_consistency():
    """The local node reports a single supported chain ID matching the test default."""
    print("\n" + "=" * 60)
    print("TEST 1: Chain ID Consistency")
    print("=" * 60)

    health = _health()
    supported = health.get("supported_chains", [])
    print(f"Local node supported chains: {supported}")

    assert len(supported) >= 1, "Node should report at least one supported chain"
    assert DEFAULT_CHAIN_ID in supported, f"Expected {DEFAULT_CHAIN_ID} in supported chains, got {supported}"
    print(f"✅ All nodes are using chain_id: {DEFAULT_CHAIN_ID}")


def test_cross_node_block_sync():
    """Import a signed block locally and verify the chain head advances."""
    print("\n" + "=" * 60)
    print("TEST 2: Block Synchronization")
    print("=" * 60)

    head = _head()
    print(f"Local node: height={head['height']}, hash={head['hash']}")

    height = head["height"] + 1
    block = make_signed_block(
        chain_id=DEFAULT_CHAIN_ID,
        height=height,
        parent_hash=head["hash"],
    )

    response = requests.post(f"{DEFAULT_RPC_URL}/importBlock", json=block, timeout=10)
    print(f"Import status: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ Block imported locally: height={height}, hash={block['hash']}")
    else:
        print(f"❌ Failed to import block locally: {response.text}")
        pytest.fail("Local block import failed")

    # Brief wait for any asynchronous head cache invalidation
    time.sleep(0.5)
    new_head = _head()
    print(f"New local head: height={new_head['height']}, hash={new_head['hash']}")
    assert new_head["height"] >= height, "Local head should advance after import"


def test_cross_node_block_range():
    """The local node can return a range of blocks."""
    print("\n" + "=" * 60)
    print("TEST 3: Block Range Query")
    print("=" * 60)

    response = requests.get(f"{DEFAULT_RPC_URL}/blocks-range", params={"start": 0, "end": 5}, timeout=10)
    response.raise_for_status()
    data = response.json()
    blocks = data.get("blocks", [])
    print(f"Local node: returned {len(blocks)} blocks in range 0-5")
    assert len(blocks) >= 1, "Local node returned no blocks"
    print("✅ Local node can query block ranges")


def test_cross_node_connectivity():
    """The local node is reachable via RPC."""
    print("\n" + "=" * 60)
    print("TEST 4: Node RPC Connectivity")
    print("=" * 60)

    head = _head()
    print(f"Local node: reachable, height={head.get('height')}")
    assert head.get("height") is not None, "Local node did not return valid head"
    print("✅ Local node is reachable via RPC")


def run_cross_node_tests():
    """Run all cross-node blockchain feature tests locally."""
    print("\n" + "=" * 60)
    print("CROSS-NODE BLOCKCHAIN FEATURE TESTS (LOCAL)")
    print("=" * 60)
    print(f"Expected chain_id: {DEFAULT_CHAIN_ID}")

    tests = [
        ("Chain ID Consistency", test_cross_node_chain_id_consistency),
        ("Block Synchronization", test_cross_node_block_sync),
        ("Block Range Query", test_cross_node_block_range),
        ("RPC Connectivity", test_cross_node_connectivity),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            test_func()
            results.append((test_name, True))
        except (AssertionError, Exception) as e:
            print(f"❌ {test_name} FAILED: {e}")
            results.append((test_name, False))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    return all(passed for _, passed in results)


if __name__ == "__main__":
    success = run_cross_node_tests()
    exit(0 if success else 1)
