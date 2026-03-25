#!/usr/bin/env python3
"""
Minimal test to debug transaction import
"""

import json
import hashlib
import requests

BASE_URL = "https://aitbc.bubuit.net/rpc"
CHAIN_ID = "ait-devnet"

def compute_block_hash(height, parent_hash, timestamp):
    """Compute block hash using the same algorithm as PoA proposer"""
    payload = f"{CHAIN_ID}|{height}|{parent_hash}|{timestamp}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()

def test_minimal():
    """Test with minimal data"""
    
    # Get current head
    response = requests.get(f"{BASE_URL}/head")
    head = response.json()
    
    # Create a new block
    height = head["height"] + 1
    parent_hash = head["hash"]
    timestamp = "2026-01-29T10:20:00"
    block_hash = compute_block_hash(height, parent_hash, timestamp)
    
    # Test with empty transactions list first
    test_block = {
        "height": height,
        "hash": block_hash,
        "parent_hash": parent_hash,
        "proposer": "test-proposer",
        "timestamp": timestamp,
        "tx_count": 0,
        "transactions": []
    }
    
    print("Testing with empty transactions list...")
    response = requests.post(f"{BASE_URL}/blocks/import", json=test_block)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        print("\n✅ Empty transactions work!")
        
        # Now test with one transaction
        height = height + 1
        block_hash = compute_block_hash(height, parent_hash, timestamp)
        
        test_block["height"] = height
        test_block["hash"] = block_hash
        test_block["tx_count"] = 1
        test_block["transactions"] = [{"tx_hash": "0xtest", "sender": "0xtest", "recipient": "0xtest", "payload": {}}]
        
        print("\nTesting with one transaction...")
        response = requests.post(f"{BASE_URL}/blocks/import", json=test_block)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

if __name__ == "__main__":
    test_minimal()
