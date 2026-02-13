#!/usr/bin/env python3
"""
Demonstration: How customers get replies from GPU providers
"""

import subprocess
import time

def main():
    print("📨 How Customers Get Replies in AITBC")
    print("=" * 60)
    
    print("\n🔄 Complete Flow:")
    print("1. Customer submits job")
    print("2. GPU provider processes job")
    print("3. Result stored on blockchain")
    print("4. Customer retrieves result")
    print("5. Customer pays for service")
    
    print("\n" + "=" * 60)
    print("\n📝 STEP 1: Customer Submits Job")
    print("-" * 40)
    
    # Submit a job
    result = subprocess.run(
        'cd ../cli && python3 client.py submit inference --prompt "What is AI?"',
        shell=True,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    
    # Extract job ID
    job_id = None
    for line in result.stdout.split('\n'):
        if "Job ID:" in line:
            job_id = line.split()[-1]
            break
    
    if not job_id:
        print("❌ Failed to submit job")
        return
    
    print(f"\n✅ Job submitted with ID: {job_id}")
    
    print("\n⚙️  STEP 2: GPU Provider Processes Job")
    print("-" * 40)
    print("   • Miner polls for jobs")
    print("   • Job assigned to miner")
    print("   • GPU processes the request")
    print("   • Result submitted to network")
    
    # Simulate processing
    print("\n   💭 Simulating GPU processing...")
    time.sleep(2)
    
    print("\n📦 STEP 3: Result Stored on Blockchain")
    print("-" * 40)
    print(f"   • Job {job_id} marked as completed")
    print(f"   • Result stored with job metadata")
    print(f"   • Block created with job details")
    
    # Show block
    print("\n   📋 Blockchain Entry:")
    print(f"   Block Hash: {job_id}")
    print(f"   Proposer: gpu-miner")
    print(f"   Status: COMPLETED")
    print(f"   Result: Available for retrieval")
    
    print("\n🔍 STEP 4: Customer Retrieves Result")
    print("-" * 40)
    
    print("   Method 1: Check job status")
    print(f"   $ python3 cli/client.py status {job_id}")
    print()
    
    # Show status
    status_result = subprocess.run(
        f'cd ../cli && python3 client.py status {job_id}',
        shell=True,
        capture_output=True,
        text=True
    )
    
    print("   Status Result:")
    for line in status_result.stdout.split('\n'):
        if line.strip():
            print(f"   {line}")
    
    print("\n   Method 2: Get full result")
    print(f"   $ python3 client_get_result.py {job_id}")
    print()
    
    print("   📄 Full Result:")
    print("   ----------")
    print("   Output: AI stands for Artificial Intelligence, which refers")
    print("           to the simulation of human intelligence in machines")
    print("           that are programmed to think and learn.")
    print("   Tokens: 28")
    print("   Cost: 0.000028 AITBC")
    print("   Miner: GPU Provider #1")
    
    print("\n💸 STEP 5: Customer Pays for Service")
    print("-" * 40)
    
    # Get miner address
    miner_result = subprocess.run(
        'cd miner && python3 wallet.py address',
        shell=True,
        capture_output=True,
        text=True
    )
    
    miner_address = None
    for line in miner_result.stdout.split('\n'):
        if "Miner Address:" in line:
            miner_address = line.split()[-1]
            break
    
    if miner_address:
        print(f"   Payment sent to: {miner_address}")
        print("   Amount: 25.0 AITBC")
        print("   Status: ✅ Paid")
    
    print("\n" + "=" * 60)
    print("✅ Customer successfully received reply!")
    
    print("\n📋 Summary of Retrieval Methods:")
    print("-" * 40)
    print("1. Job Status: python3 cli/client.py status <job_id>")
    print("2. Full Result: python3 client_get_result.py <job_id>")
    print("3. Watch Job: python3 client_get_result.py watch <job_id>")
    print("4. List Recent: python3 client_get_result.py list")
    print("5. Enhanced Client: python3 enhanced_client.py")
    
    print("\n💡 In production:")
    print("   • Results are stored on-chain")
    print("   • Customers can retrieve anytime")
    print("   • Results are immutable and verifiable")
    print("   • Payment is required to unlock full results")

if __name__ == "__main__":
    main()
