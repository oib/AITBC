#!/usr/bin/env python3
"""
Scalability Validation for AITBC Platform
Tests system performance under load and validates scalability
"""

import asyncio
import aiohttp
import time
import statistics
import json
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
from typing import List, Dict, Any

class ScalabilityValidator:
    def __init__(self, base_url="https://aitbc.bubuit.net/api/v1"):
        self.base_url = base_url
        self.api_key = "test_key_16_characters"
        self.results = []
        
    async def measure_endpoint_performance(self, session, endpoint, method="GET", **kwargs):
        """Measure performance of a single endpoint"""
        start_time = time.time()
        
        headers = kwargs.pop('headers', {})
        headers['X-Api-Key'] = self.api_key
        
        try:
            async with session.request(method, f"{self.base_url}{endpoint}", 
                                      headers=headers, timeout=30, **kwargs) as response:
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
    
    async def load_test_endpoint(self, endpoint, method="GET", concurrent_users=10, 
                               requests_per_user=5, ramp_up_time=5, **kwargs):
        """Perform load testing with gradual ramp-up"""
        print(f"🧪 Load Testing {method} {endpoint}")
        print(f"   Users: {concurrent_users}, Requests/User: {requests_per_user}")
        print(f"   Total Requests: {concurrent_users * requests_per_user}")
        
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=100)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []
            
            # Gradual ramp-up
            for user in range(concurrent_users):
                # Add delay for ramp-up
                if user > 0:
                    await asyncio.sleep(ramp_up_time / concurrent_users)
                
                # Create requests for this user
                for req in range(requests_per_user):
                    task = self.measure_endpoint_performance(session, method, endpoint, **kwargs)
                    tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter valid results
            valid_results = [r for r in results if isinstance(r, dict)]
            successful_results = [r for r in valid_results if r['success']]
            
            # Calculate metrics
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
                'p99_response_time': statistics.quantiles(response_times, n=100)[98] if len(response_times) > 100 else 0,
                'requests_per_second': len(successful_results) / (max(response_times) - min(response_time)) if len(response_times) > 1 else 0
            }
    
    def get_system_metrics(self):
        """Get current system metrics"""
        try:
            # CPU usage
            cpu_result = subprocess.run(['top', '-bn1', '|', 'grep', 'Cpu(s)', '|', "awk", "'{print $2}'"], 
                                      capture_output=True, text=True, shell=True)
            cpu_usage = cpu_result.stdout.strip().replace('%us,', '')
            
            # Memory usage
            mem_result = subprocess.run(['free', '|', 'grep', 'Mem', '|', "awk", "'{printf \"%.1f\", $3/$2 * 100.0}'"], 
                                       capture_output=True, text=True, shell=True)
            memory_usage = mem_result.stdout.strip()
            
            # Disk usage
            disk_result = subprocess.run(['df', '/', '|', 'awk', 'NR==2{print $5}'], 
                                       capture_output=True, text=True, shell=True)
            disk_usage = disk_result.stdout.strip().replace('%', '')
            
            return {
                'cpu_usage': float(cpu_usage) if cpu_usage else 0,
                'memory_usage': float(memory_usage) if memory_usage else 0,
                'disk_usage': float(disk_usage) if disk_usage else 0
            }
        except Exception as e:
            print(f"⚠️  Could not get system metrics: {e}")
            return {'cpu_usage': 0, 'memory_usage': 0, 'disk_usage': 0}
    
    async def run_scalability_tests(self):
        """Run comprehensive scalability tests"""
        print("🚀 AITBC Platform Scalability Validation")
        print("=" * 60)
        
        # Record initial system metrics
        initial_metrics = self.get_system_metrics()
        print(f"📊 Initial System Metrics:")
        print(f"   CPU: {initial_metrics['cpu_usage']:.1f}%")
        print(f"   Memory: {initial_metrics['memory_usage']:.1f}%")
        print(f"   Disk: {initial_metrics['disk_usage']:.1f}%")
        print()
        
        # Test scenarios with increasing load
        test_scenarios = [
            # Light load
            {'endpoint': '/health', 'method': 'GET', 'users': 5, 'requests': 5, 'name': 'Light Load'},
            
            # Medium load
            {'endpoint': '/health', 'method': 'GET', 'users': 20, 'requests': 10, 'name': 'Medium Load'},
            
            # Heavy load
            {'endpoint': '/health', 'method': 'GET', 'users': 50, 'requests': 10, 'name': 'Heavy Load'},
            
            # Stress test
            {'endpoint': '/health', 'method': 'GET', 'users': 100, 'requests': 5, 'name': 'Stress Test'},
        ]
        
        results = []
        
        for scenario in test_scenarios:
            print(f"🎯 Scenario: {scenario['name']}")
            
            endpoint = scenario['endpoint']
            method = scenario['method']
            users = scenario['users']
            requests = scenario['requests']
            
            # Get metrics before test
            before_metrics = self.get_system_metrics()
            
            # Run load test
            result = await self.load_test_endpoint(endpoint, method, users, requests)
            result['scenario'] = scenario['name']
            result['concurrent_users'] = users
            result['requests_per_user'] = requests
            
            # Get metrics after test
            after_metrics = self.get_system_metrics()
            
            # Calculate resource impact
            result['cpu_impact'] = after_metrics['cpu_usage'] - before_metrics['cpu_usage']
            result['memory_impact'] = after_metrics['memory_usage'] - before_metrics['memory_usage']
            
            results.append(result)
            
            # Print scenario results
            self.print_scenario_results(result)
            
            # Wait between tests
            await asyncio.sleep(2)
        
        return results
    
    def print_scenario_results(self, result):
        """Print results for a single scenario"""
        status = "✅" if result['success_rate'] >= 95 else "⚠️" if result['success_rate'] >= 80 else "❌"
        
        print(f"   {status} {result['scenario']}:")
        print(f"      Success Rate: {result['success_rate']:.1f}%")
        print(f"      Avg Response: {result['avg_response_time']:.3f}s")
        print(f"      P95 Response: {result['p95_response_time']:.3f}s")
        print(f"      P99 Response: {result['p99_response_time']:.3f}s")
        print(f"      Requests/Second: {result['requests_per_second']:.1f}")
        print(f"      CPU Impact: +{result['cpu_impact']:.1f}%")
        print(f"      Memory Impact: +{result['memory_impact']:.1f}%")
        print()
    
    def generate_scalability_report(self, results):
        """Generate comprehensive scalability report"""
        print("📋 SCALABILITY VALIDATION REPORT")
        print("=" * 60)
        
        # Overall statistics
        total_requests = sum(r['total_requests'] for r in results)
        total_successful = sum(r['successful_requests'] for r in results)
        overall_success_rate = (total_successful / total_requests * 100) if total_requests > 0 else 0
        
        print(f"📊 Overall Performance:")
        print(f"   Total Requests: {total_requests}")
        print(f"   Successful Requests: {total_successful}")
        print(f"   Overall Success Rate: {overall_success_rate:.1f}%")
        print()
        
        # Performance by scenario
        print(f"🎯 Performance by Scenario:")
        for result in results:
            status = "✅" if result['success_rate'] >= 95 else "⚠️" if result['success_rate'] >= 80 else "❌"
            print(f"   {status} {result['scenario']} ({result['concurrent_users']} users)")
            print(f"      Success: {result['success_rate']:.1f}% | "
                  f"Avg: {result['avg_response_time']:.3f}s | "
                  f"P95: {result['p95_response_time']:.3f}s | "
                  f"RPS: {result['requests_per_second']:.1f}")
        print()
        
        # Scalability analysis
        print(f"📈 Scalability Analysis:")
        
        # Response time scalability
        response_times = [(r['concurrent_users'], r['avg_response_time']) for r in results]
        print(f"   Response Time Scalability:")
        for users, avg_time in response_times:
            print(f"      {users} users: {avg_time:.3f}s avg")
        
        # Success rate scalability
        success_rates = [(r['concurrent_users'], r['success_rate']) for r in results]
        print(f"   Success Rate Scalability:")
        for users, success_rate in success_rates:
            print(f"      {users} users: {success_rate:.1f}% success")
        
        # Resource impact analysis
        cpu_impacts = [r['cpu_impact'] for r in results]
        memory_impacts = [r['memory_impact'] for r in results]
        
        print(f"   Resource Impact:")
        print(f"      Max CPU Impact: +{max(cpu_impacts):.1f}%")
        print(f"      Max Memory Impact: +{max(memory_impacts):.1f}%")
        print()
        
        # Recommendations
        print(f"💡 Scalability Recommendations:")
        
        # Check if performance degrades significantly
        max_response_time = max(r['avg_response_time'] for r in results)
        min_success_rate = min(r['success_rate'] for r in results)
        
        if max_response_time < 0.5 and min_success_rate >= 95:
            print("   🎉 Excellent scalability - system handles load well!")
            print("   ✅ Ready for production deployment")
        elif max_response_time < 1.0 and min_success_rate >= 90:
            print("   ✅ Good scalability - suitable for production")
            print("   💡 Consider optimization for higher loads")
        else:
            print("   ⚠️  Scalability concerns detected:")
            if max_response_time >= 1.0:
                print("      - Response times exceed 1s under load")
            if min_success_rate < 90:
                print("      - Success rate drops below 90% under load")
            print("   🔧 Performance optimization recommended before production")
        
        print()
        print("🏆 Scalability Benchmarks:")
        print("   ✅ Excellent: <500ms response, >95% success at 100+ users")
        print("   ⚠️  Good: <1s response, >90% success at 50+ users")
        print("   ❌ Needs Work: >1s response or <90% success rate")

async def main():
    """Main scalability validation"""
    validator = ScalabilityValidator()
    
    try:
        results = await validator.run_scalability_tests()
        validator.generate_scalability_report(results)
        
        # Determine if system is production-ready
        min_success_rate = min(r['success_rate'] for r in results)
        max_response_time = max(r['avg_response_time'] for r in results)
        
        if min_success_rate >= 90 and max_response_time < 1.0:
            print("\n✅ SCALABILITY VALIDATION PASSED")
            print("🚀 System is ready for production deployment!")
            return 0
        else:
            print("\n⚠️  SCALABILITY VALIDATION NEEDS REVIEW")
            print("🔧 Performance optimization recommended")
            return 1
            
    except Exception as e:
        print(f"❌ Scalability validation failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
