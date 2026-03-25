#!/usr/bin/env python3
"""
Simple test for block import endpoint without transactions
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

def test_simple_block_import():
    """Test importing a simple block without transactions"""
    
    print("Testing Simple Block Import")
    print("=" * 40)
    
    # Get current head
    response = requests.get(f"{BASE_URL}/head")
    head = response.json()
    print(f"Current head: height={head['height']}, hash={head['hash']}")
    
    # Create a new block
    height = head["height"] + 1
    parent_hash = head["hash"]
    timestamp = "2026-01-29T10:20:00"
    block_hash = compute_block_hash(height, parent_hash, timestamp)
    
    print(f"\nCreating test block:")
    print(f"  height: {height}")
    print(f"  parent_hash: {parent_hash}")
    print(f"  hash: {block_hash}")
    
    # Import the block
    response = requests.post(
        f"{BASE_URL}/blocks/import",
        json={
            "height": height,
            "hash": block_hash,
            "parent_hash": parent_hash,
            "proposer": "test-proposer",
            "timestamp": timestamp,
            "tx_count": 0
        }
    )
    
    print(f"\nImport response:")
    print(f"  Status: {response.status_code}")
    print(f"  Body: {response.json()}")
    
    if response.status_code == 200:
        print("\n✅ Block imported successfully!")
        
        # Verify the block was imported
        response = requests.get(f"{BASE_URL}/blocks/{height}")
        if response.status_code == 200:
            imported = response.json()
            print(f"\n✅ Verified imported block:")
            print(f"  height: {imported['height']}")
            print(f"  hash: {imported['hash']}")
            print(f"  proposer: {imported['proposer']}")
        else:
            print(f"\n❌ Could not retrieve imported block: {response.status_code}")
    else:
        print(f"\n❌ Import failed: {response.status_code}")

if __name__ == "__main__":
    test_simple_block_import()
