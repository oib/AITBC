#!/usr/bin/env python3
"""
Performance Testing Suite for AITBC Platform
Tests API endpoints, load handling, and system performance
"""

import asyncio
import aiohttp
import time
import json
import statistics
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys

class PerformanceTester:
    def __init__(self, base_url: str = "https://aitbc.bubuit.net/api/v1"):
        self.base_url = base_url
        self.api_key = "test_key_16_characters"
        self.results = []
        
    async def single_request(self, session: aiohttp.ClientSession, 
                           method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Execute a single API request and measure performance"""
        start_time = time.time()
        
        headers = kwargs.pop('headers', {})
        headers['X-Api-Key'] = self.api_key
        
        try:
            async with session.request(method, f"{self.base_url}{endpoint}", 
                                      headers=headers, **kwargs) as response:
                content = await response.text()
                end_time = time.time()
                
                return {
                    'endpoint': endpoint,
                    'method': method,
                    'status_code': response.status,
                    'response_time': end_time - start_time,
                    'content_length': len(content),
                    'success': response.status < 400
                }
        except Exception as e:
            end_time = time.time()
            return {
                'endpoint': endpoint,
                'method': method,
                'status_code': 0,
                'response_time': end_time - start_time,
                'content_length': 0,
                'success': False,
                'error': str(e)
            }
    
    async def load_test_endpoint(self, endpoint: str, method: str = "GET", 
                               concurrent_users: int = 10, requests_per_user: int = 5,
                               **kwargs) -> Dict[str, Any]:
        """Perform load testing on a specific endpoint"""
        print(f"🧪 Load testing {method} {endpoint} - {concurrent_users} users × {requests_per_user} requests")
        
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=100)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []
            for user in range(concurrent_users):
                for req in range(requests_per_user):
                    task = self.single_request(session, method, endpoint, **kwargs)
                    tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and calculate metrics
            valid_results = [r for r in results if isinstance(r, dict)]
            successful_results = [r for r in valid_results if r['success']]
            
            response_times = [r['response_time'] for r in successful_results]
            
            return {
                'endpoint': endpoint,
                'total_requests': len(valid_results),
                'successful_requests': len(successful_results),
                'failed_requests': len(valid_results) - len(successful_results),
                'success_rate': len(successful_results) / len(valid_results) * 100 if valid_results else 0,
                'avg_response_time': statistics.mean(response_times) if response_times else 0,
                'min_response_time': min(response_times) if response_times else 0,
                'max_response_time': max(response_times) if response_times else 0,
                'median_response_time': statistics.median(response_times) if response_times else 0,
                'p95_response_time': statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else 0,
                'requests_per_second': len(successful_results) / (max(response_times) - min(response_times)) if len(response_times) > 1 else 0
            }
    
    async def run_performance_tests(self):
        """Run comprehensive performance tests"""
        print("🚀 Starting AITBC Platform Performance Tests")
        print("=" * 60)
        
        test_endpoints = [
            # Health check (baseline)
            {'endpoint': '/health', 'method': 'GET', 'users': 20, 'requests': 10},
            
            # Client endpoints
            {'endpoint': '/client/jobs', 'method': 'GET', 'users': 5, 'requests': 5},
            
            # Miner endpoints  
            {'endpoint': '/miners/register', 'method': 'POST', 'users': 3, 'requests': 3,
             'json': {'capabilities': {'gpu': {'model': 'RTX 4090'}}},
             'headers': {'Content-Type': 'application/json', 'X-Miner-ID': 'perf-test-miner'}},
            
            # Blockchain endpoints
            {'endpoint': '/blockchain/info', 'method': 'GET', 'users': 5, 'requests': 5},
        ]
        
        results = []
        
        for test_config in test_endpoints:
            endpoint = test_config.pop('endpoint')
            method = test_config.pop('method')
            
            result = await self.load_test_endpoint(endpoint, method, **test_config)
            results.append(result)
            
            # Print immediate results
            print(f"📊 {method} {endpoint}:")
            print(f"   ✅ Success Rate: {result['success_rate']:.1f}%")
            print(f"   ⏱️  Avg Response: {result['avg_response_time']:.3f}s")
            print(f"   📈 RPS: {result['requests_per_second']:.1f}")
            print(f"   📏 P95: {result['p95_response_time']:.3f}s")
            print()
        
        return results
    
    def generate_report(self, results: List[Dict[str, Any]]):
        """Generate performance test report"""
        print("📋 PERFORMANCE TEST REPORT")
        print("=" * 60)
        
        total_requests = sum(r['total_requests'] for r in results)
        total_successful = sum(r['successful_requests'] for r in results)
        overall_success_rate = (total_successful / total_requests * 100) if total_requests > 0 else 0
        
        print(f"📊 Overall Statistics:")
        print(f"   Total Requests: {total_requests}")
        print(f"   Successful Requests: {total_successful}")
        print(f"   Overall Success Rate: {overall_success_rate:.1f}%")
        print()
        
        print(f"🎯 Endpoint Performance:")
        for result in results:
            status = "✅" if result['success_rate'] >= 95 else "⚠️" if result['success_rate'] >= 80 else "❌"
            print(f"   {status} {result['method']} {result['endpoint']}")
            print(f"      Success: {result['success_rate']:.1f}% | "
                  f"Avg: {result['avg_response_time']:.3f}s | "
                  f"P95: {result['p95_response_time']:.3f}s | "
                  f"RPS: {result['requests_per_second']:.1f}")
        
        print()
        print("🏆 Performance Benchmarks:")
        print("   ✅ Excellent: <100ms response time, >95% success rate")
        print("   ⚠️  Good: <500ms response time, >80% success rate") 
        print("   ❌ Needs Improvement: >500ms or <80% success rate")
        
        # Recommendations
        print()
        print("💡 Recommendations:")
        
        slow_endpoints = [r for r in results if r['avg_response_time'] > 0.5]
        if slow_endpoints:
            print("   🐌 Slow endpoints detected - consider optimization:")
            for r in slow_endpoints:
                print(f"      - {r['endpoint']} ({r['avg_response_time']:.3f}s avg)")
        
        unreliable_endpoints = [r for r in results if r['success_rate'] < 95]
        if unreliable_endpoints:
            print("   🔧 Unreliable endpoints detected - check for errors:")
            for r in unreliable_endpoints:
                print(f"      - {r['endpoint']} ({r['success_rate']:.1f}% success)")
        
        if not slow_endpoints and not unreliable_endpoints:
            print("   🎉 All endpoints performing well - ready for production!")

async def main():
    """Main performance testing execution"""
    tester = PerformanceTester()
    
    try:
        results = await tester.run_performance_tests()
        tester.generate_report(results)
        
        # Return exit code based on performance
        avg_success_rate = statistics.mean([r['success_rate'] for r in results])
        avg_response_time = statistics.mean([r['avg_response_time'] for r in results])
        
        if avg_success_rate >= 95 and avg_response_time < 0.5:
            print("\n🎉 PERFORMANCE TESTS PASSED - Ready for production!")
            return 0
        else:
            print("\n⚠️  PERFORMANCE TESTS COMPLETED - Review recommendations")
            return 1
            
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
