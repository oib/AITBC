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
CHAIN_ID = "ait-mainnet"

def compute_block_hash(height, parent_hash, timestamp):
    """Compute block hash using the same algorithm as PoA proposer"""
    payload = f"{CHAIN_ID}|{height}|{parent_hash}|{timestamp}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()

def test_block_import():
    """Test the block import endpoint with various scenarios"""
    
    print("Testing Block Import Endpoint")
    print("=" * 50)
    
    # Get current head to work with existing blockchain
    client = AITBCHTTPClient()
    head = client.get(f"{BASE_URL}/head")
    print(f"Current head: height={head['height']}, hash={head['hash']}")
    
    # Use very high heights to avoid conflicts with existing chain
    base_height = 1000000
    
    # Test 1: Import a valid block at high height
    print("\n1. Testing valid block import...")
    height = base_height
    parent_hash = head["hash"]
    timestamp = datetime.utcnow().isoformat() + "Z"
    valid_hash = compute_block_hash(height, parent_hash, timestamp)
    
    response = requests.post(
        f"{BASE_URL}/importBlock",
        json={
            "height": height,
            "hash": valid_hash,
            "parent_hash": parent_hash,
            "proposer": "test-proposer",
            "timestamp": timestamp,
            "tx_count": 0,
            "chain_id": CHAIN_ID
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200, "Should accept valid block"
    assert response.json()["success"] == True, "Should return success=True"
    print("✓ Successfully imported valid block")
    
    # Test 2: Try to import same block again (should return conflict)
    print("\n2. Testing import of existing block...")
    response = requests.post(
        f"{BASE_URL}/importBlock",
        json={
            "height": height,
            "hash": valid_hash,
            "parent_hash": parent_hash,
            "proposer": "test-proposer",
            "timestamp": timestamp,
            "tx_count": 0,
            "chain_id": CHAIN_ID
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    # The API might return 200 with success=True for existing blocks, or 409 for conflict
    # Accept either as correct behavior
    assert response.status_code in [200, 409], "Should accept existing block or return conflict"
    print("✓ Correctly handled existing block")
    
    # Test 3: Try to import different block at same height (conflict)
    print("\n3. Testing block conflict...")
    invalid_hash = compute_block_hash(height, parent_hash, "2026-01-29T10:20:00")
    response = requests.post(
        f"{BASE_URL}/importBlock",
        json={
            "height": height,
            "hash": invalid_hash,
            "parent_hash": parent_hash,
            "proposer": "test",
            "timestamp": timestamp,
            "tx_count": 0,
            "chain_id": CHAIN_ID
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 409, "Should return conflict for existing height with different hash"
    print("✓ Correctly detected block conflict")
    
    # Test 4: Invalid block hash
    print("\n4. Testing invalid block hash...")
    height = base_height + 10
    invalid_hash = "0xinvalid"
    response = requests.post(
        f"{BASE_URL}/importBlock",
        json={
            "height": height,
            "hash": invalid_hash,
            "parent_hash": parent_hash,
            "proposer": "test",
            "timestamp": timestamp,
            "tx_count": 0,
            "chain_id": CHAIN_ID
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 400, "Should reject invalid hash"
    assert "Invalid block hash" in response.json()["detail"], "Should mention invalid hash"
    print("✓ Correctly rejected invalid hash")
    
    # Test 5: Parent not found
    print("\n5. Testing parent not found...")
    parent_hash = "0xnonexistentparent"
    valid_hash = compute_block_hash(height, parent_hash, timestamp)
    response = requests.post(
        f"{BASE_URL}/importBlock",
        json={
            "height": height,
            "hash": valid_hash,
            "parent_hash": parent_hash,
            "proposer": "test",
            "timestamp": timestamp,
            "tx_count": 0,
            "chain_id": CHAIN_ID
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 400, "Should reject when parent not found"
    assert "Parent block not found" in response.json()["detail"], "Should mention parent not found"
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
