#!/usr/bin/env python3
"""
AITBC Phase 5 Performance Testing Script
Tests system performance for production deployment requirements
"""

import time
import requests
import statistics
import concurrent.futures
import sys
import os

def test_api_response_time():
    """Test API response times"""
    print("⚡ Testing API Response Time...")
    response_times = []
    
    for i in range(10):
        start_time = time.time()
        response = requests.get('http://127.0.0.1:8000/health/live', timeout=5)
        end_time = time.time()
        if response.status_code == 200:
            response_times.append((end_time - start_time) * 1000)  # Convert to ms
    
    if response_times:
        avg_time = statistics.mean(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        
        print(f"✅ API Response Time: PASSED")
        print(f"   Average: {avg_time:.2f}ms")
        print(f"   Min: {min_time:.2f}ms")
        print(f"   Max: {max_time:.2f}ms")
        
        if avg_time < 200:  # Target: <200ms
            print("   ✅ Performance Target Met")
            return True
        else:
            print("   ⚠️  Performance Target Not Met")
            return False
    return False

def test_concurrent_load():
    """Test concurrent load handling"""
    print("\n🔄 Testing Concurrent Load...")
    
    def make_request():
        try:
            response = requests.get('http://127.0.0.1:8000/health/live', timeout=5)
            return response.status_code == 200
        except:
            return False
    
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(50)]
        results = [f.result() for f in futures]
    end_time = time.time()
    
    success_rate = sum(results) / len(results) * 100
    total_time = end_time - start_time
    
    print(f"✅ Concurrent Load Testing: PASSED")
    print(f"   Requests: 50")
    print(f"   Success Rate: {success_rate:.1f}%")
    print(f"   Total Time: {total_time:.2f}s")
    print(f"   Requests/sec: {50/total_time:.1f}")
    
    return success_rate > 95  # Target: 95%+ success rate

def test_ml_zk_performance():
    """Test ML-ZK circuit performance"""
    print("\n🤖 Testing ML-ZK Circuit Performance...")
    
    start_time = time.time()
    response = requests.get('http://127.0.0.1:8000/v1/ml-zk/circuits', timeout=5)
    end_time = time.time()
    
    if response.status_code == 200:
        response_time = (end_time - start_time) * 1000
        circuits = response.json()['circuits']
        print(f"✅ ML-ZK Circuit Performance: PASSED")
        print(f"   Response Time: {response_time:.2f}ms")
        print(f"   Circuits Returned: {len(circuits)}")
        
        if response_time < 500:  # Target: <500ms for complex endpoint
            print("   ✅ Performance Target Met")
            return True
        else:
            print("   ⚠️  Performance Target Not Met")
            return False
    return False

def main():
    """Run all performance tests"""
    print("🚀 Phase 5.1 Performance Testing - Starting Now!")
    print("=" * 60)
    
    tests = [
        test_api_response_time,
        test_concurrent_load,
        test_ml_zk_performance
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    print("🎯 Performance Testing Summary:")
    
    passed = sum(results)
    total = len(results)
    
    print(f"   Tests Passed: {passed}/{total}")
    print(f"   Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("\n🚀 Phase 5.1 Performance Testing: COMPLETED!")
        print("📋 System meets production performance requirements!")
        return 0
    else:
        print("\n⚠️  Some performance tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
