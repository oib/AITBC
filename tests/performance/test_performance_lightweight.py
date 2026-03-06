"""
Performance Tests for AITBC Chain Management and Analytics
Tests system performance under various load conditions (lightweight version)
"""

import pytest
import asyncio
import json
import time
import threading
import statistics
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Tuple
import os
import resource

class TestPerformance:
    """Performance testing suite for AITBC components"""
    
    @pytest.fixture(scope="class")
    def performance_config(self):
        """Performance test configuration"""
        return {
            "base_url": "http://localhost",
            "ports": {
                "coordinator": 8001,
                "blockchain": 8007,
                "consensus": 8002,
                "network": 8008,
                "explorer": 8016,
                "wallet_daemon": 8003,
                "exchange": 8010,
                "oracle": 8011,
                "trading": 8012,
                "compliance": 8015,
                "plugin_registry": 8013,
                "plugin_marketplace": 8014,
                "global_infrastructure": 8017,
                "ai_agents": 8018,
                "load_balancer": 8019
            },
            "performance_thresholds": {
                "response_time_p95": 2000,  # 95th percentile < 2 seconds
                "response_time_p99": 5000,  # 99th percentile < 5 seconds
                "error_rate": 0.01,          # < 1% error rate
                "throughput_min": 50,        # Minimum 50 requests/second
                "cli_response_max": 5000     # CLI max response time < 5 seconds
            }
        }
    
    def get_memory_usage(self):
        """Get current memory usage (lightweight version)"""
        try:
            # Using resource module for memory usage
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return usage.ru_maxrss / 1024  # Convert to MB (on Linux)
        except:
            return 0
    
    def get_cpu_usage(self):
        """Get CPU usage (lightweight version)"""
        try:
            # Simple CPU usage calculation
            start_time = time.time()
            while time.time() - start_time < 0.1:  # Sample for 0.1 seconds
                pass
            return 0  # Simplified - would need more complex implementation for accurate CPU
        except:
            return 0
    
    def test_cli_performance(self, performance_config):
        """Test CLI command performance"""
        cli_commands = [
            ["--help"],
            ["wallet", "--help"],
            ["blockchain", "--help"],
            ["multisig", "--help"],
            ["genesis-protection", "--help"],
            ["transfer-control", "--help"],
            ["compliance", "--help"],
            ["exchange", "--help"],
            ["oracle", "--help"],
            ["market-maker", "--help"]
        ]
        
        response_times = []
        memory_usage_before = self.get_memory_usage()
        
        for command in cli_commands:
            start_time = time.time()
            
            result = subprocess.run(
                ["python", "-m", "aitbc_cli.main"] + command,
                capture_output=True,
                text=True,
                cwd="/home/oib/windsurf/aitbc/cli"
            )
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # Convert to milliseconds
            
            assert result.returncode == 0, f"CLI command failed: {' '.join(command)}"
            assert response_time < performance_config["performance_thresholds"]["cli_response_max"], \
                f"CLI command too slow: {response_time:.2f}ms"
            
            response_times.append(response_time)
        
        memory_usage_after = self.get_memory_usage()
        memory_increase = memory_usage_after - memory_usage_before
        
        # Calculate performance statistics
        avg_response_time = statistics.mean(response_times)
        p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max(response_times)
        max_response_time = max(response_times)
        
        # Performance assertions
        assert avg_response_time < 1000, f"Average CLI response time too high: {avg_response_time:.2f}ms"
        assert p95_response_time < 3000, f"95th percentile CLI response time too high: {p95_response_time:.2f}ms"
        assert max_response_time < 10000, f"Maximum CLI response time too high: {max_response_time:.2f}ms"
        assert memory_increase < 100, f"Memory usage increased too much: {memory_increase:.1f}MB"
        
        print(f"CLI Performance Results:")
        print(f"  Average: {avg_response_time:.2f}ms")
        print(f"  95th percentile: {p95_response_time:.2f}ms")
        print(f"  Maximum: {max_response_time:.2f}ms")
        print(f"  Memory increase: {memory_increase:.1f}MB")
    
    def test_concurrent_cli_operations(self, performance_config):
        """Test concurrent CLI operations"""
        def run_cli_command(command):
            start_time = time.time()
            result = subprocess.run(
                ["python", "-m", "aitbc_cli.main"] + command,
                capture_output=True,
                text=True,
                cwd="/home/oib/windsurf/aitbc/cli"
            )
            end_time = time.time()
            return {
                "command": command,
                "success": result.returncode == 0,
                "response_time": (end_time - start_time) * 1000,
                "output_length": len(result.stdout)
            }
        
        # Test concurrent operations
        commands_to_test = [
            ["wallet", "--help"],
            ["blockchain", "--help"],
            ["multisig", "--help"],
            ["compliance", "--help"],
            ["exchange", "--help"]
        ]
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit multiple concurrent requests
            futures = []
            for _ in range(20):  # 20 concurrent operations
                for command in commands_to_test:
                    future = executor.submit(run_cli_command, command)
                    futures.append(future)
            
            # Collect results
            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
        
        # Analyze results
        successful_operations = [r for r in results if r["success"]]
        response_times = [r["response_time"] for r in successful_operations]
        
        success_rate = len(successful_operations) / len(results)
        avg_response_time = statistics.mean(response_times) if response_times else 0
        p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max(response_times) if response_times else 0
        
        # Performance assertions
        assert success_rate >= 0.95, f"Low success rate: {success_rate:.2%}"
        assert avg_response_time < 2000, f"Average response time too high: {avg_response_time:.2f}ms"
        assert p95_response_time < 5000, f"95th percentile response time too high: {p95_response_time:.2f}ms"
        
        print(f"Concurrent CLI Operations Results:")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Average response time: {avg_response_time:.2f}ms")
        print(f"  95th percentile: {p95_response_time:.2f}ms")
        print(f"  Total operations: {len(results)}")
    
    def test_cli_memory_efficiency(self, performance_config):
        """Test CLI memory efficiency"""
        memory_samples = []
        
        def monitor_memory():
            for _ in range(10):
                memory_usage = self.get_memory_usage()
                memory_samples.append(memory_usage)
                time.sleep(0.5)
        
        def run_cli_operations():
            commands = [
                ["wallet", "--help"],
                ["blockchain", "--help"],
                ["multisig", "--help"],
                ["genesis-protection", "--help"],
                ["transfer-control", "--help"],
                ["compliance", "--help"],
                ["exchange", "--help"],
                ["oracle", "--help"],
                ["market-maker", "--help"]
            ]
            
            for _ in range(5):  # Run commands multiple times
                for command in commands:
                    subprocess.run(
                        ["python", "-m", "aitbc_cli.main"] + command,
                        capture_output=True,
                        text=True,
                        cwd="/home/oib/windsurf/aitbc/cli"
                    )
        
        # Monitor memory during operations
        monitor_thread = threading.Thread(target=monitor_memory)
        operation_thread = threading.Thread(target=run_cli_operations)
        
        monitor_thread.start()
        operation_thread.start()
        
        monitor_thread.join()
        operation_thread.join()
        
        # Analyze memory usage
        if memory_samples:
            avg_memory = statistics.mean(memory_samples)
            max_memory = max(memory_samples)
            memory_variance = statistics.variance(memory_samples) if len(memory_samples) > 1 else 0
            
            # Memory efficiency assertions
            assert max_memory - min(memory_samples) < 50, f"Memory usage variance too high: {max_memory - min(memory_samples):.1f}MB"
            assert avg_memory < 200, f"Average memory usage too high: {avg_memory:.1f}MB"
            
            print(f"CLI Memory Efficiency Results:")
            print(f"  Average memory: {avg_memory:.1f}MB")
            print(f"  Maximum memory: {max_memory:.1f}MB")
            print(f"  Memory variance: {memory_variance:.1f}")
    
    def test_cli_throughput(self, performance_config):
        """Test CLI command throughput"""
        def measure_throughput():
            commands = [
                ["wallet", "--help"],
                ["blockchain", "--help"],
                ["multisig", "--help"]
            ]
            
            start_time = time.time()
            successful_operations = 0
            
            for i in range(100):  # 100 operations
                command = commands[i % len(commands)]
                result = subprocess.run(
                    ["python", "-m", "aitbc_cli.main"] + command,
                    capture_output=True,
                    text=True,
                    cwd="/home/oib/windsurf/aitbc/cli"
                )
                
                if result.returncode == 0:
                    successful_operations += 1
            
            end_time = time.time()
            duration = end_time - start_time
            throughput = successful_operations / duration  # operations per second
            
            return {
                "total_operations": 100,
                "successful_operations": successful_operations,
                "duration": duration,
                "throughput": throughput
            }
        
        # Run throughput test
        result = measure_throughput()
        
        # Throughput assertions
        assert result["successful_operations"] >= 95, f"Too many failed operations: {result['successful_operations']}/100"
        assert result["throughput"] >= 10, f"Throughput too low: {result['throughput']:.2f} ops/s"
        assert result["duration"] < 30, f"Test took too long: {result['duration']:.2f}s"
        
        print(f"CLI Throughput Results:")
        print(f"  Successful operations: {result['successful_operations']}/100")
        print(f"  Duration: {result['duration']:.2f}s")
        print(f"  Throughput: {result['throughput']:.2f} ops/s")
    
    def test_cli_response_time_distribution(self, performance_config):
        """Test CLI response time distribution"""
        commands = [
            ["--help"],
            ["wallet", "--help"],
            ["blockchain", "--help"],
            ["multisig", "--help"],
            ["genesis-protection", "--help"],
            ["transfer-control", "--help"],
            ["compliance", "--help"],
            ["exchange", "--help"],
            ["oracle", "--help"],
            ["market-maker", "--help"]
        ]
        
        response_times = []
        
        # Run each command multiple times
        for command in commands:
            for _ in range(10):  # 10 times per command
                start_time = time.time()
                
                result = subprocess.run(
                    ["python", "-m", "aitbc_cli.main"] + command,
                    capture_output=True,
                    text=True,
                    cwd="/home/oib/windsurf/aitbc/cli"
                )
                
                end_time = time.time()
                response_time = (end_time - start_time) * 1000
                
                assert result.returncode == 0, f"CLI command failed: {' '.join(command)}"
                response_times.append(response_time)
        
        # Calculate distribution statistics
        min_time = min(response_times)
        max_time = max(response_times)
        mean_time = statistics.mean(response_times)
        median_time = statistics.median(response_times)
        std_dev = statistics.stdev(response_times)
        
        # Percentiles
        sorted_times = sorted(response_times)
        p50 = sorted_times[len(sorted_times) // 2]
        p90 = sorted_times[int(len(sorted_times) * 0.9)]
        p95 = sorted_times[int(len(sorted_times) * 0.95)]
        p99 = sorted_times[int(len(sorted_times) * 0.99)]
        
        # Distribution assertions
        assert mean_time < 1000, f"Mean response time too high: {mean_time:.2f}ms"
        assert p95 < 3000, f"95th percentile too high: {p95:.2f}ms"
        assert p99 < 5000, f"99th percentile too high: {p99:.2f}ms"
        assert std_dev < mean_time, f"Standard deviation too high: {std_dev:.2f}ms"
        
        print(f"CLI Response Time Distribution:")
        print(f"  Min: {min_time:.2f}ms")
        print(f"  Max: {max_time:.2f}ms")
        print(f"  Mean: {mean_time:.2f}ms")
        print(f"  Median: {median_time:.2f}ms")
        print(f"  Std Dev: {std_dev:.2f}ms")
        print(f"  50th percentile: {p50:.2f}ms")
        print(f"  90th percentile: {p90:.2f}ms")
        print(f"  95th percentile: {p95:.2f}ms")
        print(f"  99th percentile: {p99:.2f}ms")
    
    def test_cli_scalability(self, performance_config):
        """Test CLI scalability with increasing load"""
        def test_load_level(num_concurrent, operations_per_thread):
            def worker():
                commands = [["--help"], ["wallet", "--help"], ["blockchain", "--help"]]
                results = []
                
                for i in range(operations_per_thread):
                    command = commands[i % len(commands)]
                    start_time = time.time()
                    
                    result = subprocess.run(
                        ["python", "-m", "aitbc_cli.main"] + command,
                        capture_output=True,
                        text=True,
                        cwd="/home/oib/windsurf/aitbc/cli"
                    )
                    
                    end_time = time.time()
                    results.append({
                        "success": result.returncode == 0,
                        "response_time": (end_time - start_time) * 1000
                    })
                
                return results
            
            with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
                futures = [executor.submit(worker) for _ in range(num_concurrent)]
                all_results = []
                
                for future in as_completed(futures):
                    worker_results = future.result()
                    all_results.extend(worker_results)
            
            # Analyze results
            successful = [r for r in all_results if r["success"]]
            response_times = [r["response_time"] for r in successful]
            
            if response_times:
                success_rate = len(successful) / len(all_results)
                avg_response_time = statistics.mean(response_times)
                
                return {
                    "total_operations": len(all_results),
                    "successful_operations": len(successful),
                    "success_rate": success_rate,
                    "avg_response_time": avg_response_time
                }
        
        # Test different load levels
        load_levels = [
            (1, 50),    # 1 thread, 50 operations
            (2, 50),    # 2 threads, 50 operations each
            (5, 20),    # 5 threads, 20 operations each
            (10, 10)    # 10 threads, 10 operations each
        ]
        
        results = {}
        
        for num_threads, ops_per_thread in load_levels:
            result = test_load_level(num_threads, ops_per_thread)
            results[f"{num_threads}x{ops_per_thread}"] = result
            
            # Scalability assertions
            assert result["success_rate"] >= 0.90, f"Low success rate at {num_threads}x{ops_per_thread}: {result['success_rate']:.2%}"
            assert result["avg_response_time"] < 3000, f"Response time too high at {num_threads}x{ops_per_thread}: {result['avg_response_time']:.2f}ms"
        
        print(f"CLI Scalability Results:")
        for load_level, result in results.items():
            print(f"  {load_level}: {result['success_rate']:.2%} success, {result['avg_response_time']:.2f}ms avg")
    
    def test_cli_error_handling_performance(self, performance_config):
        """Test CLI error handling performance"""
        # Test invalid commands
        invalid_commands = [
            ["--invalid-option"],
            ["wallet", "--invalid-subcommand"],
            ["blockchain", "invalid-subcommand"],
            ["nonexistent-command"]
        ]
        
        response_times = []
        
        for command in invalid_commands:
            start_time = time.time()
            
            result = subprocess.run(
                ["python", "-m", "aitbc_cli.main"] + command,
                capture_output=True,
                text=True,
                cwd="/home/oib/windsurf/aitbc/cli"
            )
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            # Should fail gracefully
            assert result.returncode != 0, f"Invalid command should fail: {' '.join(command)}"
            assert response_time < 2000, f"Error handling too slow: {response_time:.2f}ms"
            
            response_times.append(response_time)
        
        avg_error_response_time = statistics.mean(response_times)
        max_error_response_time = max(response_times)
        
        # Error handling performance assertions
        assert avg_error_response_time < 1000, f"Average error response time too high: {avg_error_response_time:.2f}ms"
        assert max_error_response_time < 2000, f"Maximum error response time too high: {max_error_response_time:.2f}ms"
        
        print(f"CLI Error Handling Performance:")
        print(f"  Average error response time: {avg_error_response_time:.2f}ms")
        print(f"  Maximum error response time: {max_error_response_time:.2f}ms")

class TestServicePerformance:
    """Test service performance (when services are available)"""
    
    def test_service_health_performance(self, performance_config):
        """Test service health endpoint performance"""
        services_to_test = {
            "global_infrastructure": performance_config["ports"]["global_infrastructure"],
            "consensus": performance_config["ports"]["consensus"]
        }
        
        for service_name, port in services_to_test.items():
            try:
                start_time = time.time()
                response = requests.get(f"{performance_config['base_url']}:{port}/health", timeout=5)
                end_time = time.time()
                
                response_time = (end_time - start_time) * 1000
                
                if response.status_code == 200:
                    assert response_time < 1000, f"{service_name} health endpoint too slow: {response_time:.2f}ms"
                    print(f"✅ {service_name} health: {response_time:.2f}ms")
                else:
                    print(f"⚠️  {service_name} health returned {response.status_code}")
                    
            except Exception as e:
                print(f"❌ {service_name} health check failed: {str(e)}")

if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "--tb=short"])
