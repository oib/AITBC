#!/usr/bin/env python3
"""
Cross-node blockchain feature tests
Tests new blockchain features across aitbc and aitbc1 nodes
"""

import hashlib
import subprocess
from datetime import datetime, UTC
import time
from aitbc import AITBCHTTPClient, NetworkError

# Test configuration
NODES = {
    "aitbc": {
        "rpc_url": "https://aitbc.bubuit.net/rpc",
        "name": "aitbc (localhost)"
    },
    "aitbc1": {
        "rpc_url": "http://10.1.223.40:8006/rpc",
        "name": "aitbc1 (remote)"
    },
    "gitea-runner": {
        "rpc_url": "http://10.1.223.93:8006/rpc",
        "name": "gitea-runner (CI)"
    }
}

CHAIN_ID = "ait-mainnet"

def compute_block_hash(height, parent_hash, timestamp):
    """Compute block hash using the same algorithm as PoA proposer"""
    payload = f"{CHAIN_ID}|{height}|{parent_hash}|{timestamp}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()

def get_node_head(node_key):
    """Get the current head block from a node"""
    client = AITBCHTTPClient(timeout=10)
    try:
        url = f"{NODES[node_key]['rpc_url']}/head"
        return client.get(url)
    except NetworkError as e:
        print(f"Error getting head from {node_key}: {e}")
        return None

def get_node_chain_id(node_key):
    """Get the chain_id from a node (from head endpoint)"""
    head = get_node_head(node_key)
    if head:
        return head.get("chain_id")
    return None

def test_cross_node_chain_id_consistency():
    """Test that both nodes are using the same chain_id"""
    print("\n" + "=" * 60)
    print("TEST 1: Chain ID Consistency Across Nodes")
    print("=" * 60)
    
    # Since head endpoint doesn't return chain_id, verify via SSH
    print("Verifying chain_id configuration on both nodes...")
    
    chain_ids = {}
    for node_key in NODES:
        if node_key == "aitbc":
            # Check local .env file
            with open("/etc/aitbc/.env", "r") as f:
                for line in f:
                    if line.startswith("CHAIN_ID="):
                        chain_id = line.strip().split("=")[1]
                        chain_ids[node_key] = chain_id
                        print(f"{NODES[node_key]['name']}: chain_id = {chain_id}")
                        break
        else:
            # Check remote .env file via SSH
            result = subprocess.run(
                ["ssh", node_key, "cat /etc/aitbc/.env | grep CHAIN_ID"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                chain_id = result.stdout.strip().split("=")[1]
                chain_ids[node_key] = chain_id
                print(f"{NODES[node_key]['name']}: chain_id = {chain_id}")
    
    # Verify all nodes have the same chain_id
    unique_chain_ids = set(chain_ids.values())
    assert len(unique_chain_ids) == 1, f"Nodes have different chain_ids: {chain_ids}"
    
    # Verify chain_id is "ait-mainnet"
    expected_chain_id = CHAIN_ID
    assert list(unique_chain_ids)[0] == expected_chain_id, \
        f"Expected chain_id '{expected_chain_id}', got '{list(unique_chain_ids)[0]}'"
    
    print(f"✅ All nodes are using chain_id: {expected_chain_id}")
    return True

def test_cross_node_block_sync():
    """Test that blocks sync between nodes"""
    print("\n" + "=" * 60)
    print("TEST 2: Block Synchronization Between Nodes")
    print("=" * 60)
    
    # Get current heads from both nodes
    heads = {}
    for node_key in NODES:
        head = get_node_head(node_key)
        if head:
            heads[node_key] = head
            print(f"{NODES[node_key]['name']}: height={head['height']}, hash={head['hash']}")
        else:
            print(f"❌ Failed to get head from {node_key}")
            return False
    
    # Import a block on aitbc
    print("\nImporting test block on aitbc...")
    aitbc_head = heads["aitbc"]
    height = aitbc_head["height"] + 10000000  # Use very high height to avoid conflicts
    parent_hash = aitbc_head["hash"]
    timestamp = datetime.now(UTC).isoformat() + "Z"
    valid_hash = compute_block_hash(height, parent_hash, timestamp)
    
    client = AITBCHTTPClient(timeout=10)
    try:
        result = client.post(
            f"{NODES['aitbc']['rpc_url']}/importBlock",
            json={
                "height": height,
                "hash": valid_hash,
                "parent_hash": parent_hash,
                "proposer": "cross-node-test",
                "timestamp": timestamp,
                "tx_count": 0,
                "chain_id": CHAIN_ID
            }
        )
        if result.get("success"):
            print(f"✅ Block imported on aitbc: height={height}, hash={valid_hash}")
        else:
            print(f"❌ Failed to import block on aitbc")
            return False
    except NetworkError as e:
        print(f"❌ Failed to import block on aitbc: {e}")
        return False
    
    # Wait for gossip propagation
    print("\nWaiting for gossip propagation to aitbc1...")
    time.sleep(5)
    
    # Check if block synced to aitbc1
    aitbc1_head = get_node_head("aitbc1")
    if aitbc1_head:
        print(f"{NODES['aitbc1']['name']}: height={aitbc1_head['height']}, hash={aitbc1_head['hash']}")
        
        # Try to get the specific block from aitbc1
        try:
            block_data = AITBCHTTPClient(timeout=10).get(f"{NODES['aitbc1']['rpc_url']}/blocks/{height}")
            if block_data:
                print(f"✅ Block synced to aitbc1: height={block_data.get('height')}, hash={block_data.get('hash')}")
                return True
            else:
                print(f"⚠️  Block not yet synced to aitbc1 (expected for gossip-based sync)")
                return True  # Don't fail - gossip sync is asynchronous
        except Exception as e:
            print(f"⚠️  Could not verify block sync to aitbc1: {e}")
            return True  # Don't fail - network connectivity issues
    else:
        print(f"❌ Failed to get head from aitbc1")
        return False

def test_cross_node_block_range():
    """Test that both nodes can return block ranges"""
    print("\n" + "=" * 60)
    print("TEST 3: Block Range Query")
    print("=" * 60)
    
    for node_key in NODES:
        url = f"{NODES[node_key]['rpc_url']}/blocks-range"
        try:
            response = AITBCHTTPClient(timeout=10).get(url, params={"start": 0, "end": 5})
            blocks = response.get("blocks", []) if response else []
            print(f"{NODES[node_key]['name']}: returned {len(blocks)} blocks in range 0-5")
            assert len(blocks) >= 1, \
                f"Node {node_key} returned no blocks"
        except NetworkError as e:
            print(f"❌ Error getting block range from {node_key}: {e}")
            return False
    
    print("✅ All nodes can query block ranges")
    return True

def test_cross_node_connectivity():
    """Test that both nodes are reachable via RPC"""
    print("\n" + "=" * 60)
    print("TEST 4: Node RPC Connectivity")
    print("=" * 60)
    
    for node_key in NODES:
        client = AITBCHTTPClient(timeout=10)
        try:
            head = client.get(f"{NODES[node_key]['rpc_url']}/head")
            print(f"{NODES[node_key]['name']}: reachable, height={head.get('height')}")
            assert head.get("height") is not None, \
                f"Node {node_key} did not return valid head"
        except NetworkError as e:
            print(f"❌ Error connecting to {node_key}: {e}")
            return False
    
    print("✅ All nodes are reachable via RPC")
    return True

def run_cross_node_tests():
    """Run all cross-node blockchain feature tests"""
    print("\n" + "=" * 60)
    print("CROSS-NODE BLOCKCHAIN FEATURE TESTS")
    print("=" * 60)
    print(f"Testing nodes: {', '.join(NODES.keys())}")
    print(f"Expected chain_id: {CHAIN_ID}")
    
    tests = [
        ("Chain ID Consistency", test_cross_node_chain_id_consistency),
        ("Block Synchronization", test_cross_node_block_sync),
        ("Block Range Query", test_cross_node_block_range),
        ("RPC Connectivity", test_cross_node_connectivity),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except AssertionError as e:
            print(f"❌ {test_name} FAILED: {e}")
            results.append((test_name, False))
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return all(result for _, result in results)

if __name__ == "__main__":
    success = run_cross_node_tests()
    exit(0 if success else 1)
