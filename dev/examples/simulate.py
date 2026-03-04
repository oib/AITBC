#!/usr/bin/env python3
"""
Complete simulation: Client pays for GPU services, Miner earns AITBC
"""

import os
import sys
import time
import subprocess

def run_wallet_command(wallet_type, command, description):
    """Run a wallet command and display results"""
    print(f"\n{'='*60}")
    print(f"💼 {wallet_type}: {description}")
    print(f"{'='*60}")
    
    wallet_dir = os.path.join(os.path.dirname(__file__), wallet_type.lower())
    cmd = f"cd {wallet_dir} && python3 wallet.py {command}"
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    
    if result.stderr:
        print(f"Error: {result.stderr}")
    
    return result

def main():
    print("🎭 AITBC Local Simulation")
    print("=" * 60)
    print("Simulating client and GPU provider interactions")
    print()
    
    # Step 1: Initialize wallets with genesis distribution
    print("📋 STEP 1: Initialize Wallets")
    os.system("cd /home/oib/windsurf/aitbc/home && python3 genesis.py")
    
    input("\nPress Enter to continue...")
    
    # Step 2: Check initial balances
    print("\n📋 STEP 2: Check Initial Balances")
    run_wallet_command("Client", "balance", "Initial client balance")
    run_wallet_command("Miner", "balance", "Initial miner balance")
    
    input("\nPress Enter to continue...")
    
    # Step 3: Client submits a job (using CLI tool)
    print("\n📋 STEP 3: Client Submits Job")
    print("-" * 40)
    
    # Submit job to coordinator
    result = subprocess.run(
        "cd /home/oib/windsurf/aitbc/cli && python3 client.py submit inference --model llama-2-7b --prompt 'What is the future of AI?'",
        shell=True,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    
    # Extract job ID if successful
    job_id = None
    if "Job ID:" in result.stdout:
        for line in result.stdout.split('\n'):
            if "Job ID:" in line:
                job_id = line.split()[-1]
                break
    
    input("\nPress Enter to continue...")
    
    # Step 4: Miner processes the job
    print("\n📋 STEP 4: Miner Processes Job")
    print("-" * 40)
    
    if job_id:
        print(f"⛏️  Miner found job: {job_id}")
        print("⚙️  Processing job...")
        time.sleep(2)
        
        # Miner earns AITBC for completing the job
        run_wallet_command(
            "Miner", 
            f"earn 50.0 --job {job_id} --desc 'Inference task completed'", 
            "Miner earns AITBC"
        )
    
    input("\nPress Enter to continue...")
    
    # Step 5: Client pays for the service
    print("\n📋 STEP 5: Client Pays for Service")
    print("-" * 40)
    
    if job_id:
        # Get miner address
        miner_result = subprocess.run(
            "cd /home/oib/windsurf/aitbc/home/miner && python3 wallet.py address",
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
            run_wallet_command(
                "Client",
                f"send 50.0 {miner_address} 'Payment for inference job {job_id}'",
                "Client pays for completed job"
            )
    
    input("\nPress Enter to continue...")
    
    # Step 6: Check final balances
    print("\n📋 STEP 6: Final Balances")
    run_wallet_command("Client", "balance", "Final client balance")
    run_wallet_command("Miner", "balance", "Final miner balance")
    
    print("\n🎉 Simulation Complete!")
    print("=" * 60)
    print("Summary:")
    print("  • Client submitted job and paid 50 AITBC")
    print("  • Miner processed job and earned 50 AITBC")
    print("  • Transaction recorded on blockchain")
    print()
    print("💡 You can:")
    print("  • Run 'cd home/client && python3 wallet.py history' to see client transactions")
    print("  • Run 'cd home/miner && python3 wallet.py stats' to see miner earnings")
    print("  • Submit more jobs with the CLI tools")

if __name__ == "__main__":
    main()
