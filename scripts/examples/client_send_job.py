#!/usr/bin/env python3
"""
Client sends a job to GPU provider and pays for it
"""

import subprocess
import json
import time
import sys
import os

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'cli'))
sys.path.append(os.path.join(os.path.dirname(__file__)))

def send_job_to_gpu_provider():
    print("🚀 Client: Sending Job to GPU Provider")
    print("=" * 60)
    
    # 1. Check client wallet balance
    print("\n1. Checking client wallet...")
    result = subprocess.run(
        'cd client && python3 wallet.py balance',
        shell=True,
        capture_output=True,
        text=True
    )
    print(result.stdout)
    
    # 2. Submit job to coordinator
    print("\n2. Submitting 'hello' job to network...")
    job_result = subprocess.run(
        'cd ../cli && python3 client.py submit inference --prompt "hello"',
        shell=True,
        capture_output=True,
        text=True
    )
    
    print(job_result.stdout)
    
    # Extract job ID
    job_id = None
    if "Job ID:" in job_result.stdout:
        for line in job_result.stdout.split('\n'):
            if "Job ID:" in line:
                job_id = line.split()[-1]
                break
    
    if not job_id:
        print("❌ Failed to submit job")
        return
    
    print(f"\n✅ Job submitted: {job_id}")
    
    # 3. Wait for miner to process
    print("\n3. Waiting for GPU provider to process job...")
    print("   (Make sure miner is running: python3 cli/miner.py mine)")
    
    # Check job status
    max_wait = 30
    for i in range(max_wait):
        status_result = subprocess.run(
            f'cd ../cli && python3 client.py status {job_id}',
            shell=True,
            capture_output=True,
            text=True
        )
        
        if "completed" in status_result.stdout:
            print("✅ Job completed by GPU provider!")
            print(status_result.stdout)
            break
        elif "failed" in status_result.stdout:
            print("❌ Job failed")
            print(status_result.stdout)
            break
        else:
            print(f"   Waiting... ({i+1}s)")
            time.sleep(1)
    
    # 4. Get cost and pay
    print("\n4. Processing payment...")
    
    # For demo, assume cost is 10 AITBC
    job_cost = 10.0
    
    # Get miner address
    miner_result = subprocess.run(
        'cd miner && python3 wallet.py address',
        shell=True,
        capture_output=True,
        text=True
    )
    
    miner_address = None
    if "Miner Address:" in miner_result.stdout:
        for line in miner_result.stdout.split('\n'):
            if "Miner Address:" in line:
                miner_address = line.split()[-1]
                break
    
    if miner_address:
        print(f"   Paying {job_cost} AITBC to miner...")
        
        # Send payment
        pay_result = subprocess.run(
            f'cd client && python3 wallet.py send {job_cost} {miner_address} "Payment for job {job_id}"',
            shell=True,
            capture_output=True,
            text=True
        )
        
        print(pay_result.stdout)
    
    # 5. Show final balances
    print("\n5. Final balances:")
    print("\n   Client:")
    subprocess.run('cd client && python3 wallet.py balance', shell=True)
    
    print("\n   Miner:")
    subprocess.run('cd miner && python3 wallet.py balance', shell=True)
    
    print("\n✅ Job completed and paid for!")

if __name__ == "__main__":
    send_job_to_gpu_provider()
