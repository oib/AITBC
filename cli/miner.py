#!/usr/bin/env python3
"""
AITBC Miner CLI Tool - Register, poll for jobs, and submit results
"""

import argparse
import httpx
import json
import sys
import time
from datetime import datetime
from typing import Optional

# Configuration
DEFAULT_COORDINATOR = "http://localhost:8001"
DEFAULT_API_KEY = "${MINER_API_KEY}"
DEFAULT_MINER_ID = "cli-miner"

class AITBCMiner:
    def __init__(self, coordinator_url: str, api_key: str, miner_id: str):
        self.coordinator_url = coordinator_url
        self.api_key = api_key
        self.miner_id = miner_id
        self.client = httpx.Client()
        
    def register(self, capabilities: dict) -> bool:
        """Register miner with coordinator"""
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/miners/register?miner_id={self.miner_id}",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json={"capabilities": capabilities}
            )
            
            if response.status_code == 200:
                print(f"✅ Miner {self.miner_id} registered successfully")
                return True
            else:
                print(f"❌ Registration failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def poll_job(self, max_wait: int = 5) -> Optional[dict]:
        """Poll for available jobs"""
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/miners/poll",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json={"max_wait_seconds": max_wait}
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 204:
                return None
            else:
                print(f"❌ Poll failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def submit_result(self, job_id: str, result: dict, metrics: dict = None) -> bool:
        """Submit job result"""
        payload = {
            "result": result
        }
        if metrics:
            payload["metrics"] = metrics
        
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/miners/{job_id}/result",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json=payload
            )
            
            if response.status_code == 200:
                print(f"✅ Result submitted for job {job_id}")
                return True
            else:
                print(f"❌ Submit failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def send_heartbeat(self) -> bool:
        """Send heartbeat to coordinator"""
        heartbeat_data = {
            "status": "ONLINE",
            "inflight": 0,
            "metadata": {
                "last_seen": datetime.utcnow().isoformat(),
                "gpu_utilization": 75,
                "gpu_memory_used": 8000,
                "gpu_temperature": 65
            }
        }
        
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/miners/heartbeat?miner_id={self.miner_id}",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json=heartbeat_data
            )
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"❌ Heartbeat error: {e}")
            return False
    
    def mine_continuous(self, max_jobs: int = None, simulate_work: bool = True):
        """Continuously mine jobs"""
        print(f"⛏️  Starting continuous mining...")
        print(f"   Miner ID: {self.miner_id}")
        print(f"   Max jobs: {max_jobs or 'unlimited'}")
        print()
        
        jobs_completed = 0
        
        try:
            while max_jobs is None or jobs_completed < max_jobs:
                # Poll for job
                print("🔍 Polling for jobs...")
                job = self.poll_job()
                
                if job:
                    print(f"✅ Got job: {job['job_id']}")
                    print(f"   Type: {job['payload'].get('type', 'unknown')}")
                    
                    if simulate_work:
                        print("⚙️  Processing job...")
                        time.sleep(2)  # Simulate work
                    
                    # Submit result
                    result = {
                        "status": "completed",
                        "output": f"Job {job['job_id']} processed by {self.miner_id}",
                        "execution_time_ms": 2000,
                        "miner_id": self.miner_id
                    }
                    
                    metrics = {
                        "compute_time": 2.0,
                        "energy_used": 0.1,
                        "aitbc_earned": 10.0
                    }
                    
                    if self.submit_result(job['job_id'], result, metrics):
                        jobs_completed += 1
                        print(f"💰 Earned 10 AITBC!")
                        print(f"   Total jobs completed: {jobs_completed}")
                        
                        # Check if this job is now a block with proposer
                        print("🔍 Checking block status...")
                        time.sleep(1)
                else:
                    print("💤 No jobs available, sending heartbeat...")
                    self.send_heartbeat()
                
                print("-" * 50)
                time.sleep(3)  # Wait before next poll
                
        except KeyboardInterrupt:
            print("\n⏹️  Mining stopped by user")
            print(f"   Total jobs completed: {jobs_completed}")

def main():
    parser = argparse.ArgumentParser(description="AITBC Miner CLI")
    parser.add_argument("--url", default=DEFAULT_COORDINATOR, help="Coordinator URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--miner-id", default=DEFAULT_MINER_ID, help="Miner ID")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Register command
    register_parser = subparsers.add_parser("register", help="Register miner")
    register_parser.add_argument("--gpu", default="RTX 4060 Ti", help="GPU model")
    register_parser.add_argument("--memory", type=int, default=16, help="GPU memory GB")
    
    # Poll command
    poll_parser = subparsers.add_parser("poll", help="Poll for a job")
    poll_parser.add_argument("--wait", type=int, default=5, help="Max wait seconds")
    
    # Mine command
    mine_parser = subparsers.add_parser("mine", help="Mine continuously")
    mine_parser.add_argument("--jobs", type=int, help="Max jobs to complete")
    mine_parser.add_argument("--no-simulate", action="store_true", help="Don't simulate work")
    
    # Heartbeat command
    heartbeat_parser = subparsers.add_parser("heartbeat", help="Send heartbeat")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    miner = AITBCMiner(args.url, args.api_key, args.miner_id)
    
    if args.command == "register":
        capabilities = {
            "gpu": {
                "model": args.gpu,
                "memory_gb": args.memory,
                "cuda_version": "12.4"
            },
            "compute": {
                "type": "GPU",
                "platform": "CUDA",
                "supported_tasks": ["inference", "training"],
                "max_concurrent_jobs": 1
            }
        }
        miner.register(capabilities)
    
    elif args.command == "poll":
        print(f"🔍 Polling for jobs (max wait: {args.wait}s)...")
        job = miner.poll_job(args.wait)
        
        if job:
            print(f"✅ Received job:")
            print(json.dumps(job, indent=2))
        else:
            print("💤 No jobs available")
    
    elif args.command == "mine":
        miner.mine_continuous(args.jobs, not args.no_simulate)
    
    elif args.command == "heartbeat":
        if miner.send_heartbeat():
            print("💓 Heartbeat sent successfully")
        else:
            print("❌ Heartbeat failed")

if __name__ == "__main__":
    main()
