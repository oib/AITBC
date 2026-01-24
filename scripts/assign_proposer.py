#!/usr/bin/env python3
"""
Script to assign a proposer to a block by polling for it
"""

import httpx
import json

# Configuration
COORDINATOR_URL = "http://localhost:8001"
MINER_API_KEY = "REDACTED_MINER_KEY"
MINER_ID = "localhost-gpu-miner"

def assign_proposer_to_latest_block():
    """Poll for the latest unassigned job to become the proposer"""
    
    # First register the miner
    print("📝 Registering miner...")
    register_response = httpx.post(
        f"{COORDINATOR_URL}/v1/miners/register?miner_id={MINER_ID}",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": MINER_API_KEY
        },
        json={
            "capabilities": {
                "gpu": {"model": "RTX 4060 Ti", "memory_gb": 16}
            }
        }
    )
    
    if register_response.status_code != 200:
        print(f"❌ Registration failed: {register_response.text}")
        return
    
    print("✅ Miner registered")
    
    # Poll for a job
    print("\n🔍 Polling for jobs...")
    poll_response = httpx.post(
        f"{COORDINATOR_URL}/v1/miners/poll",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": MINER_API_KEY
        },
        json={"max_wait_seconds": 1}
    )
    
    if poll_response.status_code == 200:
        job = poll_response.json()
        print(f"✅ Received job: {job['job_id']}")
        print(f"   This job is now assigned to miner: {MINER_ID}")
        
        # Check the block
        print("\n📦 Checking block...")
        blocks_response = httpx.get(f"{COORDINATOR_URL}/v1/explorer/blocks")
        
        if blocks_response.status_code == 200:
            blocks = blocks_response.json()
            for block in blocks['items']:
                if block['hash'] == job['job_id']:
                    print(f"✅ Block updated!")
                    print(f"   Height: {block['height']}")
                    print(f"   Hash: {block['hash']}")
                    print(f"   Proposer: {block['proposer']}")
                    break
    elif poll_response.status_code == 204:
        print("ℹ️  No jobs available to poll")
    else:
        print(f"❌ Poll failed: {poll_response.text}")

if __name__ == "__main__":
    print("🎯 Assign Proposer to Latest Block")
    print("=" * 40)
    assign_proposer_to_latest_block()
