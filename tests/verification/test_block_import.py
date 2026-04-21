#!/usr/bin/env python3
"""
Test script for block import endpoint
Tests the /rpc/blocks/import POST endpoint functionality
"""

import json
import hashlib
from datetime import datetime

# Test configuration
BASE_URL = "https://aitbc.bubuit.net/rpc"
CHAIN_ID = "ait-devnet"

def compute_block_hash(height, parent_hash, timestamp):
    """Compute block hash using the same algorithm as PoA proposer"""
    payload = f"{CHAIN_ID}|{height}|{parent_hash}|{timestamp}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()

def test_block_import():
    """Test the block import endpoint with various scenarios"""
    import requests
    
    print("Testing Block Import Endpoint")
    print("=" * 50)
    
    # Test 1: Invalid height (0)
    print("\n1. Testing invalid height (0)...")
    response = requests.post(
        f"{BASE_URL}/blocks/import",
        json={
            "height": 0,
            "hash": "0x123",
            "parent_hash": "0x00",
            "proposer": "test",
            "timestamp": "2026-01-29T10:20:00",
            "tx_count": 0
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 422, "Should return validation error for height 0"
    print("✓ Correctly rejected height 0")
    
    # Test 2: Block already exists with different hash
    print("\n2. Testing block conflict...")
    response = requests.post(
        f"{BASE_URL}/blocks/import",
        json={
            "height": 1,
            "hash": "0xinvalidhash",
            "parent_hash": "0x00",
            "proposer": "test",
            "timestamp": "2026-01-29T10:20:00",
            "tx_count": 0
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 409, "Should return conflict for existing height with different hash"
    print("✓ Correctly detected block conflict")
    
    # Test 3: Import existing block with correct hash
    print("\n3. Testing import of existing block with correct hash...")
    # Get actual block data
    response = requests.get(f"{BASE_URL}/blocks/1")
    block_data = response.json()
    
    response = requests.post(
        f"{BASE_URL}/blocks/import",
        json={
            "height": block_data["height"],
            "hash": block_data["hash"],
            "parent_hash": block_data["parent_hash"],
            "proposer": block_data["proposer"],
            "timestamp": block_data["timestamp"],
            "tx_count": block_data["tx_count"]
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200, "Should accept existing block with correct hash"
    assert response.json()["status"] == "exists", "Should return 'exists' status"
    print("✓ Correctly handled existing block")
    
    # Test 4: Invalid block hash (with valid parent)
    print("\n4. Testing invalid block hash...")
    # Get current head to use as parent
    response = requests.get(f"{BASE_URL}/head")
    head = response.json()
    
    timestamp = "2026-01-29T10:20:00"
    parent_hash = head["hash"]  # Use actual parent hash
    height = head["height"] + 1000  # Use high height to avoid conflicts
    invalid_hash = "0xinvalid"
    
    response = requests.post(
        f"{BASE_URL}/blocks/import",
        json={
            "height": height,
            "hash": invalid_hash,
            "parent_hash": parent_hash,
            "proposer": "test",
            "timestamp": timestamp,
            "tx_count": 0
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 400, "Should reject invalid hash"
    assert "Invalid block hash" in response.json()["detail"], "Should mention invalid hash"
    print("✓ Correctly rejected invalid hash")
    
    # Test 5: Valid hash but parent not found
    print("\n5. Testing valid hash but parent not found...")
    height = head["height"] + 2000  # Use different height
    parent_hash = "0xnonexistentparent"
    timestamp = "2026-01-29T10:20:00"
    valid_hash = compute_block_hash(height, parent_hash, timestamp)
    
    response = requests.post(
        f"{BASE_URL}/blocks/import",
        json={
            "height": height,
            "hash": valid_hash,
            "parent_hash": parent_hash,
            "proposer": "test",
            "timestamp": timestamp,
            "tx_count": 0
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 400, "Should reject when parent not found"
    assert "Parent block not found" in response.json()["detail"], "Should mention parent not found"
    print("✓ Correctly rejected missing parent")
    
    # Test 6: Valid block with transactions and receipts
    print("\n6. Testing valid block with transactions...")
    # Get current head to use as parent
    response = requests.get(f"{BASE_URL}/head")
    head = response.json()
    
    height = head["height"] + 1
    parent_hash = head["hash"]
    timestamp = datetime.utcnow().isoformat() + "Z"
    valid_hash = compute_block_hash(height, parent_hash, timestamp)
    
    test_block = {
        "height": height,
        "hash": valid_hash,
        "parent_hash": parent_hash,
        "proposer": "test-proposer",
        "timestamp": timestamp,
        "tx_count": 1,
        "transactions": [{
            "tx_hash": f"0xtx{height}",
            "sender": "0xsender",
            "recipient": "0xreceiver",
            "payload": {"to": "0xreceiver", "amount": 1000000}
        }],
        "receipts": [{
            "receipt_id": f"rx{height}",
            "job_id": f"job{height}",
            "payload": {"result": "success"},
            "miner_signature": "0xminer",
            "coordinator_attestations": ["0xatt1"],
            "minted_amount": 100,
            "recorded_at": timestamp
        }]
    }
    
    response = requests.post(
        f"{BASE_URL}/blocks/import",
        json=test_block
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200, "Should accept valid block with transactions"
    assert response.json()["status"] == "imported", "Should return 'imported' status"
    print("✓ Successfully imported block with transactions")
    
    # Verify the block was imported
    print("\n7. Verifying imported block...")
    response = requests.get(f"{BASE_URL}/blocks/{height}")
    assert response.status_code == 200, "Should be able to retrieve imported block"
    imported_block = response.json()
    assert imported_block["hash"] == valid_hash, "Hash should match"
    assert imported_block["tx_count"] == 1, "Should have 1 transaction"
    print("✓ Block successfully imported and retrievable")
    
    print("\n" + "=" * 50)
    print("All tests passed! ✅")
    print("\nBlock import endpoint is fully functional with:")
    print("- ✓ Input validation")
    print("- ✓ Hash validation")
    print("- ✓ Parent block verification")
    print("- ✓ Conflict detection")
    print("- ✓ Transaction and receipt import")
    print("- ✓ Proper error handling")

if __name__ == "__main__":
    test_block_import()
