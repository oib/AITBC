#!/usr/bin/env python3
"""
Test transaction import specifically
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

def test_transaction_import():
    """Test importing a block with a single transaction"""
    
    print("Testing Transaction Import")
    print("=" * 40)
    
    # Get current head
    response = requests.get(f"{BASE_URL}/head")
    head = response.json()
    print(f"Current head: height={head['height']}")
    
    # Create a new block with one transaction
    height = head["height"] + 1
    parent_hash = head["hash"]
    timestamp = "2026-01-29T10:20:00"
    block_hash = compute_block_hash(height, parent_hash, timestamp)
    
    test_block = {
        "height": height,
        "hash": block_hash,
        "parent_hash": parent_hash,
        "proposer": "test-proposer",
        "timestamp": timestamp,
        "tx_count": 1,
        "transactions": [{
            "tx_hash": "0xtx123456789",
            "sender": "0xsender123",
            "recipient": "0xreceiver456",
            "payload": {"to": "0xreceiver456", "amount": 1000000}
        }]
    }
    
    print(f"\nTest block data:")
    print(json.dumps(test_block, indent=2))
    
    # Import the block
    response = requests.post(
        f"{BASE_URL}/blocks/import",
        json=test_block
    )
    
    print(f"\nImport response:")
    print(f"  Status: {response.status_code}")
    print(f"  Body: {response.json()}")
    
    # Check logs
    print("\nChecking recent logs...")
    import subprocess
    result = subprocess.run(
        ["ssh", "aitbc-cascade", "journalctl -u blockchain-node --since '30 seconds ago' | grep 'Importing transaction' | tail -1"],
        capture_output=True,
        text=True
    )
    if result.stdout:
        print(f"Log: {result.stdout.strip()}")
    else:
        print("No transaction import logs found")

if __name__ == "__main__":
    test_transaction_import()
