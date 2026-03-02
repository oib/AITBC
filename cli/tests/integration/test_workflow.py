#!/usr/bin/env python3
"""
Complete AITBC workflow test - Client submits job, miner processes it, earns AITBC
"""

import subprocess
import time
import sys
import os

def run_command(cmd, description):
    """Run a CLI command and display results"""
    print(f"\n{'='*60}")
    print(f"🔧 {description}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    
    if result.stderr:
        print(f"Errors: {result.stderr}")
    
    return result.returncode == 0

def main():
    print("🚀 AITBC Complete Workflow Test")
    print("=" * 60)
    
    # Get the directory of this script
    cli_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Check current blocks
    run_command(
        f"python3 {cli_dir}/client.py blocks --limit 3",
        "Checking current blocks"
    )
    
    # 2. Register miner
    run_command(
        f"python3 {cli_dir}/miner.py register --gpu RTX 4090 --memory 24",
        "Registering miner"
    )
    
    # 3. Submit a job from client
    run_command(
        f"python3 {cli_dir}/client.py submit inference --model llama-2-7b --prompt 'What is blockchain?'",
        "Client submitting inference job"
    )
    
    # 4. Miner polls for and processes the job
    print(f"\n{'='*60}")
    print("⛏️  Miner polling for job (will wait up to 10 seconds)...")
    print(f"{'='*60}")
    
    # Run miner in poll mode repeatedly
    for i in range(5):
        result = subprocess.run(
            f"python3 {cli_dir}/miner.py poll --wait 2",
            shell=True,
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        
        if "job_id" in result.stdout:
            print("✅ Job found! Processing...")
            time.sleep(2)
            break
        
        if i < 4:
            print("💤 No job yet, trying again...")
            time.sleep(2)
    
    # 5. Check updated blocks
    run_command(
        f"python3 {cli_dir}/client.py blocks --limit 3",
        "Checking updated blocks (should show proposer)"
    )
    
    # 6. Check wallet
    run_command(
        f"python3 {cli_dir}/wallet.py balance",
        "Checking wallet balance"
    )
    
    # Add earnings manually (in real system, this would be automatic)
    run_command(
        f"python3 {cli_dir}/wallet.py earn 10.0 --job demo-job-123 --desc 'Inference task completed'",
        "Adding earnings to wallet"
    )
    
    # 7. Final wallet status
    run_command(
        f"python3 {cli_dir}/wallet.py history",
        "Showing transaction history"
    )
    
    print(f"\n{'='*60}")
    print("✅ Workflow test complete!")
    print("💡 Tips:")
    print("   - Use 'python3 cli/client.py --help' for client commands")
    print("   - Use 'python3 cli/miner.py --help' for miner commands")
    print("   - Use 'python3 cli/wallet.py --help' for wallet commands")
    print("   - Run 'python3 cli/miner.py mine' for continuous mining")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
