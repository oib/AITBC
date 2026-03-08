#!/usr/bin/env python3
"""
Simple Performance Test with Debugging and Timeout
"""

import time
import requests
import signal
import sys
from typing import Dict, List

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

def test_endpoint_with_timeout(url: str, method: str = "GET", data: Dict = None, timeout: int = 5) -> Dict:
    """Test single endpoint with timeout and debugging"""
    print(f"🔍 Testing {method} {url}")
    
    # Set timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)
    
    try:
        start_time = time.time()
        
        if method == "GET":
            response = requests.get(url, timeout=timeout)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=timeout)
        
        end_time = time.time()
        signal.alarm(0)  # Cancel timeout
        
        response_time_ms = (end_time - start_time) * 1000
        
        result = {
            "url": url,
            "method": method,
            "status_code": response.status_code,
            "response_time_ms": response_time_ms,
            "success": True,
            "error": None
        }
        
        print(f"✅ Status: {response.status_code}")
        print(f"⏱️  Response Time: {response_time_ms:.2f}ms")
        print(f"📄 Response Size: {len(response.content)} bytes")
        
        return result
        
    except TimeoutError as e:
        signal.alarm(0)
        print(f"❌ Timeout: {e}")
        return {
            "url": url,
            "method": method,
            "status_code": None,
            "response_time_ms": timeout * 1000,
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        signal.alarm(0)
        print(f"❌ Error: {e}")
        return {
            "url": url,
            "method": method,
            "status_code": None,
            "response_time_ms": 0,
            "success": False,
            "error": str(e)
        }

def run_performance_tests():
    """Run performance tests with debugging"""
    print("🎯 AITBC GPU Marketplace Performance Test")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    results = []
    
    # Test 1: Health endpoint
    print("\n1️⃣ Health Endpoint Test")
    result = test_endpoint_with_timeout(f"{base_url}/health", timeout=3)
    results.append(result)
    
    # Test 2: GPU List endpoint  
    print("\n2️⃣ GPU List Endpoint Test")
    result = test_endpoint_with_timeout(f"{base_url}/v1/marketplace/gpu/list", timeout=5)
    results.append(result)
    
    # Test 3: GPU Booking endpoint
    print("\n3️⃣ GPU Booking Endpoint Test")
    booking_data = {"duration_hours": 1}
    result = test_endpoint_with_timeout(
        f"{base_url}/v1/marketplace/gpu/gpu_c5be877c/book", 
        "POST", 
        booking_data, 
        timeout=10
    )
    results.append(result)
    
    # Test 4: GPU Release endpoint
    print("\n4️⃣ GPU Release Endpoint Test")
    result = test_endpoint_with_timeout(
        f"{base_url}/v1/marketplace/gpu/gpu_c5be877c/release", 
        "POST", 
        timeout=10
    )
    results.append(result)
    
    # Summary
    print("\n📊 PERFORMANCE SUMMARY")
    print("=" * 50)
    
    successful_tests = sum(1 for r in results if r["success"])
    total_tests = len(results)
    
    print(f"✅ Successful Tests: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    
    print(f"\n📈 Response Times:")
    for result in results:
        if result["success"]:
            status = "🟢" if result["response_time_ms"] < 100 else "🟡" if result["response_time_ms"] < 200 else "🔴"
            endpoint = result['url'].split('/')[-1] if '/' in result['url'] else result['url']
            print(f"   {status} {result['method']} {endpoint}: {result['response_time_ms']:.2f}ms")
        else:
            endpoint = result['url'].split('/')[-1] if '/' in result['url'] else result['url']
            print(f"   ❌ {result['method']} {endpoint}: {result['error']}")
    
    # Performance grade
    successful_times = [r["response_time_ms"] for r in results if r["success"]]
    if successful_times:
        avg_response_time = sum(successful_times) / len(successful_times)
        if avg_response_time < 50:
            grade = "🟢 EXCELLENT"
        elif avg_response_time < 100:
            grade = "🟡 GOOD"
        elif avg_response_time < 200:
            grade = "🟠 FAIR"
        else:
            grade = "🔴 POOR"
        
        print(f"\n🎯 Overall Performance: {grade}")
        print(f"📊 Average Response Time: {avg_response_time:.2f}ms")
    
    print(f"\n✅ Performance testing complete!")

if __name__ == "__main__":
    try:
        run_performance_tests()
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
