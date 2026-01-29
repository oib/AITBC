#!/usr/bin/env python3
"""
AITBC Client CLI Tool - Submit jobs and check status
"""

import argparse
import httpx
import json
import sys
from datetime import datetime
from typing import Optional

# Configuration
DEFAULT_COORDINATOR = "http://127.0.0.1:18000"
DEFAULT_API_KEY = "REDACTED_CLIENT_KEY"

class AITBCClient:
    def __init__(self, coordinator_url: str, api_key: str):
        self.coordinator_url = coordinator_url
        self.api_key = api_key
        self.client = httpx.Client()
        
    def submit_job(self, job_type: str, task_data: dict, ttl: int = 900) -> Optional[str]:
        """Submit a job to the coordinator"""
        job_payload = {
            "payload": {
                "type": job_type,
                **task_data
            },
            "ttl_seconds": ttl
        }
        
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/jobs",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json=job_payload
            )
            
            if response.status_code == 201:
                job = response.json()
                return job['job_id']
            else:
                print(f"❌ Error submitting job: {response.status_code}")
                print(f"   Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def list_transactions(self, limit: int = 10) -> Optional[list]:
        """List recent transactions"""
        try:
            response = self.client.get(
                f"{self.coordinator_url}/v1/explorer/transactions",
                params={"limit": limit}
            )

            if response.status_code == 200:
                transactions = response.json()
                return transactions.get('items', [])[:limit]
            else:
                print(f"❌ Error listing transactions: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def list_receipts(self, limit: int = 10, job_id: Optional[str] = None) -> Optional[list]:
        """List recent receipts"""
        params = {"limit": limit}
        if job_id:
            params["job_id"] = job_id
        try:
            response = self.client.get(
                f"{self.coordinator_url}/v1/explorer/receipts",
                params=params
            )

            if response.status_code == 200:
                receipts = response.json()
                return receipts.get('items', [])[:limit]
            else:
                print(f"❌ Error listing receipts: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get job status"""
        try:
            response = self.client.get(
                f"{self.coordinator_url}/v1/jobs/{job_id}",
                headers={"X-Api-Key": self.api_key}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error getting status: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def list_blocks(self, limit: int = 10) -> Optional[list]:
        """List recent blocks"""
        try:
            response = self.client.get(f"{self.coordinator_url}/v1/explorer/blocks")
            
            if response.status_code == 200:
                blocks = response.json()
                return blocks['items'][:limit]
            else:
                print(f"❌ Error listing blocks: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description="AITBC Client CLI")
    parser.add_argument("--url", default=DEFAULT_COORDINATOR, help="Coordinator URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Submit job command
    submit_parser = subparsers.add_parser("submit", help="Submit a job")
    submit_parser.add_argument("type", help="Job type (e.g., inference, training)")
    submit_parser.add_argument("--task", help="Task description")
    submit_parser.add_argument("--model", help="Model to use")
    submit_parser.add_argument("--prompt", help="Prompt for inference")
    submit_parser.add_argument("--ttl", type=int, default=900, help="TTL in seconds")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check job status")
    status_parser.add_argument("job_id", help="Job ID to check")
    
    # Blocks command
    blocks_parser = subparsers.add_parser("blocks", help="List recent blocks")
    blocks_parser.add_argument("--limit", type=int, default=10, help="Number of blocks")

    # Browser command
    browser_parser = subparsers.add_parser("browser", help="Show latest blocks, transactions, and receipt metrics")
    browser_parser.add_argument("--block-limit", type=int, default=1, help="Number of blocks")
    browser_parser.add_argument("--tx-limit", type=int, default=5, help="Number of transactions")
    browser_parser.add_argument("--receipt-limit", type=int, default=10, help="Number of receipts")
    browser_parser.add_argument("--job-id", help="Filter receipts by job ID")
    
    # Quick demo command
    demo_parser = subparsers.add_parser("demo", help="Submit a demo job")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    client = AITBCClient(args.url, args.api_key)
    
    if args.command == "submit":
        task_data = {}
        if args.task:
            task_data["task"] = args.task
        if args.model:
            task_data["model"] = args.model
        if args.prompt:
            task_data["prompt"] = args.prompt
            task_data["parameters"] = {"prompt": args.prompt}
        
        print(f"📤 Submitting {args.type} job...")
        job_id = client.submit_job(args.type, task_data, args.ttl)
        
        if job_id:
            print(f"✅ Job submitted successfully!")
            print(f"   Job ID: {job_id}")
            print(f"   Track with: python3 cli/client.py status {job_id}")
    
    elif args.command == "status":
        print(f"🔍 Checking status for job {args.job_id}...")
        status = client.get_job_status(args.job_id)
        
        if status:
            print(f"📊 Job Status:")
            print(f"   ID: {status['job_id']}")
            print(f"   State: {status['state']}")
            print(f"   Miner: {status.get('assigned_miner_id', 'None')}")
            print(f"   Created: {status['requested_at']}")
            if status.get('expires_at'):
                print(f"   Expires: {status['expires_at']}")
    
    elif args.command == "blocks":
        print(f"📦 Recent blocks (last {args.limit}):")
        blocks = client.list_blocks(args.limit)
        
        if blocks:
            for i, block in enumerate(blocks, 1):
                print(f"\n{i}. Height: {block['height']}")
                print(f"   Hash: {block['hash']}")
                print(f"   Time: {block['timestamp']}")
                print(f"   Proposer: {block['proposer']}")

    elif args.command == "browser":
        blocks = client.list_blocks(args.block_limit) or []
        transactions = client.list_transactions(args.tx_limit) or []
        receipts = client.list_receipts(args.receipt_limit, job_id=args.job_id) or []

        print("🧭 Blockchain Browser Snapshot")
        if blocks:
            block = blocks[0]
            tx_count = block.get("txCount", block.get("tx_count"))
            print("\n🧱 Latest Block")
            print(f"   Height: {block.get('height')}")
            print(f"   Hash: {block.get('hash')}")
            print(f"   Time: {block.get('timestamp')}")
            print(f"   Tx Count: {tx_count}")
            print(f"   Proposer: {block.get('proposer')}")
        else:
            print("\n🧱 Latest Block: none found")

        print("\n🧾 Latest Transactions")
        if not transactions:
            print("   No transactions found")
        for tx in transactions:
            tx_hash = tx.get("hash") or tx.get("tx_hash")
            from_addr = tx.get("from") or tx.get("from_address")
            to_addr = tx.get("to") or tx.get("to_address")
            value = tx.get("value")
            status = tx.get("status")
            block_ref = tx.get("block")
            print(f"   - {tx_hash} | block {block_ref} | {status}")
            print(f"     from: {from_addr} -> to: {to_addr} | value: {value}")

        print("\n📈 Receipt Metrics (recent)")
        if not receipts:
            print("   No receipts found")
        else:
            status_counts = {}
            total_units = 0.0
            unit_type = None
            for receipt in receipts:
                status_label = receipt.get("status") or receipt.get("state") or "Unknown"
                status_counts[status_label] = status_counts.get(status_label, 0) + 1
                payload = receipt.get("payload") or {}
                units = payload.get("units")
                if isinstance(units, (int, float)):
                    total_units += float(units)
                    if unit_type is None:
                        unit_type = payload.get("unit_type")

            print(f"   Receipts: {len(receipts)}")
            for status_label, count in status_counts.items():
                print(f"   {status_label}: {count}")
            if total_units:
                unit_suffix = f" {unit_type}" if unit_type else ""
                print(f"   Total Units: {total_units}{unit_suffix}")
    
    elif args.command == "demo":
        print("🎭 Submitting demo inference job...")
        job_id = client.submit_job("inference", {
            "task": "text-generation",
            "model": "llama-2-7b",
            "prompt": "What is AITBC?",
            "parameters": {"max_tokens": 100}
        })
        
        if job_id:
            print(f"✅ Demo job submitted!")
            print(f"   Job ID: {job_id}")
            
            # Check status after a moment
            import time
            time.sleep(2)
            status = client.get_job_status(job_id)
            if status:
                print(f"\n📊 Status: {status['state']}")
                print(f"   Miner: {status.get('assigned_miner_id', 'unassigned')}")

if __name__ == "__main__":
    main()
