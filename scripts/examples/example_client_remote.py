#!/usr/bin/env python3
"""
Example client using the remote AITBC coordinator
"""

import httpx
import json
from datetime import datetime

# Configuration - using the SSH tunnel to remote server
COORDINATOR_URL = "http://localhost:8001"
CLIENT_API_KEY = "${CLIENT_API_KEY}"

def create_job():
    """Create a job on the remote coordinator"""
    job_data = {
        "payload": {
            "type": "inference",
            "task": "text-generation",
            "model": "llama-2-7b",
            "parameters": {
                "prompt": "Hello, AITBC!",
                "max_tokens": 100
            }
        },
        "ttl_seconds": 900
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{COORDINATOR_URL}/v1/jobs",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": CLIENT_API_KEY
            },
            json=job_data
        )
        
        if response.status_code == 201:
            job = response.json()
            print(f"✅ Job created successfully!")
            print(f"   Job ID: {job['job_id']}")
            print(f"   State: {job['state']}")
            print(f"   Expires at: {job['expires_at']}")
            return job['job_id']
        else:
            print(f"❌ Failed to create job: {response.status_code}")
            print(f"   Response: {response.text}")
            return None

def check_job_status(job_id):
    """Check the status of a job"""
    with httpx.Client() as client:
        response = client.get(
            f"{COORDINATOR_URL}/v1/jobs/{job_id}",
            headers={"X-Api-Key": CLIENT_API_KEY}
        )
        
        if response.status_code == 200:
            job = response.json()
            print(f"\n📊 Job Status:")
            print(f"   Job ID: {job['job_id']}")
            print(f"   State: {job['state']}")
            print(f"   Assigned Miner: {job.get('assigned_miner_id', 'None')}")
            print(f"   Created: {job['requested_at']}")
            return job
        else:
            print(f"❌ Failed to get job status: {response.status_code}")
            return None

def list_blocks():
    """List blocks from the explorer"""
    with httpx.Client() as client:
        response = client.get(f"{COORDINATOR_URL}/v1/explorer/blocks")
        
        if response.status_code == 200:
            blocks = response.json()
            print(f"\n📦 Recent Blocks ({len(blocks['items'])} total):")
            for block in blocks['items'][:5]:  # Show last 5 blocks
                print(f"   Height: {block['height']}")
                print(f"   Hash: {block['hash']}")
                print(f"   Time: {block['timestamp']}")
                print(f"   Transactions: {block['txCount']}")
                print(f"   Proposer: {block['proposer']}")
                print()
        else:
            print(f"❌ Failed to list blocks: {response.status_code}")

def main():
    print("🚀 AITBC Remote Client Example")
    print(f"   Connecting to: {COORDINATOR_URL}")
    print()
    
    # List current blocks
    list_blocks()
    
    # Create a new job
    job_id = create_job()
    
    if job_id:
        # Check job status
        check_job_status(job_id)
        
        # List blocks again to see the new job
        print("\n🔄 Updated block list:")
        list_blocks()

if __name__ == "__main__":
    main()
