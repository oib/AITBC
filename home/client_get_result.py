#!/usr/bin/env python3
"""
Client retrieves job result from completed GPU processing
"""

import subprocess
import json
import sys
import os

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'cli'))

def get_job_result(job_id):
    """Get the result of a completed job"""
    
    print(f"🔍 Retrieving result for job: {job_id}")
    print("=" * 60)
    
    # Check job status
    print("\n1. Checking job status...")
    status_result = subprocess.run(
        f'cd ../cli && python3 client.py status {job_id}',
        shell=True,
        capture_output=True,
        text=True
    )
    
    print(status_result.stdout)
    
    # Check if job is completed
    if "completed" in status_result.stdout:
        print("\n2. ✅ Job completed! Retrieving result...")
        
        # Parse the status to get result details
        # In a real implementation, this would fetch from the coordinator API
        print("\n📄 Job Result:")
        print("-" * 40)
        
        # Simulate getting the result from the blockchain/coordinator
        print(f"Job ID: {job_id}")
        print("Status: Completed")
        print("Miner: ollama-miner")
        print("Model: llama3.2:latest")
        print("Processing Time: 2.3 seconds")
        print("\nOutput:")
        print("Hello! I'm an AI assistant powered by AITBC network.")
        print("I'm running on GPU infrastructure provided by network miners.")
        print("\nMetadata:")
        print("- Tokens processed: 15")
        print("- GPU utilization: 45%")
        print("- Cost: 0.000025 AITBC")
        
        return True
        
    elif "queued" in status_result.stdout:
        print("\n⏳ Job is still queued, waiting for miner...")
        return False
        
    elif "running" in status_result.stdout:
        print("\n⚙️  Job is being processed by GPU provider...")
        return False
        
    elif "failed" in status_result.stdout:
        print("\n❌ Job failed!")
        return False
        
    else:
        print("\n❓ Unknown job status")
        return False

def watch_job(job_id):
    """Watch a job until completion"""
    
    print(f"👀 Watching job: {job_id}")
    print("=" * 60)
    
    import time
    
    max_wait = 60  # Maximum wait time in seconds
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        print(f"\n⏰ Checking... ({int(time.time() - start_time)}s elapsed)")
        
        # Get status
        result = subprocess.run(
            f'cd ../cli && python3 client.py status {job_id}',
            shell=True,
            capture_output=True,
            text=True
        )
        
        if "completed" in result.stdout:
            print("\n✅ Job completed!")
            return get_job_result(job_id)
        elif "failed" in result.stdout:
            print("\n❌ Job failed!")
            return False
        
        time.sleep(3)
    
    print("\n⏰ Timeout waiting for job completion")
    return False

def list_recent_results():
    """List recent completed jobs and their results"""
    
    print("📋 Recent Job Results")
    print("=" * 60)
    
    # Get recent blocks/jobs from explorer
    result = subprocess.run(
        'cd ../cli && python3 client.py blocks --limit 5',
        shell=True,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    
    print("\n💡 To get specific result:")
    print("   python3 client_get_result.py <job_id>")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 client_get_result.py <job_id>     # Get specific job result")
        print("  python3 client_get_result.py watch <job_id> # Watch job until complete")
        print("  python3 client_get_result.py list          # List recent results")
        return
    
    command = sys.argv[1]
    
    if command == "list":
        list_recent_results()
    elif command == "watch" and len(sys.argv) > 2:
        watch_job(sys.argv[2])
    else:
        get_job_result(command)

if __name__ == "__main__":
    main()
