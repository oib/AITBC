#!/usr/bin/env python3
"""
AITBC Client CLI Tool - Enhanced version with output formatting
"""

import argparse
import httpx
import json
import sys
import yaml
from datetime import datetime
from typing import Optional, Dict, Any
from tabulate import tabulate

# Configuration
DEFAULT_COORDINATOR = "http://127.0.0.1:18000"
DEFAULT_API_KEY = "${CLIENT_API_KEY}"


class OutputFormatter:
    """Handle different output formats"""
    
    @staticmethod
    def format(data: Any, format_type: str = "table") -> str:
        """Format data according to specified type"""
        if format_type == "json":
            return json.dumps(data, indent=2, default=str)
        elif format_type == "yaml":
            return yaml.dump(data, default_flow_style=False, sort_keys=False)
        elif format_type == "table":
            return OutputFormatter._format_table(data)
        else:
            return str(data)
    
    @staticmethod
    def _format_table(data: Any) -> str:
        """Format data as table"""
        if isinstance(data, dict):
            # Simple key-value table
            rows = [[k, v] for k, v in data.items()]
            return tabulate(rows, headers=["Key", "Value"], tablefmt="grid")
        elif isinstance(data, list) and data:
            if all(isinstance(item, dict) for item in data):
                # Table from list of dicts
                headers = list(data[0].keys())
                rows = [[item.get(h, "") for h in headers] for item in data]
                return tabulate(rows, headers=headers, tablefmt="grid")
            else:
                # Simple list
                return "\n".join(f"• {item}" for item in data)
        else:
            return str(data)


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
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
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
            response = self.client.get(
                f"{self.coordinator_url}/v1/explorer/blocks",
                params={"limit": limit},
                headers={"X-Api-Key": self.api_key}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error getting blocks: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def list_transactions(self, limit: int = 10) -> Optional[list]:
        """List recent transactions"""
        try:
            response = self.client.get(
                f"{self.coordinator_url}/v1/explorer/transactions",
                params={"limit": limit},
                headers={"X-Api-Key": self.api_key}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error getting transactions: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def list_receipts(self, limit: int = 10, job_id: str = None) -> Optional[list]:
        """List job receipts"""
        try:
            params = {"limit": limit}
            if job_id:
                params["job_id"] = job_id
                
            response = self.client.get(
                f"{self.coordinator_url}/v1/explorer/receipts",
                params=params,
                headers={"X-Api-Key": self.api_key}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error getting receipts: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/jobs/{job_id}/cancel",
                headers={"X-Api-Key": self.api_key}
            )
            
            if response.status_code == 200:
                return True
            else:
                print(f"❌ Error cancelling job: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="AITBC Client CLI Tool")
    parser.add_argument("--url", default=DEFAULT_COORDINATOR, help="Coordinator URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--output", choices=["table", "json", "yaml"], 
                       default="table", help="Output format")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Submit command
    submit_parser = subparsers.add_parser("submit", help="Submit a job")
    submit_parser.add_argument("type", help="Job type (e.g., inference, training)")
    submit_parser.add_argument("--prompt", help="Prompt for inference jobs")
    submit_parser.add_argument("--model", help="Model name")
    submit_parser.add_argument("--ttl", type=int, default=900, help="Time to live (seconds)")
    submit_parser.add_argument("--file", type=argparse.FileType('r'), 
                              help="Submit job from JSON file")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check job status")
    status_parser.add_argument("job_id", help="Job ID")
    
    # Blocks command
    blocks_parser = subparsers.add_parser("blocks", help="List recent blocks")
    blocks_parser.add_argument("--limit", type=int, default=10, help="Number of blocks")
    
    # Browser command
    browser_parser = subparsers.add_parser("browser", help="Browse blockchain")
    browser_parser.add_argument("--block-limit", type=int, default=5, help="Block limit")
    browser_parser.add_argument("--tx-limit", type=int, default=10, help="Transaction limit")
    browser_parser.add_argument("--receipt-limit", type=int, default=10, help="Receipt limit")
    browser_parser.add_argument("--job-id", help="Filter by job ID")
    
    # Cancel command
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a job")
    cancel_parser.add_argument("job_id", help="Job ID")
    
    # Receipts command
    receipts_parser = subparsers.add_parser("receipts", help="List receipts")
    receipts_parser.add_argument("--limit", type=int, default=10, help="Number of receipts")
    receipts_parser.add_argument("--job-id", help="Filter by job ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Create client
    client = AITBCClient(args.url, args.api_key)
    
    # Execute command
    if args.command == "submit":
        # Build job data
        if args.file:
            try:
                task_data = json.load(args.file)
            except Exception as e:
                print(f"❌ Error reading job file: {e}")
                sys.exit(1)
        else:
            task_data = {"type": args.type}
            if args.prompt:
                task_data["prompt"] = args.prompt
            if args.model:
                task_data["model"] = args.model
        
        # Submit job
        job_id = client.submit_job(args.type, task_data, args.ttl)
        
        if job_id:
            result = {
                "status": "success",
                "job_id": job_id,
                "message": "Job submitted successfully",
                "track_command": f"python3 cli/client_enhanced.py status {job_id}"
            }
            print(OutputFormatter.format(result, args.output))
            sys.exit(0)
        else:
            sys.exit(1)
    
    elif args.command == "status":
        status = client.get_job_status(args.job_id)
        
        if status:
            print(OutputFormatter.format(status, args.output))
            sys.exit(0)
        else:
            sys.exit(1)
    
    elif args.command == "blocks":
        blocks = client.list_blocks(args.limit)
        
        if blocks:
            print(OutputFormatter.format(blocks, args.output))
            sys.exit(0)
        else:
            sys.exit(1)
    
    elif args.command == "browser":
        blocks = client.list_blocks(args.block_limit) or []
        transactions = client.list_transactions(args.tx_limit) or []
        receipts = client.list_receipts(args.receipt_limit, job_id=args.job_id) or []
        
        result = {
            "latest_block": blocks[0] if blocks else None,
            "recent_transactions": transactions,
            "recent_receipts": receipts
        }
        
        print(OutputFormatter.format(result, args.output))
        sys.exit(0)
    
    elif args.command == "cancel":
        if client.cancel_job(args.job_id):
            result = {
                "status": "success",
                "job_id": args.job_id,
                "message": "Job cancelled successfully"
            }
            print(OutputFormatter.format(result, args.output))
            sys.exit(0)
        else:
            sys.exit(1)
    
    elif args.command == "receipts":
        receipts = client.list_receipts(args.limit, args.job_id)
        
        if receipts:
            print(OutputFormatter.format(receipts, args.output))
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
