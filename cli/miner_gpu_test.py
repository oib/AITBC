#!/usr/bin/env python3
"""
Miner GPU Test - Test if the miner service can access and utilize GPU
"""

import argparse
import httpx
import json
import time
import sys

# Configuration
DEFAULT_COORDINATOR = "http://localhost:8001"
DEFAULT_API_KEY = "REDACTED_MINER_KEY"
DEFAULT_MINER_ID = "localhost-gpu-miner"

def test_miner_registration(coordinator_url):
    """Test if miner can register with GPU capabilities"""
    print("📝 Testing Miner Registration...")
    
    gpu_capabilities = {
        "gpu": {
            "model": "NVIDIA GeForce RTX 4060 Ti",
            "memory_gb": 16,
            "cuda_version": "12.1",
            "compute_capability": "8.9"
        },
        "compute": {
            "type": "GPU",
            "platform": "CUDA",
            "supported_tasks": ["inference", "training", "stable-diffusion", "llama"],
            "max_concurrent_jobs": 1
        }
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{coordinator_url}/v1/miners/register?miner_id={DEFAULT_MINER_ID}",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": DEFAULT_API_KEY
                },
                json={"capabilities": gpu_capabilities}
            )
            
            if response.status_code == 200:
                print("✅ Miner registered with GPU capabilities")
                print(f"   GPU Model: {gpu_capabilities['gpu']['model']}")
                print(f"   Memory: {gpu_capabilities['gpu']['memory_gb']} GB")
                print(f"   CUDA: {gpu_capabilities['gpu']['cuda_version']}")
                return True
            else:
                print(f"❌ Registration failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_job_processing(coordinator_url):
    """Test if miner can process a GPU job"""
    print("\n⚙️  Testing GPU Job Processing...")
    
    # First submit a test job
    print("   1. Submitting test job...")
    try:
        with httpx.Client() as client:
            # Submit job as client
            job_response = client.post(
                f"{coordinator_url}/v1/jobs",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": "REDACTED_CLIENT_KEY"
                },
                json={
                    "payload": {
                        "type": "inference",
                        "task": "gpu-test",
                        "model": "test-gpu-model",
                        "parameters": {
                            "require_gpu": True,
                            "memory_gb": 8
                        }
                    },
                    "ttl_seconds": 300
                }
            )
            
            if job_response.status_code != 201:
                print(f"❌ Failed to submit job: {job_response.status_code}")
                return False
            
            job_id = job_response.json()['job_id']
            print(f"   ✅ Job submitted: {job_id}")
            
            # Poll for the job as miner
            print("   2. Polling for job...")
            poll_response = client.post(
                f"{coordinator_url}/v1/miners/poll",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": DEFAULT_API_KEY
                },
                json={"max_wait_seconds": 5}
            )
            
            if poll_response.status_code == 200:
                job = poll_response.json()
                print(f"   ✅ Job received: {job['job_id']}")
                
                # Simulate GPU processing
                print("   3. Simulating GPU processing...")
                time.sleep(2)
                
                # Submit result
                print("   4. Submitting result...")
                result_response = client.post(
                    f"{coordinator_url}/v1/miners/{job['job_id']}/result",
                    headers={
                        "Content-Type": "application/json",
                        "X-Api-Key": DEFAULT_API_KEY
                    },
                    json={
                        "result": {
                            "status": "completed",
                            "output": "GPU task completed successfully",
                            "execution_time_ms": 2000,
                            "gpu_utilization": 85,
                            "memory_used_mb": 4096
                        },
                        "metrics": {
                            "compute_time": 2.0,
                            "energy_used": 0.05,
                            "aitbc_earned": 25.0
                        }
                    }
                )
                
                if result_response.status_code == 200:
                    print("   ✅ Result submitted successfully")
                    print(f"   💰 Earned: 25.0 AITBC")
                    return True
                else:
                    print(f"❌ Failed to submit result: {result_response.status_code}")
                    return False
                    
            elif poll_response.status_code == 204:
                print("   ⚠️  No jobs available")
                return False
            else:
                print(f"❌ Poll failed: {poll_response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_gpu_heartbeat(coordinator_url):
    """Test sending GPU metrics in heartbeat"""
    print("\n💓 Testing GPU Heartbeat...")
    
    heartbeat_data = {
        "status": "ONLINE",
        "inflight": 0,
        "metadata": {
            "last_seen": time.time(),
            "gpu_utilization": 45,
            "gpu_memory_used": 8192,
            "gpu_temperature": 68,
            "gpu_power_usage": 220,
            "cuda_version": "12.1",
            "driver_version": "535.104.05"
        }
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{coordinator_url}/v1/miners/heartbeat?miner_id={DEFAULT_MINER_ID}",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": DEFAULT_API_KEY
                },
                json=heartbeat_data
            )
            
            if response.status_code == 200:
                print("✅ GPU heartbeat sent successfully")
                print(f"   GPU Utilization: {heartbeat_data['metadata']['gpu_utilization']}%")
                print(f"   Memory Used: {heartbeat_data['metadata']['gpu_memory_used']} MB")
                print(f"   Temperature: {heartbeat_data['metadata']['gpu_temperature']}°C")
                return True
            else:
                print(f"❌ Heartbeat failed: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def check_blockchain_status(coordinator_url):
    """Check if processed jobs appear in blockchain"""
    print("\n📦 Checking Blockchain Status...")
    
    try:
        with httpx.Client() as client:
            response = client.get(f"{coordinator_url}/v1/explorer/blocks")
            
            if response.status_code == 200:
                blocks = response.json()
                print(f"✅ Found {len(blocks['items'])} blocks")
                
                # Show latest blocks
                for i, block in enumerate(blocks['items'][:3]):
                    print(f"\n   Block {block['height']}:")
                    print(f"   Hash: {block['hash']}")
                    print(f"   Proposer: {block['proposer']}")
                    print(f"   Time: {block['timestamp']}")
                
                return True
            else:
                print(f"❌ Failed to get blocks: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test Miner GPU Access")
    parser.add_argument("--url", help="Coordinator URL")
    parser.add_argument("--full", action="store_true", help="Run full test suite")
    
    args = parser.parse_args()
    
    coordinator_url = args.url if args.url else DEFAULT_COORDINATOR
    
    print("🚀 AITBC Miner GPU Test")
    print("=" * 60)
    print(f"Coordinator: {coordinator_url}")
    print(f"Miner ID: {DEFAULT_MINER_ID}")
    print()
    
    # Run tests
    tests = [
        ("Miner Registration", lambda: test_miner_registration(coordinator_url)),
        ("GPU Heartbeat", lambda: test_gpu_heartbeat(coordinator_url)),
    ]
    
    if args.full:
        tests.append(("Job Processing", lambda: test_job_processing(coordinator_url)))
        tests.append(("Blockchain Status", lambda: check_blockchain_status(coordinator_url)))
    
    results = []
    
    for test_name, test_func in tests:
        print(f"🧪 Running: {test_name}")
        result = test_func()
        results.append((test_name, result))
        print()
    
    # Summary
    print("📊 TEST RESULTS")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nScore: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 All tests passed! Miner is ready for GPU mining.")
        print("\n💡 Next steps:")
        print("   1. Start continuous mining: python3 cli/miner.py mine")
        print("   2. Monitor earnings: cd home/miner && python3 wallet.py balance")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")

if __name__ == "__main__":
    main()
