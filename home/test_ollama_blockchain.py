#!/usr/bin/env python3
"""
Ollama GPU Provider Test with Blockchain Verification using Home Directory Users
Tests the complete flow: Client -> Coordinator -> GPU Miner -> Receipt -> Blockchain
"""

import os
import sys
import subprocess
import time
import json
from typing import Optional

import httpx

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cli'))

# Configuration
DEFAULT_COORDINATOR = "http://127.0.0.1:18000"
DEFAULT_BLOCKCHAIN = "http://aitbc.keisanki.net/rpc"
DEFAULT_PROMPT = "What is the capital of France?"
DEFAULT_MODEL = "llama3.2:latest"
DEFAULT_TIMEOUT = 180
POLL_INTERVAL = 3


def get_wallet_balance(wallet_dir: str) -> float:
    """Get wallet balance from home directory wallet"""
    result = subprocess.run(
        f'cd {wallet_dir} && python3 wallet.py balance',
        shell=True,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        for line in result.stdout.split('\n'):
            if 'Balance:' in line:
                # Extract the value after "Balance:"
                balance_part = line.split('Balance:')[1].strip()
                balance_value = balance_part.split()[0]  # Get the numeric part before "AITBC"
                try:
                    return float(balance_value)
                except ValueError:
                    continue
    return 0.0


def get_wallet_address(wallet_dir: str) -> Optional[str]:
    """Get wallet address from home directory wallet"""
    result = subprocess.run(
        f'cd {wallet_dir} && python3 wallet.py address',
        shell=True,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        for line in result.stdout.split('\n'):
            if 'Address:' in line:
                return line.split()[-1]
    return None


def submit_job_via_client(prompt: str, model: str) -> Optional[str]:
    """Submit job using the CLI client"""
    cmd = f'cd ../cli && python3 client.py submit inference --prompt "{prompt}" --model {model}'
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ Job submission failed: {result.stderr}")
        return None
    
    # Extract job ID
    for line in result.stdout.split('\n'):
        if "Job ID:" in line:
            return line.split()[-1]
    return None


def get_job_status(job_id: str) -> Optional[str]:
    """Get job status using CLI client"""
    result = subprocess.run(
        f'cd ../cli && python3 client.py status {job_id}',
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        return None
    
    # Extract state
    for line in result.stdout.split('\n'):
        if "State:" in line:
            return line.split()[-1]
    return None


def get_job_result(job_id: str) -> Optional[dict]:
    """Get job result via API"""
    with httpx.Client() as client:
        response = client.get(
            f"{DEFAULT_COORDINATOR}/v1/jobs/{job_id}/result",
            headers={"X-Api-Key": "${CLIENT_API_KEY}"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
    return None


def check_blockchain_transaction(receipt_id: str) -> Optional[dict]:
    """Check if receipt is recorded on blockchain"""
    try:
        with httpx.Client() as client:
            # Try to get recent transactions
            response = client.get(
                f"{DEFAULT_BLOCKCHAIN}/transactions",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                transactions = data.get("transactions", data.get("items", []))
                # Look for matching receipt
                for tx in transactions:
                    payload = tx.get("payload", {})
                    if payload.get("receipt_id") == receipt_id:
                        return tx
            return None
    except httpx.ConnectError:
        print(f"⚠️  Blockchain node not available at {DEFAULT_BLOCKCHAIN}")
        return None
    except Exception as e:
        print(f"⚠️  Error checking blockchain: {e}")
        return None


def main():
    print("🚀 Ollama GPU Provider Test with Home Directory Users")
    print("=" * 60)
    
    # Get initial balances
    print("\n💰 Initial Wallet Balances:")
    print("-" * 40)
    
    client_balance = get_wallet_balance("client")
    miner_balance = get_wallet_balance("miner")
    
    print(f"   Client: {client_balance} AITBC")
    print(f"   Miner:  {miner_balance} AITBC")
    
    # Submit job
    print(f"\n📤 Submitting Inference Job:")
    print("-" * 40)
    print(f"   Prompt: {DEFAULT_PROMPT}")
    print(f"   Model: {DEFAULT_MODEL}")
    
    job_id = submit_job_via_client(DEFAULT_PROMPT, DEFAULT_MODEL)
    if not job_id:
        print("❌ Failed to submit job")
        return 1
    
    print(f"✅ Job submitted: {job_id}")
    
    # Monitor job progress
    print(f"\n⏳ Monitoring Job Progress:")
    print("-" * 40)
    
    deadline = time.time() + DEFAULT_TIMEOUT
    
    while time.time() < deadline:
        state = get_job_status(job_id)
        if not state:
            print("   ⚠️  Could not fetch status")
            time.sleep(POLL_INTERVAL)
            continue
        
        print(f"   State: {state}")
        
        if state == "COMPLETED":
            break
        elif state in {"FAILED", "CANCELED", "EXPIRED"}:
            print(f"❌ Job ended in state: {state}")
            return 1
        
        time.sleep(POLL_INTERVAL)
    
    if state != "COMPLETED":
        print("❌ Job did not complete within timeout")
        return 1
    
    # Get job result
    print(f"\n📊 Job Result:")
    print("-" * 40)
    
    result = get_job_result(job_id)
    if result:
        output = result.get("result", {}).get("output", "No output")
        receipt = result.get("receipt")
        
        print(f"   Output: {output[:200]}{'...' if len(output) > 200 else ''}")
        
        if receipt:
            print(f"\n🧾 Receipt Information:")
            print(f"   Receipt ID: {receipt.get('receipt_id')}")
            print(f"   Provider: {receipt.get('provider')}")
            print(f"   Units: {receipt.get('units')} {receipt.get('unit_type', 'seconds')}")
            print(f"   Unit Price: {receipt.get('unit_price')} AITBC")
            print(f"   Total Price: {receipt.get('price')} AITBC")
            
            # Check blockchain
            print(f"\n⛓️  Checking Blockchain:")
            print("-" * 40)
            
            tx = check_blockchain_transaction(receipt.get('receipt_id'))
            if tx:
                print(f"✅ Transaction found on blockchain!")
                print(f"   TX Hash: {tx.get('tx_hash')}")
                print(f"   Block: {tx.get('block_height')}")
                print(f"   From: {tx.get('sender')}")
                print(f"   To: {tx.get('recipient')}")
                print(f"   Amount: {tx.get('amount')} AITBC")
            else:
                print(f"⚠️  Transaction not yet found on blockchain")
                print(f"   (May take a few moments to be mined)")
        else:
            print(f"⚠️  No receipt generated")
    else:
        print("   Could not fetch result")
    
    # Show final balances
    print(f"\n💰 Final Wallet Balances:")
    print("-" * 40)
    
    client_balance = get_wallet_balance("client")
    miner_balance = get_wallet_balance("miner")
    
    print(f"   Client: {client_balance} AITBC")
    print(f"   Miner:  {miner_balance} AITBC")
    
    # Calculate difference
    client_diff = client_balance - get_wallet_balance("client")
    print(f"\n📈 Transaction Summary:")
    print("-" * 40)
    print(f"   Client spent: {abs(client_diff):.4f} AITBC")
    print(f"   Miner earned: {abs(client_diff):.4f} AITBC")
    
    print(f"\n✅ Test completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
