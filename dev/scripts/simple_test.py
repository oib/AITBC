#!/usr/bin/env python3
"""
Simple Multi-Site Test without CLI dependencies
Tests basic connectivity and functionality
"""

import subprocess
import json
import time
import sys

def run_command(cmd, description, timeout=10):
    """Run a command and return success status"""
    try:
        print(f"🔧 {description}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        success = result.returncode == 0
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {status}: {description}")
        
        if not success and result.stderr.strip():
            print(f"   Error: {result.stderr.strip()}")
        
        return success, result.stdout.strip() if success else result.stderr.strip()
    except subprocess.TimeoutExpired:
        print(f"   ❌ TIMEOUT: {description}")
        return False, "Command timed out"
    except Exception as e:
        print(f"   ❌ ERROR: {description} - {str(e)}")
        return False, str(e)

def test_connectivity():
    """Test basic connectivity to all sites"""
    print("\n🌐 Testing Connectivity")
    print("=" * 40)
    
    tests = [
        ("curl -s http://127.0.0.1:18000/v1/health", "aitbc health check"),
        ("curl -s http://127.0.0.1:18001/v1/health", "aitbc1 health check"),
        ("ollama list", "Ollama GPU service"),
        ("ssh aitbc-cascade 'echo SSH_OK'", "SSH to aitbc container"),
        ("ssh aitbc1-cascade 'echo SSH_OK'", "SSH to aitbc1 container"),
    ]
    
    results = []
    for cmd, desc in tests:
        success, output = run_command(cmd, desc)
        results.append((desc, success, output))
    
    return results

def test_marketplace_functionality():
    """Test marketplace functionality"""
    print("\n💰 Testing Marketplace Functionality")
    print("=" * 40)
    
    tests = [
        ("curl -s http://127.0.0.1:18000/v1/marketplace/offers", "aitbc marketplace offers"),
        ("curl -s http://127.0.0.1:18001/v1/marketplace/offers", "aitbc1 marketplace offers"),
        ("curl -s http://127.0.0.1:18000/v1/marketplace/stats", "aitbc marketplace stats"),
        ("curl -s http://127.0.0.1:18001/v1/marketplace/stats", "aitbc1 marketplace stats"),
    ]
    
    results = []
    for cmd, desc in tests:
        success, output = run_command(cmd, desc)
        results.append((desc, success, output))
    
    return results

def test_gpu_services():
    """Test GPU service functionality"""
    print("\n🚀 Testing GPU Services")
    print("=" * 40)
    
    tests = [
        ("ollama list", "List available models"),
        ("curl -X POST http://localhost:11434/api/generate -H 'Content-Type: application/json' -d '{\"model\": \"gemma3:1b\", \"prompt\": \"Test\", \"stream\": false}'", "Direct Ollama inference"),
        ("curl -s http://127.0.0.1:18000/v1/marketplace/offers | jq '.[] | select(.miner_id == \"miner1\")' 2>/dev/null || echo 'No miner1 offers found'", "Check miner1 offers on aitbc"),
    ]
    
    results = []
    for cmd, desc in tests:
        success, output = run_command(cmd, desc, timeout=30)
        results.append((desc, success, output))
    
    return results

def test_container_operations():
    """Test container operations"""
    print("\n🏢 Testing Container Operations")
    print("=" * 40)
    
    tests = [
        ("ssh aitbc-cascade 'free -h | head -2'", "aitbc container memory"),
        ("ssh aitbc-cascade 'df -h | head -3'", "aitbc container disk"),
        ("ssh aitbc1-cascade 'free -h | head -2'", "aitbc1 container memory"),
        ("ssh aitbc1-cascade 'df -h | head -3'", "aitbc1 container disk"),
    ]
    
    results = []
    for cmd, desc in tests:
        success, output = run_command(cmd, desc)
        results.append((desc, success, output))
    
    return results

def test_user_configurations():
    """Test user configurations"""
    print("\n👤 Testing User Configurations")
    print("=" * 40)
    
    tests = [
        ("ls -la /home/oib/windsurf/aitbc/home/miner1/", "miner1 directory"),
        ("ls -la /home/oib/windsurf/aitbc/home/client1/", "client1 directory"),
        ("cat /home/oib/windsurf/aitbc/home/miner1/miner_wallet.json 2>/dev/null || echo 'No miner wallet'", "miner1 wallet"),
        ("cat /home/oib/windsurf/aitbc/home/client1/client_wallet.json 2>/dev/null || echo 'No client wallet'", "client1 wallet"),
    ]
    
    results = []
    for cmd, desc in tests:
        success, output = run_command(cmd, desc)
        results.append((desc, success, output))
    
    return results

def generate_summary(all_results):
    """Generate test summary"""
    print("\n📊 Test Summary")
    print("=" * 40)
    
    total_tests = sum(len(results) for results in all_results.values())
    passed_tests = sum(1 for results in all_results.values() for _, success, _ in results if success)
    failed_tests = total_tests - passed_tests
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
    print(f"Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
    
    if failed_tests > 0:
        print("\n❌ Failed Tests:")
        for category, results in all_results.items():
            for desc, success, output in results:
                if not success:
                    print(f"  • {desc}: {output}")
    
    print(f"\n🎯 Test Categories:")
    for category, results in all_results.items():
        passed = sum(1 for _, success, _ in results if success)
        total = len(results)
        print(f"  • {category}: {passed}/{total}")
    
    return failed_tests == 0

def main():
    """Main test execution"""
    print("🚀 Simple Multi-Site AITBC Test Suite")
    print("Testing basic functionality without CLI dependencies")
    
    all_results = {}
    
    # Run all test categories
    all_results["Connectivity"] = test_connectivity()
    all_results["Marketplace"] = test_marketplace_functionality()
    all_results["GPU Services"] = test_gpu_services()
    all_results["Container Operations"] = test_container_operations()
    all_results["User Configurations"] = test_user_configurations()
    
    # Generate summary
    success = generate_summary(all_results)
    
    # Save results
    results_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": {category: [{"test": desc, "success": success, "output": output} for desc, success, output in results] 
                   for category, results in all_results.items()}
    }
    
    with open("/home/oib/windsurf/aitbc/simple_test_results.json", "w") as f:
        json.dump(results_data, f, indent=2)
    
    print(f"\n📄 Results saved to: /home/oib/windsurf/aitbc/simple_test_results.json")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
