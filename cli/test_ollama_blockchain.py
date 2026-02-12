#!/usr/bin/env python3
"""
Ollama GPU Provider Test with Blockchain Verification
Submits an inference job and verifies the complete flow:
- Job submission to coordinator
- Processing by GPU miner
- Receipt generation
- Blockchain transaction recording
"""

import argparse
import sys
import time
from typing import Optional
import json

import httpx

# Configuration
DEFAULT_COORDINATOR = "http://localhost:8000"
DEFAULT_BLOCKCHAIN = "http://127.0.0.1:19000"
DEFAULT_API_KEY = "${CLIENT_API_KEY}"
DEFAULT_PROMPT = "What is the capital of France?"
DEFAULT_MODEL = "llama3.2:latest"
DEFAULT_TIMEOUT = 180
POLL_INTERVAL = 3


def submit_job(client: httpx.Client, base_url: str, api_key: str, prompt: str, model: str) -> Optional[str]:
    """Submit an inference job to the coordinator"""
    payload = {
        "payload": {
            "type": "inference",
            "prompt": prompt,
            "parameters": {
                "prompt": prompt,
                "model": model,
                "stream": False
            },
        },
        "ttl_seconds": 900,
    }
    response = client.post(
        f"{base_url}/v1/jobs",
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    if response.status_code != 201:
        print(f"❌ Job submission failed: {response.status_code} {response.text}")
        return None
    return response.json().get("job_id")


def fetch_status(client: httpx.Client, base_url: str, api_key: str, job_id: str) -> Optional[dict]:
    """Fetch job status from coordinator"""
    response = client.get(
        f"{base_url}/v1/jobs/{job_id}",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Status check failed: {response.status_code} {response.text}")
        return None
    return response.json()


def fetch_result(client: httpx.Client, base_url: str, api_key: str, job_id: str) -> Optional[dict]:
    """Fetch job result from coordinator"""
    response = client.get(
        f"{base_url}/v1/jobs/{job_id}/result",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Result fetch failed: {response.status_code} {response.text}")
        return None
    return response.json()


def fetch_receipt(client: httpx.Client, base_url: str, api_key: str, job_id: str) -> Optional[dict]:
    """Fetch job receipt from coordinator"""
    response = client.get(
        f"{base_url}/v1/jobs/{job_id}/receipt",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Receipt fetch failed: {response.status_code} {response.text}")
        return None
    return response.json()


def check_blockchain_transaction(client: httpx.Client, blockchain_url: str, receipt_id: str) -> Optional[dict]:
    """Check if receipt is recorded on blockchain"""
    # Search for transaction by receipt ID
    response = client.get(
        f"{blockchain_url}/rpc/transactions/search",
        params={"receipt_id": receipt_id},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"⚠️  Blockchain search failed: {response.status_code}")
        return None
    
    transactions = response.json().get("transactions", [])
    if transactions:
        return transactions[0]  # Return the first matching transaction
    return None


def get_miner_info(client: httpx.Client, base_url: str, api_key: str) -> Optional[dict]:
    """Get registered miner information"""
    response = client.get(
        f"{base_url}/v1/admin/miners",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"⚠️  Could not fetch miner info: {response.status_code}")
        return None
    
    data = response.json()
    # Handle different response formats
    if isinstance(data, list):
        return data[0] if data else None
    elif isinstance(data, dict):
        if 'miners' in data:
            miners = data['miners']
            return miners[0] if miners else None
        elif 'items' in data:
            items = data['items']
            return items[0] if items else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Ollama GPU provider with blockchain verification")
    parser.add_argument("--coordinator-url", default=DEFAULT_COORDINATOR, help="Coordinator base URL")
    parser.add_argument("--blockchain-url", default=DEFAULT_BLOCKCHAIN, help="Blockchain node URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Client API key")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt to send")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model to use")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    args = parser.parse_args()

    print("🚀 Starting Ollama GPU Provider Test with Blockchain Verification")
    print("=" * 60)
    
    # Check miner registration
    print("\n📋 Checking miner registration...")
    with httpx.Client() as client:
        miner_info = get_miner_info(client, args.coordinator_url, "${ADMIN_API_KEY}")
        if miner_info:
            print(f"✅ Found registered miner: {miner_info.get('miner_id')}")
            print(f"   Status: {miner_info.get('status')}")
            print(f"   Last seen: {miner_info.get('last_seen')}")
        else:
            print("⚠️  No miners registered. Job may not be processed.")
    
    # Submit job
    print(f"\n📤 Submitting inference job...")
    print(f"   Prompt: {args.prompt}")
    print(f"   Model: {args.model}")
    
    with httpx.Client() as client:
        job_id = submit_job(client, args.coordinator_url, args.api_key, args.prompt, args.model)
        if not job_id:
            return 1
        print(f"✅ Job submitted successfully: {job_id}")

        # Monitor job progress
        print(f"\n⏳ Monitoring job progress...")
        deadline = time.time() + args.timeout
        status = None
        
        while time.time() < deadline:
            status = fetch_status(client, args.coordinator_url, args.api_key, job_id)
            if not status:
                return 1
            
            state = status.get("state")
            assigned_miner = status.get("assigned_miner_id", "None")
            
            print(f"   State: {state} | Miner: {assigned_miner}")
            
            if state == "COMPLETED":
                break
            if state in {"FAILED", "CANCELED", "EXPIRED"}:
                print(f"❌ Job ended in state: {state}")
                if status.get("error"):
                    print(f"   Error: {status['error']}")
                return 1
            time.sleep(POLL_INTERVAL)

        if not status or status.get("state") != "COMPLETED":
            print("❌ Job did not complete within timeout")
            return 1

        # Fetch result and receipt
        print(f"\n📊 Fetching job results...")
        result = fetch_result(client, args.coordinator_url, args.api_key, job_id)
        if result is None:
            return 1

        receipt = fetch_receipt(client, args.coordinator_url, args.api_key, job_id)
        if receipt is None:
            print("⚠️  No receipt found (payment may not be processed)")
            receipt = {}
        
        # Display results
        payload = result.get("result") or {}
        output = payload.get("output", "No output")
        
        print(f"\n✅ Job completed successfully!")
        print(f"📝 Output: {output[:200]}{'...' if len(output) > 200 else ''}")
        
        if receipt:
            print(f"\n🧾 Receipt Information:")
            print(f"   Receipt ID: {receipt.get('receipt_id')}")
            print(f"   Provider: {receipt.get('provider')}")
            print(f"   Units: {receipt.get('units')} {receipt.get('unit_type', 'seconds')}")
            print(f"   Unit Price: {receipt.get('unit_price')} AITBC")
            print(f"   Total Price: {receipt.get('price')} AITBC")
            print(f"   Status: {receipt.get('status')}")
            
            # Check blockchain
            print(f"\n⛓️  Checking blockchain recording...")
            receipt_id = receipt.get('receipt_id')
            
            with httpx.Client() as bc_client:
                tx = check_blockchain_transaction(bc_client, args.blockchain_url, receipt_id)
                
                if tx:
                    print(f"✅ Transaction found on blockchain!")
                    print(f"   TX Hash: {tx.get('tx_hash')}")
                    print(f"   Block: {tx.get('block_height')}")
                    print(f"   From: {tx.get('sender')}")
                    print(f"   To: {tx.get('recipient')}")
                    print(f"   Amount: {tx.get('amount')} AITBC")
                    
                    # Show transaction payload
                    payload = tx.get('payload', {})
                    if 'receipt_id' in payload:
                        print(f"   Payload Receipt: {payload['receipt_id']}")
                else:
                    print(f"⚠️  Transaction not yet found on blockchain")
                    print(f"   This may take a few moments to be mined...")
                    print(f"   Receipt ID: {receipt_id}")
        else:
            print(f"\n❌ No receipt generated - payment not processed")
        
        print(f"\n🎉 Test completed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
