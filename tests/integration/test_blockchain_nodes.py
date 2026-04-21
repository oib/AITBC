#!/usr/bin/env python3
"""
Test script for AITBC blockchain nodes
Tests both nodes for functionality and consistency
"""

import httpx
import json
import time
import sys
from typing import Dict, Any, Optional

# Configuration
NODES = {
    "node1": {"url": "http://127.0.0.1:8082", "name": "Node 1"},
    "node2": {"url": "http://127.0.0.1:8081", "name": "Node 2"},
}

# Test addresses
TEST_ADDRESSES = {
    "alice": "aitbc1alice00000000000000000000000000000000000",
    "bob": "aitbc1bob0000000000000000000000000000000000000",
    "charlie": "aitbc1charl0000000000000000000000000000000000",
}

def print_header(message: str):
    """Print test header"""
    print(f"\n{'='*60}")
    print(f" {message}")
    print(f"{'='*60}")

def print_step(message: str):
    """Print test step"""
    print(f"\n→ {message}")

def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")

def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")

def print_warning(message: str):
    """Print warning message"""
    print(f"⚠️  {message}")

def check_node_health(node_name: str, node_config: Dict[str, str]) -> bool:
    """Check if node is responsive"""
    try:
        response = httpx.get(f"{node_config['url']}/openapi.json", timeout=5)
        if response.status_code == 200:
            print_success(f"{node_config['name']} is responsive")
            return True
        else:
            print_error(f"{node_config['name']} returned status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"{node_config['name']} is not responding: {e}")
        return False

def get_chain_head(node_name: str, node_config: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Get current chain head from node"""
    try:
        response = httpx.get(f"{node_config['url']}/rpc/head", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print_error(f"Failed to get chain head from {node_config['name']}: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Error getting chain head from {node_config['name']}: {e}")
        return None

def get_balance(node_name: str, node_config: Dict[str, str], address: str) -> Optional[int]:
    """Get balance for an address"""
    try:
        response = httpx.get(f"{node_config['url']}/rpc/getBalance/{address}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("balance", 0)
        else:
            print_error(f"Failed to get balance from {node_config['name']}: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Error getting balance from {node_config['name']}: {e}")
        return None

def mint_faucet(node_name: str, node_config: Dict[str, str], address: str, amount: int) -> bool:
    """Mint tokens to an address (devnet only)"""
    try:
        response = httpx.post(
            f"{node_config['url']}/rpc/admin/mintFaucet",
            json={"address": address, "amount": amount},
            timeout=5
        )
        if response.status_code == 200:
            print_success(f"Minted {amount} tokens to {address} on {node_config['name']}")
            return True
        else:
            print_error(f"Failed to mint on {node_config['name']}: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Error minting on {node_config['name']}: {e}")
        return False

def send_transaction(node_name: str, node_config: Dict[str, str], tx: Dict[str, Any]) -> Optional[str]:
    """Send a transaction"""
    try:
        response = httpx.post(
            f"{node_config['url']}/rpc/sendTx",
            json=tx,
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("tx_hash")
        else:
            print_error(f"Failed to send transaction on {node_config['name']}: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print_error(f"Error sending transaction on {node_config['name']}: {e}")
        return None

def wait_for_block(node_name: str, node_config: Dict[str, str], target_height: int, timeout: int = 30) -> bool:
    """Wait for node to reach a target block height"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        head = get_chain_head(node_name, node_config)
        if head and head.get("height", 0) >= target_height:
            return True
        time.sleep(1)
    return False

def test_node_connectivity():
    """Test if both nodes are running and responsive"""
    print_header("Testing Node Connectivity")
    
    all_healthy = True
    for node_name, node_config in NODES.items():
        if not check_node_health(node_name, node_config):
            all_healthy = False
    
    assert all_healthy, "Not all nodes are healthy"

def test_chain_consistency():
    """Test if both nodes have consistent chain heads"""
    print_header("Testing Chain Consistency")
    
    heads = {}
    for node_name, node_config in NODES.items():
        print_step(f"Getting chain head from {node_config['name']}")
        head = get_chain_head(node_name, node_config)
        if head:
            heads[node_name] = head
            print(f"  Height: {head.get('height', 'unknown')}")
            print(f"  Hash: {head.get('hash', 'unknown')[:16]}...")
        else:
            print_error(f"Failed to get chain head from {node_config['name']}")
    
    if len(heads) == len(NODES):
        # Compare heights
        heights = [head.get("height", 0) for head in heads.values()]
        if len(set(heights)) == 1:
            print_success("Both nodes have the same block height")
        else:
            print_error(f"Node heights differ: {heights}")
        
        # Compare hashes
        hashes = [head.get("hash", "") for head in heads.values()]
        if len(set(hashes)) == 1:
            print_success("Both nodes have the same chain hash")
        else:
            print_warning("Nodes have different chain hashes (may be syncing)")
    
    assert len(heads) == len(NODES), "Failed to get chain heads from all nodes"

def test_faucet_and_balances():
    """Test faucet minting and balance queries"""
    print_header("Testing Faucet and Balances")
    
    # Test on node1
    print_step("Testing faucet on Node 1")
    if mint_faucet("node1", NODES["node1"], TEST_ADDRESSES["alice"], 1000):
        time.sleep(2)  # Wait for block
        
        # Check balance on both nodes
        for node_name, node_config in NODES.items():
            balance = get_balance(node_name, node_config, TEST_ADDRESSES["alice"])
            if balance is not None:
                print(f"  {node_config['name']} balance for alice: {balance}")
                if balance >= 1000:
                    print_success(f"Balance correct on {node_config['name']}")
                else:
                    print_error(f"Balance incorrect on {node_config['name']}")
            else:
                print_error(f"Failed to get balance from {node_config['name']}")
    
    # Test on node2
    print_step("Testing faucet on Node 2")
    if mint_faucet("node2", NODES["node2"], TEST_ADDRESSES["bob"], 500):
        time.sleep(2)  # Wait for block
        
        # Check balance on both nodes
        for node_name, node_config in NODES.items():
            balance = get_balance(node_name, node_config, TEST_ADDRESSES["bob"])
            if balance is not None:
                print(f"  {node_config['name']} balance for bob: {balance}")
                if balance >= 500:
                    print_success(f"Balance correct on {node_config['name']}")
                else:
                    print_error(f"Balance incorrect on {node_config['name']}")
            else:
                print_error(f"Failed to get balance from {node_config['name']}")

def test_transaction_submission():
    """Test transaction submission between addresses"""
    print_header("Testing Transaction Submission")
    
    # First ensure alice has funds
    print_step("Ensuring alice has funds")
    mint_faucet("node1", NODES["node1"], TEST_ADDRESSES["alice"], 2000)
    time.sleep(2)
    
    # Create a transfer transaction (simplified - normally needs proper signing)
    print_step("Submitting transfer transaction")
    tx = {
        "type": "TRANSFER",
        "sender": TEST_ADDRESSES["alice"],
        "nonce": 0,
        "fee": 10,
        "payload": {
            "to": TEST_ADDRESSES["bob"],
            "amount": 100
        },
        "sig": None  # In devnet, signature might be optional
    }
    
    tx_hash = send_transaction("node1", NODES["node1"], tx)
    if tx_hash:
        print_success(f"Transaction submitted: {tx_hash[:16]}...")
        time.sleep(3)  # Wait for inclusion
        
        # Check final balances
        print_step("Checking final balances")
        for node_name, node_config in NODES.items():
            alice_balance = get_balance(node_name, node_config, TEST_ADDRESSES["alice"])
            bob_balance = get_balance(node_name, node_config, TEST_ADDRESSES["bob"])
            
            if alice_balance is not None and bob_balance is not None:
                print(f"  {node_config['name']}: alice={alice_balance}, bob={bob_balance}")
    else:
        print_error("Failed to submit transaction")

def test_block_production():
    """Test that nodes are producing blocks"""
    print_header("Testing Block Production")
    
    initial_heights = {}
    for node_name, node_config in NODES.items():
        head = get_chain_head(node_name, node_config)
        if head:
            initial_heights[node_name] = head.get("height", 0)
            print(f"  {node_config['name']} initial height: {initial_heights[node_name]}")
    
    print_step("Waiting for new blocks...")
    time.sleep(10)  # Wait for block production (2s block time)
    
    final_heights = {}
    for node_name, node_config in NODES.items():
        head = get_chain_head(node_name, node_config)
        if head:
            final_heights[node_name] = head.get("height", 0)
            print(f"  {node_config['name']} final height: {final_heights[node_name]}")
    
    # Check if blocks were produced
    for node_name in NODES:
        if node_name in initial_heights and node_name in final_heights:
            produced = final_heights[node_name] - initial_heights[node_name]
            if produced > 0:
                print_success(f"{NODES[node_name]['name']} produced {produced} block(s)")
            else:
                print_error(f"{NODES[node_name]['name']} produced no blocks")

def main():
    """Run all tests"""
    print_header("AITBC Blockchain Node Test Suite")
    
    tests = [
        ("Node Connectivity", test_node_connectivity),
        ("Chain Consistency", test_chain_consistency),
        ("Faucet and Balances", test_faucet_and_balances),
        ("Transaction Submission", test_transaction_submission),
        ("Block Production", test_block_production),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print_error(f"Test '{test_name}' failed with exception: {e}")
            results[test_name] = False
    
    # Summary
    print_header("Test Summary")
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:.<40} {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print_success("All tests passed! 🎉")
        return 0
    else:
        print_error("Some tests failed. Check the logs above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
