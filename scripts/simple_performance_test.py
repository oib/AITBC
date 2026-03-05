#!/usr/bin/env python3
"""
Simple Performance Testing for AITBC Platform
"""

import time
import requests
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

class SimplePerformanceTester:
    def __init__(self, base_url="https://aitbc.bubuit.net/api/v1"):
        self.base_url = base_url
        self.api_key = "test_key_16_characters"
        
    def test_endpoint(self, method, endpoint, **kwargs):
        """Test a single endpoint"""
        start_time = time.time()
        
        headers = kwargs.pop('headers', {})
        headers['X-Api-Key'] = self.api_key
        
        try:
            response = requests.request(method, f"{self.base_url}{endpoint}", 
                                      headers=headers, timeout=10, **kwargs)
            end_time = time.time()
            
            return {
                'endpoint': endpoint,
                'method': method,
                'status_code': response.status_code,
                'response_time': end_time - start_time,
                'success': response.status_code < 400,
                'content_length': len(response.text)
            }
        except Exception as e:
            end_time = time.time()
            return {
                'endpoint': endpoint,
                'method': method,
                'status_code': 0,
                'response_time': end_time - start_time,
                'success': False,
                'error': str(e)
            }
    
    def load_test_endpoint(self, method, endpoint, concurrent_users=5, requests_per_user=3, **kwargs):
        """Load test an endpoint"""
        print(f"🧪 Testing {method} {endpoint} - {concurrent_users} users × {requests_per_user} requests")
        
        def make_request():
            return self.test_endpoint(method, endpoint, **kwargs)
        
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = []
            for _ in range(concurrent_users * requests_per_user):
                future = executor.submit(make_request)
                futures.append(future)
            
            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
        
        successful_results = [r for r in results if r['success']]
        response_times = [r['response_time'] for r in successful_results]
        
        return {
            'endpoint': endpoint,
            'total_requests': len(results),
            'successful_requests': len(successful_results),
            'failed_requests': len(results) - len(successful_results),
            'success_rate': len(successful_results) / len(results) * 100 if results else 0,
            'avg_response_time': statistics.mean(response_times) if response_times else 0,
            'min_response_time': min(response_times) if response_times else 0,
            'max_response_time': max(response_times) if response_times else 0,
            'median_response_time': statistics.median(response_times) if response_times else 0,
        }
    
    def run_tests(self):
        """Run performance tests"""
        print("🚀 AITBC Platform Performance Tests")
        print("=" * 50)
        
        test_cases = [
            # Health check
            {'method': 'GET', 'endpoint': '/health', 'users': 10, 'requests': 5},
            
            # Client endpoints
            {'method': 'GET', 'endpoint': '/client/jobs', 'users': 5, 'requests': 3},
            
            # Miner endpoints
            {'method': 'POST', 'endpoint': '/miners/register', 'users': 3, 'requests': 2,
             'json': {'capabilities': {'gpu': {'model': 'RTX 4090'}}},
             'headers': {'Content-Type': 'application/json', 'X-Miner-ID': 'perf-test-miner'}},
        ]
        
        results = []
        
        for test_case in test_cases:
            method = test_case.pop('method')
            endpoint = test_case.pop('endpoint')
            
            result = self.load_test_endpoint(method, endpoint, **test_case)
            results.append(result)
            
            # Print results
            status = "✅" if result['success_rate'] >= 80 else "⚠️" if result['success_rate'] >= 50 else "❌"
            print(f"{status} {method} {endpoint}:")
            print(f"   Success Rate: {result['success_rate']:.1f}%")
            print(f"   Avg Response: {result['avg_response_time']:.3f}s")
            print(f"   Requests: {result['successful_requests']}/{result['total_requests']}")
            print()
        
        # Generate report
        self.generate_report(results)
        return results
    
    def generate_report(self, results):
        """Generate performance report"""
        print("📋 PERFORMANCE REPORT")
        print("=" * 50)
        
        total_requests = sum(r['total_requests'] for r in results)
        total_successful = sum(r['successful_requests'] for r in results)
        overall_success_rate = (total_successful / total_requests * 100) if total_requests > 0 else 0
        
        print(f"📊 Overall:")
        print(f"   Total Requests: {total_requests}")
        print(f"   Successful: {total_successful}")
        print(f"   Success Rate: {overall_success_rate:.1f}%")
        print()
        
        print(f"🎯 Endpoint Performance:")
        for result in results:
            status = "✅" if result['success_rate'] >= 80 else "⚠️" if result['success_rate'] >= 50 else "❌"
            print(f"   {status} {result['method']} {result['endpoint']}")
            print(f"      Success: {result['success_rate']:.1f}% | "
                  f"Avg: {result['avg_response_time']:.3f}s | "
                  f"Requests: {result['successful_requests']}/{result['total_requests']}")
        
        print()
        print("💡 Recommendations:")
        
        if overall_success_rate >= 80:
            print("   🎉 Good performance - ready for production!")
        else:
            print("   ⚠️  Performance issues detected - review endpoints")
        
        slow_endpoints = [r for r in results if r['avg_response_time'] > 1.0]
        if slow_endpoints:
            print("   🐌 Slow endpoints:")
            for r in slow_endpoints:
                print(f"      - {r['endpoint']} ({r['avg_response_time']:.3f}s)")

if __name__ == "__main__":
    tester = SimplePerformanceTester()
    results = tester.run_tests()
    
    # Exit code based on performance
    avg_success_rate = statistics.mean([r['success_rate'] for r in results])
    if avg_success_rate >= 80:
        print("\n✅ PERFORMANCE TESTS PASSED")
        exit(0)
    else:
        print("\n⚠️ PERFORMANCE TESTS NEED REVIEW")
        exit(1)
