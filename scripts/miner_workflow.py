#!/usr/bin/env python3
"""
Complete miner workflow - poll for jobs and assign proposer
"""

import httpx
import json
import time
from datetime import datetime

# Configuration
COORDINATOR_URL = "http://localhost:8001"
MINER_API_KEY = "REDACTED_MINER_KEY"
MINER_ID = "localhost-gpu-miner"

def poll_and_accept_job():
    """Poll for a job and accept it"""
    print("🔍 Polling for jobs...")
    
    with httpx.Client() as client:
        # Poll for a job
        response = client.post(
            f"{COORDINATOR_URL}/v1/miners/poll",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": MINER_API_KEY
            },
            json={"max_wait_seconds": 5}
        )
        
        if response.status_code == 200:
            job = response.json()
            print(f"✅ Received job: {job['job_id']}")
            print(f"   Task: {job['payload'].get('task', 'unknown')}")
            
            # Simulate processing
            print("⚙️  Processing job...")
            time.sleep(2)
            
            # Submit result
            result_data = {
                "result": {
                    "status": "completed",
                    "output": f"Job {job['job_id']} completed successfully",
                    "execution_time_ms": 2000,
                    "miner_id": MINER_ID
                },
                "metrics": {
                    "compute_time": 2.0,
                    "energy_used": 0.1
                }
            }
            
            print(f"📤 Submitting result for job {job['job_id']}...")
            result_response = client.post(
                f"{COORDINATOR_URL}/v1/miners/{job['job_id']}/result",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": MINER_API_KEY
                },
                json=result_data
            )
            
            if result_response.status_code == 200:
                print("✅ Result submitted successfully!")
                return job['job_id']
            else:
                print(f"❌ Failed to submit result: {result_response.status_code}")
                print(f"   Response: {result_response.text}")
                return None
                
        elif response.status_code == 204:
            print("ℹ️  No jobs available")
            return None
        else:
            print(f"❌ Failed to poll: {response.status_code}")
            return None

def check_block_proposer(job_id):
    """Check if the block now has a proposer"""
    print(f"\n🔍 Checking proposer for job {job_id}...")
    
    with httpx.Client() as client:
        response = client.get(f"{COORDINATOR_URL}/v1/explorer/blocks")
        
        if response.status_code == 200:
            blocks = response.json()
            for block in blocks['items']:
                if block['hash'] == job_id:
                    print(f"📦 Block Info:")
                    print(f"   Height: {block['height']}")
                    print(f"   Hash: {block['hash']}")
                    print(f"   Proposer: {block['proposer']}")
                    print(f"   Time: {block['timestamp']}")
                    return block
        return None

def main():
    print("⛏️  AITBC Miner Workflow Demo")
    print(f"   Miner ID: {MINER_ID}")
    print(f"   Coordinator: {COORDINATOR_URL}")
    print()
    
    # Poll and accept a job
    job_id = poll_and_accept_job()
    
    if job_id:
        # Check if the block has a proposer now
        time.sleep(1)  # Give the server a moment to update
        check_block_proposer(job_id)
    else:
        print("\n💡 Tip: Create a job first using example_client_remote.py")

if __name__ == "__main__":
    main()
