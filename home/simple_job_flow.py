#!/usr/bin/env python3
"""
Simple job flow: Client -> GPU Provider -> Payment
"""

import subprocess
import time

def main():
    print("📋 AITBC Job Flow: Client -> GPU Provider -> Payment")
    print("=" * 60)
    
    print("\n📝 STEP 1: Client submits job 'hello'")
    print("-" * 40)
    
    # Submit job
    result = subprocess.run(
        'cd ../cli && python3 client.py demo',
        shell=True,
        capture_output=True,
        text=True
    )
    print(result.stdout)
    
    # Extract job ID
    job_id = None
    if "Job ID:" in result.stdout:
        for line in result.stdout.split('\n'):
            if "Job ID:" in line:
                job_id = line.split()[-1]
                break
    
    if not job_id:
        print("❌ Failed to submit job")
        return
    
    print(f"\n📮 Job submitted: {job_id}")
    
    print("\n⛏️  STEP 2: GPU Provider processes job")
    print("-" * 40)
    print("   (Start miner with: python3 cli/miner.py mine)")
    print("   The miner will automatically pick up the job")
    
    # Simulate miner processing
    print("\n   💭 Simulating job processing...")
    time.sleep(2)
    
    # Miner earns AITBC
    print("   ✅ Job processed!")
    print("   💰 Miner earned 25 AITBC")
    
    # Add to miner wallet
    subprocess.run(
        f'cd miner && python3 wallet.py earn 25.0 --job {job_id} --desc "Processed hello job"',
        shell=True,
        capture_output=True,
        text=True
    )
    
    print("\n💸 STEP 3: Client pays for service")
    print("-" * 40)
    
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
        # Client pays
        subprocess.run(
            f'cd client && python3 wallet.py send 25.0 {miner_address} "Payment for job {job_id}"',
            shell=True,
            capture_output=True,
            text=True
        )
    
    print("\n📊 STEP 4: Final balances")
    print("-" * 40)
    
    print("\n   Client Wallet:")
    subprocess.run('cd client && python3 wallet.py balance', shell=True)
    
    print("\n   Miner Wallet:")
    subprocess.run('cd miner && python3 wallet.py balance', shell=True)
    
    print("\n✅ Complete workflow demonstrated!")
    print("\n💡 To run with real GPU processing:")
    print("   1. Start miner: python3 cli/miner.py mine")
    print("   2. Submit job: python3 cli/client.py submit inference --prompt 'hello'")
    print("   3. Check status: python3 cli/client.py status <job_id>")
    print("   4. Pay manually: cd home/client && python3 wallet.py send <amount> <miner_address>")

if __name__ == "__main__":
    main()
