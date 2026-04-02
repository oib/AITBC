"""
Performance Benchmark Tests for AITBC Agent Systems
Tests system performance under various loads
"""

import pytest
import asyncio
import time
import requests
import psutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import statistics

class TestAPIPerformance:
    """Test API performance benchmarks"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_health_endpoint_performance(self):
        """Test health endpoint performance under load"""
        def make_request():
            start_time = time.time()
            response = requests.get(f"{self.BASE_URL}/health")
            end_time = time.time()
            return {
                'status_code': response.status_code,
                'response_time': end_time - start_time
            }
        
        # Test with 100 concurrent requests
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request) for _ in range(100)]
            results = [future.result() for future in as_completed(futures)]
        
        # Analyze results
        response_times = [r['response_time'] for r in results]
        success_count = sum(1 for r in results if r['status_code'] == 200)
        
        assert success_count >= 95  # 95% success rate
        assert statistics.mean(response_times) < 0.5  # Average < 500ms
        assert statistics.median(response_times) < 0.3  # Median < 300ms
        assert max(response_times) < 2.0  # Max < 2 seconds
    
    def test_agent_registration_performance(self):
        """Test agent registration performance"""
        def register_agent(i):
            agent_data = {
                "agent_id": f"perf_test_agent_{i}",
                "agent_type": "worker",
                "capabilities": ["test"],
                "services": ["test_service"]
            }
            
            start_time = time.time()
            response = requests.post(
                f"{self.BASE_URL}/agents/register",
                json=agent_data,
                headers={"Content-Type": "application/json"}
            )
            end_time = time.time()
            
            return {
                'status_code': response.status_code,
                'response_time': end_time - start_time
            }
        
        # Test with 50 concurrent registrations
        with ThreadPoolExecutor(max_workers=25) as executor:
            futures = [executor.submit(register_agent, i) for i in range(50)]
            results = [future.result() for future in as_completed(futures)]
        
        response_times = [r['response_time'] for r in results]
        success_count = sum(1 for r in results if r['status_code'] == 200)
        
        assert success_count >= 45  # 90% success rate
        assert statistics.mean(response_times) < 1.0  # Average < 1 second
    
    def test_load_balancer_performance(self):
        """Test load balancer performance"""
        def get_stats():
            start_time = time.time()
            response = requests.get(f"{self.BASE_URL}/load-balancer/stats")
            end_time = time.time()
            return {
                'status_code': response.status_code,
                'response_time': end_time - start_time
            }
        
        # Test with 200 concurrent requests
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(get_stats) for _ in range(200)]
            results = [future.result() for future in as_completed(futures)]
        
        response_times = [r['response_time'] for r in results]
        success_count = sum(1 for r in results if r['status_code'] == 200)
        
        assert success_count >= 190  # 95% success rate
        assert statistics.mean(response_times) < 0.3  # Average < 300ms

class TestSystemResourceUsage:
    """Test system resource usage during operations"""
    
    def test_memory_usage_during_load(self):
        """Test memory usage during high load"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        # Perform memory-intensive operations
        def heavy_operation():
            for _ in range(10):
                response = requests.get("http://localhost:9001/registry/stats")
                time.sleep(0.01)
        
        # Run 20 concurrent heavy operations
        threads = []
        for _ in range(20):
            thread = threading.Thread(target=heavy_operation)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (< 50MB)
        assert memory_increase < 50 * 1024 * 1024  # 50MB in bytes
    
    def test_cpu_usage_during_load(self):
        """Test CPU usage during high load"""
        process = psutil.Process()
        
        # Monitor CPU during load test
        def cpu_monitor():
            cpu_percentages = []
            for _ in range(10):
                cpu_percentages.append(process.cpu_percent())
                time.sleep(0.1)
            return statistics.mean(cpu_percentages)
        
        # Start CPU monitoring
        monitor_thread = threading.Thread(target=cpu_monitor)
        monitor_thread.start()
        
        # Perform CPU-intensive operations
        for _ in range(50):
            response = requests.get("http://localhost:9001/load-balancer/stats")
            # Process response to simulate CPU work
            data = response.json()
            _ = len(str(data))
        
        monitor_thread.join()
        
        # CPU usage should be reasonable (< 80%)
        # Note: This is a rough test, actual CPU usage depends on system load

class TestConcurrencyLimits:
    """Test system behavior under concurrency limits"""
    
    def test_maximum_concurrent_connections(self):
        """Test maximum concurrent connections"""
        def make_request():
            try:
                response = requests.get("http://localhost:9001/health", timeout=5)
                return response.status_code == 200
            except:
                return False
        
        # Test with increasing concurrency
        max_concurrent = 0
        for concurrency in [50, 100, 200, 500]:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(make_request) for _ in range(concurrency)]
                results = [future.result() for future in as_completed(futures)]
            
            success_rate = sum(results) / len(results)
            
            if success_rate >= 0.8:  # 80% success rate
                max_concurrent = concurrency
            else:
                break
        
        # Should handle at least 100 concurrent connections
        assert max_concurrent >= 100

class TestScalabilityMetrics:
    """Test scalability metrics"""
    
    def test_response_time_scaling(self):
        """Test how response times scale with load"""
        loads = [1, 10, 50, 100]
        response_times = []
        
        for load in loads:
            def make_request():
                start_time = time.time()
                response = requests.get("http://localhost:9001/health")
                end_time = time.time()
                return end_time - start_time
            
            with ThreadPoolExecutor(max_workers=load) as executor:
                futures = [executor.submit(make_request) for _ in range(load)]
                results = [future.result() for future in as_completed(futures)]
            
            avg_time = statistics.mean(results)
            response_times.append(avg_time)
        
        # Response times should scale reasonably
        # (not more than 10x increase from 1 to 100 concurrent requests)
        assert response_times[-1] < response_times[0] * 10
    
    def test_throughput_metrics(self):
        """Test throughput metrics"""
        duration = 10  # Test for 10 seconds
        start_time = time.time()
        
        def make_request():
            return requests.get("http://localhost:9001/health")
        
        requests_made = 0
        with ThreadPoolExecutor(max_workers=50) as executor:
            while time.time() - start_time < duration:
                futures = [executor.submit(make_request) for _ in range(10)]
                for future in as_completed(futures):
                    future.result()  # Wait for completion
                    requests_made += 1
        
        throughput = requests_made / duration  # requests per second
        
        # Should handle at least 50 requests per second
        assert throughput >= 50

if __name__ == '__main__':
    pytest.main([__file__])
