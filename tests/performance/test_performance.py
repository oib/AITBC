"""
Performance Tests for AITBC Chain Management and Analytics
Tests system performance under various load conditions
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
import psutil
import memory_profiler

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
            "load_test_config": {
                "concurrent_users": 10,
                "requests_per_user": 100,
                "duration_seconds": 60,
                "ramp_up_time": 10
            },
            "performance_thresholds": {
                "response_time_p95": 2000,  # 95th percentile < 2 seconds
                "response_time_p99": 5000,  # 99th percentile < 5 seconds
                "error_rate": 0.01,          # < 1% error rate
                "throughput_min": 50,        # Minimum 50 requests/second
                "cpu_usage_max": 0.80,      # < 80% CPU usage
                "memory_usage_max": 0.85    # < 85% memory usage
            }
        }
    
    @pytest.fixture(scope="class")
    def baseline_metrics(self, performance_config):
        """Capture baseline system metrics"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "timestamp": datetime.utcnow().isoformat()
        }
    
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
            assert response_time < 5000, f"CLI command too slow: {response_time:.2f}ms"
            
            response_times.append(response_time)
        
        # Calculate performance statistics
        avg_response_time = statistics.mean(response_times)
        p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
        max_response_time = max(response_times)
        
        # Performance assertions
        assert avg_response_time < 1000, f"Average CLI response time too high: {avg_response_time:.2f}ms"
        assert p95_response_time < 3000, f"95th percentile CLI response time too high: {p95_response_time:.2f}ms"
        assert max_response_time < 10000, f"Maximum CLI response time too high: {max_response_time:.2f}ms"
        
        print(f"CLI Performance Results:")
        print(f"  Average: {avg_response_time:.2f}ms")
        print(f"  95th percentile: {p95_response_time:.2f}ms")
        print(f"  Maximum: {max_response_time:.2f}ms")
    
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
    
    def test_memory_usage_cli(self, performance_config):
        """Test memory usage during CLI operations"""
        @memory_profiler.profile
        def run_memory_intensive_cli_operations():
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
            
            for _ in range(10):  # Run commands multiple times
                for command in commands:
                    subprocess.run(
                        ["python", "-m", "aitbc_cli.main"] + command,
                        capture_output=True,
                        text=True,
                        cwd="/home/oib/windsurf/aitbc/cli"
                    )
        
        # Capture memory before test
        memory_before = psutil.virtual_memory().percent
        
        # Run memory-intensive operations
        run_memory_intensive_cli_operations()
        
        # Capture memory after test
        memory_after = psutil.virtual_memory().percent
        memory_increase = memory_after - memory_before
        
        # Memory assertion
        assert memory_increase < 20, f"Memory usage increased too much: {memory_increase:.1f}%"
        
        print(f"Memory Usage Results:")
        print(f"  Memory before: {memory_before:.1f}%")
        print(f"  Memory after: {memory_after:.1f}%")
        print(f"  Memory increase: {memory_increase:.1f}%")
    
    def test_load_balancing_performance(self, performance_config):
        """Test load balancer performance under load"""
        def make_load_balancer_request():
            try:
                start_time = time.time()
                response = requests.get(
                    f"{performance_config['base_url']}:{performance_config['ports']['load_balancer']}/health",
                    timeout=5
                )
                end_time = time.time()
                
                return {
                    "success": response.status_code == 200,
                    "response_time": (end_time - start_time) * 1000,
                    "status_code": response.status_code
                }
            except Exception as e:
                return {
                    "success": False,
                    "response_time": 5000,  # Timeout
                    "error": str(e)
                }
        
        # Test with concurrent requests
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_load_balancer_request) for _ in range(100)]
            results = [future.result() for future in as_completed(futures)]
        
        # Analyze results
        successful_requests = [r for r in results if r["success"]]
        response_times = [r["response_time"] for r in successful_requests]
        
        if response_times:
            success_rate = len(successful_requests) / len(results)
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max(response_times)
            throughput = len(successful_requests) / 10  # requests per second
            
            # Performance assertions
            assert success_rate >= 0.90, f"Low success rate: {success_rate:.2%}"
            assert avg_response_time < 1000, f"Average response time too high: {avg_response_time:.2f}ms"
            assert throughput >= 10, f"Throughput too low: {throughput:.2f} req/s"
            
            print(f"Load Balancer Performance Results:")
            print(f"  Success rate: {success_rate:.2%}")
            print(f"  Average response time: {avg_response_time:.2f}ms")
            print(f"  95th percentile: {p95_response_time:.2f}ms")
            print(f"  Throughput: {throughput:.2f} req/s")
    
    def test_global_infrastructure_performance(self, performance_config):
        """Test global infrastructure performance"""
        def test_service_performance(service_name, port):
            try:
                start_time = time.time()
                response = requests.get(f"{performance_config['base_url']}:{port}/health", timeout=5)
                end_time = time.time()
                
                return {
                    "service": service_name,
                    "success": response.status_code == 200,
                    "response_time": (end_time - start_time) * 1000,
                    "status_code": response.status_code
                }
            except Exception as e:
                return {
                    "service": service_name,
                    "success": False,
                    "response_time": 5000,
                    "error": str(e)
                }
        
        # Test all global services
        global_services = {
            "global_infrastructure": performance_config["ports"]["global_infrastructure"],
            "ai_agents": performance_config["ports"]["ai_agents"],
            "load_balancer": performance_config["ports"]["load_balancer"]
        }
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(test_service_performance, service_name, port)
                for service_name, port in global_services.items()
            ]
            results = [future.result() for future in as_completed(futures)]
        
        # Analyze results
        successful_services = [r for r in results if r["success"]]
        response_times = [r["response_time"] for r in successful_services]
        
        if response_times:
            avg_response_time = statistics.mean(response_times)
            max_response_time = max(response_times)
            
            # Performance assertions
            assert len(successful_services) >= 2, f"Too few successful services: {len(successful_services)}"
            assert avg_response_time < 2000, f"Average response time too high: {avg_response_time:.2f}ms"
            assert max_response_time < 5000, f"Maximum response time too high: {max_response_time:.2f}ms"
            
            print(f"Global Infrastructure Performance Results:")
            print(f"  Successful services: {len(successful_services)}/{len(results)}")
            print(f"  Average response time: {avg_response_time:.2f}ms")
            print(f"  Maximum response time: {max_response_time:.2f}ms")
    
    def test_ai_agent_communication_performance(self, performance_config):
        """Test AI agent communication performance"""
        def test_agent_communication():
            try:
                start_time = time.time()
                response = requests.get(
                    f"{performance_config['base_url']}:{performance_config['ports']['ai_agents']}/api/v1/network/dashboard",
                    timeout=5
                )
                end_time = time.time()
                
                return {
                    "success": response.status_code == 200,
                    "response_time": (end_time - start_time) * 1000,
                    "data_size": len(response.content)
                }
            except Exception as e:
                return {
                    "success": False,
                    "response_time": 5000,
                    "error": str(e)
                }
        
        # Test concurrent agent communications
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(test_agent_communication) for _ in range(50)]
            results = [future.result() for future in as_completed(futures)]
        
        # Analyze results
        successful_requests = [r for r in results if r["success"]]
        response_times = [r["response_time"] for r in successful_requests]
        
        if response_times:
            success_rate = len(successful_requests) / len(results)
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max(response_times)
            
            # Performance assertions
            assert success_rate >= 0.80, f"Low success rate: {success_rate:.2%}"
            assert avg_response_time < 3000, f"Average response time too high: {avg_response_time:.2f}ms"
            assert p95_response_time < 8000, f"95th percentile response time too high: {p95_response_time:.2f}ms"
            
            print(f"AI Agent Communication Performance Results:")
            print(f"  Success rate: {success_rate:.2%}")
            print(f"  Average response time: {avg_response_time:.2f}ms")
            print(f"  95th percentile: {p95_response_time:.2f}ms")
            print(f"  Total requests: {len(results)}")
    
    def test_plugin_ecosystem_performance(self, performance_config):
        """Test plugin ecosystem performance"""
        plugin_services = {
            "plugin_registry": performance_config["ports"]["plugin_registry"],
            "plugin_marketplace": performance_config["ports"]["plugin_marketplace"],
            "plugin_analytics": performance_config["ports"]["plugin_analytics"]
        }
        
        def test_plugin_service(service_name, port):
            try:
                start_time = time.time()
                response = requests.get(f"{performance_config['base_url']}:{port}/health", timeout=5)
                end_time = time.time()
                
                return {
                    "service": service_name,
                    "success": response.status_code == 200,
                    "response_time": (end_time - start_time) * 1000
                }
            except Exception as e:
                return {
                    "service": service_name,
                    "success": False,
                    "response_time": 5000,
                    "error": str(e)
                }
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(test_plugin_service, service_name, port)
                for service_name, port in plugin_services.items()
            ]
            results = [future.result() for future in as_completed(futures)]
        
        # Analyze results
        successful_services = [r for r in results if r["success"]]
        response_times = [r["response_time"] for r in successful_services]
        
        if response_times:
            avg_response_time = statistics.mean(response_times)
            
            # Performance assertions
            assert len(successful_services) >= 1, f"No plugin services responding"
            assert avg_response_time < 2000, f"Average response time too high: {avg_response_time:.2f}ms"
            
            print(f"Plugin Ecosystem Performance Results:")
            print(f"  Successful services: {len(successful_services)}/{len(results)}")
            print(f"  Average response time: {avg_response_time:.2f}ms")
    
    def test_system_resource_usage(self, performance_config, baseline_metrics):
        """Test system resource usage during operations"""
        # Monitor system resources during intensive operations
        resource_samples = []
        
        def monitor_resources():
            for _ in range(30):  # Monitor for 30 seconds
                cpu_percent = psutil.cpu_percent(interval=1)
                memory_percent = psutil.virtual_memory().percent
                
                resource_samples.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent
                })
        
        def run_intensive_operations():
            # Run intensive CLI operations
            commands = [
                ["wallet", "--help"],
                ["blockchain", "--help"],
                ["multisig", "--help"],
                ["compliance", "--help"]
            ]
            
            for _ in range(20):
                for command in commands:
                    subprocess.run(
                        ["python", "-m", "aitbc_cli.main"] + command,
                        capture_output=True,
                        text=True,
                        cwd="/home/oib/windsurf/aitbc/cli"
                    )
        
        # Run monitoring and operations concurrently
        monitor_thread = threading.Thread(target=monitor_resources)
        operation_thread = threading.Thread(target=run_intensive_operations)
        
        monitor_thread.start()
        operation_thread.start()
        
        monitor_thread.join()
        operation_thread.join()
        
        # Analyze resource usage
        cpu_values = [sample["cpu_percent"] for sample in resource_samples]
        memory_values = [sample["memory_percent"] for sample in resource_samples]
        
        avg_cpu = statistics.mean(cpu_values)
        max_cpu = max(cpu_values)
        avg_memory = statistics.mean(memory_values)
        max_memory = max(memory_values)
        
        # Resource assertions
        assert avg_cpu < 70, f"Average CPU usage too high: {avg_cpu:.1f}%"
        assert max_cpu < 90, f"Maximum CPU usage too high: {max_cpu:.1f}%"
        assert avg_memory < 80, f"Average memory usage too high: {avg_memory:.1f}%"
        assert max_memory < 95, f"Maximum memory usage too high: {max_memory:.1f}%"
        
        print(f"System Resource Usage Results:")
        print(f"  Average CPU: {avg_cpu:.1f}% (max: {max_cpu:.1f}%)")
        print(f"  Average Memory: {avg_memory:.1f}% (max: {max_memory:.1f}%)")
        print(f"  Baseline CPU: {baseline_metrics['cpu_percent']:.1f}%")
        print(f"  Baseline Memory: {baseline_metrics['memory_percent']:.1f}%")
    
    def test_stress_test_cli(self, performance_config):
        """Stress test CLI with high load"""
        def stress_cli_worker(worker_id):
            results = []
            commands = [
                ["wallet", "--help"],
                ["blockchain", "--help"],
                ["multisig", "--help"],
                ["compliance", "--help"]
            ]
            
            for i in range(50):  # 50 operations per worker
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
                    "worker_id": worker_id,
                    "operation_id": i,
                    "success": result.returncode == 0,
                    "response_time": (end_time - start_time) * 1000
                })
            
            return results
        
        # Run stress test with multiple workers
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(stress_cli_worker, i) for i in range(5)]
            all_results = []
            
            for future in as_completed(futures):
                worker_results = future.result()
                all_results.extend(worker_results)
        
        # Analyze stress test results
        successful_operations = [r for r in all_results if r["success"]]
        response_times = [r["response_time"] for r in successful_operations]
        
        success_rate = len(successful_operations) / len(all_results)
        avg_response_time = statistics.mean(response_times) if response_times else 0
        p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max(response_times) if response_times else 0
        total_throughput = len(successful_operations) / 30  # operations per second
        
        # Stress test assertions (more lenient thresholds)
        assert success_rate >= 0.90, f"Low success rate under stress: {success_rate:.2%}"
        assert avg_response_time < 5000, f"Average response time too high under stress: {avg_response_time:.2f}ms"
        assert total_throughput >= 5, f"Throughput too low under stress: {total_throughput:.2f} ops/s"
        
        print(f"CLI Stress Test Results:")
        print(f"  Total operations: {len(all_results)}")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Average response time: {avg_response_time:.2f}ms")
        print(f"  95th percentile: {p95_response_time:.2f}ms")
        print(f"  Throughput: {total_throughput:.2f} ops/s")

class TestLoadTesting:
    """Load testing for high-volume scenarios"""
    
    def test_load_test_blockchain_operations(self, performance_config):
        """Load test blockchain operations"""
        # This would test blockchain operations under high load
        # Implementation depends on blockchain service availability
        pass
    
    def test_load_test_trading_operations(self, performance_config):
        """Load test trading operations"""
        # This would test trading operations under high load
        # Implementation depends on trading service availability
        pass

if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "--tb=short"])
