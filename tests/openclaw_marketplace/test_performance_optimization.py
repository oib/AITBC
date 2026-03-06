#!/usr/bin/env python3
"""
Marketplace Performance Optimization Tests
Phase 9.2: Marketplace Performance Optimization (Weeks 10-12)
"""

import pytest
import asyncio
import time
import json
import requests
import psutil
import statistics
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OptimizationStrategy(Enum):
    """Performance optimization strategies"""
    GPU_ACCELERATION = "gpu_acceleration"
    DISTRIBUTED_PROCESSING = "distributed_processing"
    CACHING_OPTIMIZATION = "caching_optimization"
    LOAD_BALANCING = "load_balancing"
    RESOURCE_SCALING = "resource_scaling"
    QUERY_OPTIMIZATION = "query_optimization"

class PerformanceMetric(Enum):
    """Performance metrics to monitor"""
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    GPU_UTILIZATION = "gpu_utilization"
    MEMORY_USAGE = "memory_usage"
    CPU_UTILIZATION = "cpu_utilization"
    NETWORK_LATENCY = "network_latency"
    CACHE_HIT_RATE = "cache_hit_rate"

@dataclass
class PerformanceBaseline:
    """Performance baseline for comparison"""
    metric_name: str
    baseline_value: float
    target_value: float
    measurement_unit: str
    tolerance: float = 0.1
    
@dataclass
class OptimizationResult:
    """Result of optimization test"""
    strategy: OptimizationStrategy
    baseline_performance: Dict[str, float]
    optimized_performance: Dict[str, float]
    improvement_percentage: float
    resource_usage_change: Dict[str, float]
    optimization_time: float
    success: bool

@dataclass
class LoadTestConfig:
    """Load testing configuration"""
    concurrent_users: int
    requests_per_second: int
    test_duration_seconds: int
    ramp_up_period_seconds: int
    think_time_seconds: float = 0.5

class MarketplacePerformanceTests:
    """Test suite for marketplace performance optimization"""
    
    def __init__(self, marketplace_url: str = "http://127.0.0.1:18000"):
        self.marketplace_url = marketplace_url
        self.baselines = self._setup_baselines()
        self.session = requests.Session()
        self.session.timeout = 30
        self.performance_history = []
        
    def _setup_baselines(self) -> Dict[PerformanceMetric, PerformanceBaseline]:
        """Setup performance baselines for optimization"""
        return {
            PerformanceMetric.RESPONSE_TIME: PerformanceBaseline(
                metric_name="response_time",
                baseline_value=200.0,  # 200ms baseline
                target_value=50.0,     # 50ms target
                measurement_unit="ms",
                tolerance=0.2
            ),
            PerformanceMetric.THROUGHPUT: PerformanceBaseline(
                metric_name="throughput",
                baseline_value=100.0,   # 100 req/s baseline
                target_value=1000.0,    # 1000 req/s target
                measurement_unit="req/s",
                tolerance=0.15
            ),
            PerformanceMetric.GPU_UTILIZATION: PerformanceBaseline(
                metric_name="gpu_utilization",
                baseline_value=0.60,    # 60% baseline
                target_value=0.90,      # 90% target
                measurement_unit="percentage",
                tolerance=0.1
            ),
            PerformanceMetric.MEMORY_USAGE: PerformanceBaseline(
                metric_name="memory_usage",
                baseline_value=70.0,    # 70% baseline
                target_value=85.0,      # 85% target (efficient use)
                measurement_unit="percentage",
                tolerance=0.15
            ),
            PerformanceMetric.CACHE_HIT_RATE: PerformanceBaseline(
                metric_name="cache_hit_rate",
                baseline_value=0.40,    # 40% baseline
                target_value=0.85,      # 85% target
                measurement_unit="percentage",
                tolerance=0.1
            )
        }
        
    async def measure_current_performance(self) -> Dict[str, float]:
        """Measure current marketplace performance"""
        try:
            # Test basic endpoint performance
            start_time = time.time()
            response = self.session.get(f"{self.marketplace_url}/v1/marketplace/status", timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_info = psutil.virtual_memory()
            memory_percent = memory_info.percent
            
            # Get marketplace-specific metrics
            metrics_response = self.session.get(f"{self.marketplace_url}/v1/metrics/current", timeout=10)
            
            if metrics_response.status_code == 200:
                marketplace_metrics = metrics_response.json()
            else:
                marketplace_metrics = {}
                
            current_performance = {
                "response_time": response_time,
                "cpu_utilization": cpu_percent,
                "memory_usage": memory_percent,
                "gpu_utilization": marketplace_metrics.get("gpu_utilization", 0.0),
                "cache_hit_rate": marketplace_metrics.get("cache_hit_rate", 0.0),
                "throughput": marketplace_metrics.get("throughput", 0.0),
                "active_connections": marketplace_metrics.get("active_connections", 0),
                "error_rate": marketplace_metrics.get("error_rate", 0.0)
            }
            
            self.performance_history.append({
                "timestamp": datetime.now(),
                "metrics": current_performance
            })
            
            return current_performance
            
        except Exception as e:
            logger.error(f"Performance measurement failed: {e}")
            return {}
            
    async def test_gpu_acceleration_optimization(self) -> OptimizationResult:
        """Test GPU acceleration optimization for marketplace"""
        try:
            # Measure baseline performance
            baseline_performance = await self.measure_current_performance()
            
            # Enable GPU acceleration
            optimization_payload = {
                "optimization_strategy": "gpu_acceleration",
                "gpu_acceleration_config": {
                    "enable_gpu_processing": True,
                    "gpu_memory_fraction": 0.8,
                    "batch_processing_size": 32,
                    "cuda_streams": 4,
                    "memory_optimization": True
                },
                "target_endpoints": [
                    "/v1/marketplace/search",
                    "/v1/marketplace/recommend",
                    "/v1/analytics/marketplace"
                ]
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/optimization/apply",
                json=optimization_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                optimization_result = response.json()
                
                # Wait for optimization to take effect
                await asyncio.sleep(5)
                
                # Measure optimized performance
                optimized_performance = await self.measure_current_performance()
                
                # Calculate improvements
                response_time_improvement = (
                    (baseline_performance.get("response_time", 0) - optimized_performance.get("response_time", 0))
                    / baseline_performance.get("response_time", 1) * 100
                )
                
                throughput_improvement = (
                    (optimized_performance.get("throughput", 0) - baseline_performance.get("throughput", 0))
                    / baseline_performance.get("throughput", 1) * 100
                )
                
                gpu_utilization_change = (
                    optimized_performance.get("gpu_utilization", 0) - baseline_performance.get("gpu_utilization", 0)
                )
                
                overall_improvement = (response_time_improvement + throughput_improvement) / 2
                
                return OptimizationResult(
                    strategy=OptimizationStrategy.GPU_ACCELERATION,
                    baseline_performance=baseline_performance,
                    optimized_performance=optimized_performance,
                    improvement_percentage=overall_improvement,
                    resource_usage_change={
                        "gpu_utilization": gpu_utilization_change,
                        "memory_usage": optimized_performance.get("memory_usage", 0) - baseline_performance.get("memory_usage", 0),
                        "cpu_utilization": optimized_performance.get("cpu_utilization", 0) - baseline_performance.get("cpu_utilization", 0)
                    },
                    optimization_time=optimization_result.get("optimization_time", 0),
                    success=True
                )
            else:
                return OptimizationResult(
                    strategy=OptimizationStrategy.GPU_ACCELERATION,
                    baseline_performance=baseline_performance,
                    optimized_performance={},
                    improvement_percentage=0,
                    resource_usage_change={},
                    optimization_time=0,
                    success=False
                )
                
        except Exception as e:
            logger.error(f"GPU acceleration optimization test failed: {e}")
            return OptimizationResult(
                strategy=OptimizationStrategy.GPU_ACCELERATION,
                baseline_performance={},
                optimized_performance={},
                improvement_percentage=0,
                resource_usage_change={},
                optimization_time=0,
                success=False
            )
            
    async def test_distributed_processing_optimization(self) -> OptimizationResult:
        """Test distributed processing framework optimization"""
        try:
            # Measure baseline performance
            baseline_performance = await self.measure_current_performance()
            
            # Enable distributed processing
            optimization_payload = {
                "optimization_strategy": "distributed_processing",
                "distributed_config": {
                    "enable_distributed_processing": True,
                    "worker_nodes": 4,
                    "task_distribution": "round_robin",
                    "load_balancing_algorithm": "least_connections",
                    "fault_tolerance": True,
                    "replication_factor": 2
                },
                "target_workloads": [
                    "bulk_data_processing",
                    "analytics_computation",
                    "recommendation_generation"
                ]
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/optimization/apply",
                json=optimization_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                optimization_result = response.json()
                
                # Wait for optimization to take effect
                await asyncio.sleep(5)
                
                # Measure optimized performance
                optimized_performance = await self.measure_current_performance()
                
                # Calculate improvements
                throughput_improvement = (
                    (optimized_performance.get("throughput", 0) - baseline_performance.get("throughput", 0))
                    / baseline_performance.get("throughput", 1) * 100
                )
                
                response_time_improvement = (
                    (baseline_performance.get("response_time", 0) - optimized_performance.get("response_time", 0))
                    / baseline_performance.get("response_time", 1) * 100
                )
                
                overall_improvement = (throughput_improvement + response_time_improvement) / 2
                
                return OptimizationResult(
                    strategy=OptimizationStrategy.DISTRIBUTED_PROCESSING,
                    baseline_performance=baseline_performance,
                    optimized_performance=optimized_performance,
                    improvement_percentage=overall_improvement,
                    resource_usage_change={
                        "cpu_utilization": optimized_performance.get("cpu_utilization", 0) - baseline_performance.get("cpu_utilization", 0),
                        "memory_usage": optimized_performance.get("memory_usage", 0) - baseline_performance.get("memory_usage", 0),
                        "network_latency": optimized_performance.get("network_latency", 0) - baseline_performance.get("network_latency", 0)
                    },
                    optimization_time=optimization_result.get("optimization_time", 0),
                    success=True
                )
            else:
                return OptimizationResult(
                    strategy=OptimizationStrategy.DISTRIBUTED_PROCESSING,
                    baseline_performance=baseline_performance,
                    optimized_performance={},
                    improvement_percentage=0,
                    resource_usage_change={},
                    optimization_time=0,
                    success=False
                )
                
        except Exception as e:
            logger.error(f"Distributed processing optimization test failed: {e}")
            return OptimizationResult(
                strategy=OptimizationStrategy.DISTRIBUTED_PROCESSING,
                baseline_performance={},
                optimized_performance={},
                improvement_percentage=0,
                resource_usage_change={},
                optimization_time=0,
                success=False
            )
            
    async def test_caching_optimization(self) -> OptimizationResult:
        """Test advanced caching and optimization"""
        try:
            # Measure baseline performance
            baseline_performance = await self.measure_current_performance()
            
            # Enable advanced caching
            optimization_payload = {
                "optimization_strategy": "caching_optimization",
                "caching_config": {
                    "enable_redis_cache": True,
                    "cache_ttl_seconds": 300,
                    "cache_size_mb": 1024,
                    "cache_strategy": "lru_with_write_through",
                    "enable_query_result_cache": True,
                    "enable_session_cache": True,
                    "compression_enabled": True
                },
                "cache_targets": [
                    "marketplace_listings",
                    "agent_profiles",
                    "pricing_data",
                    "analytics_results"
                ]
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/optimization/apply",
                json=optimization_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                optimization_result = response.json()
                
                # Wait for cache warming
                await asyncio.sleep(10)
                
                # Measure optimized performance
                optimized_performance = await self.measure_current_performance()
                
                # Calculate improvements
                cache_hit_rate_improvement = (
                    (optimized_performance.get("cache_hit_rate", 0) - baseline_performance.get("cache_hit_rate", 0))
                    * 100
                )
                
                response_time_improvement = (
                    (baseline_performance.get("response_time", 0) - optimized_performance.get("response_time", 0))
                    / baseline_performance.get("response_time", 1) * 100
                )
                
                overall_improvement = (cache_hit_rate_improvement + response_time_improvement) / 2
                
                return OptimizationResult(
                    strategy=OptimizationStrategy.CACHING_OPTIMIZATION,
                    baseline_performance=baseline_performance,
                    optimized_performance=optimized_performance,
                    improvement_percentage=overall_improvement,
                    resource_usage_change={
                        "memory_usage": optimized_performance.get("memory_usage", 0) - baseline_performance.get("memory_usage", 0),
                        "cache_hit_rate": optimized_performance.get("cache_hit_rate", 0) - baseline_performance.get("cache_hit_rate", 0),
                        "response_time": baseline_performance.get("response_time", 0) - optimized_performance.get("response_time", 0)
                    },
                    optimization_time=optimization_result.get("optimization_time", 0),
                    success=True
                )
            else:
                return OptimizationResult(
                    strategy=OptimizationStrategy.CACHING_OPTIMIZATION,
                    baseline_performance=baseline_performance,
                    optimized_performance={},
                    improvement_percentage=0,
                    resource_usage_change={},
                    optimization_time=0,
                    success=False
                )
                
        except Exception as e:
            logger.error(f"Caching optimization test failed: {e}")
            return OptimizationResult(
                strategy=OptimizationStrategy.CACHING_OPTIMIZATION,
                baseline_performance={},
                optimized_performance={},
                improvement_percentage=0,
                resource_usage_change={},
                optimization_time=0,
                success=False
            )
            
    async def test_load_balancing_optimization(self) -> OptimizationResult:
        """Test load balancing optimization"""
        try:
            # Measure baseline performance
            baseline_performance = await self.measure_current_performance()
            
            # Enable advanced load balancing
            optimization_payload = {
                "optimization_strategy": "load_balancing",
                "load_balancing_config": {
                    "algorithm": "weighted_round_robin",
                    "health_check_interval": 30,
                    "failover_enabled": True,
                    "connection_pool_size": 100,
                    "max_connections_per_node": 50,
                    "sticky_sessions": False
                },
                "backend_nodes": [
                    {"node_id": "node_1", "weight": 3, "max_connections": 50},
                    {"node_id": "node_2", "weight": 2, "max_connections": 40},
                    {"node_id": "node_3", "weight": 1, "max_connections": 30}
                ]
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/optimization/apply",
                json=optimization_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                optimization_result = response.json()
                
                # Wait for load balancer configuration
                await asyncio.sleep(5)
                
                # Measure optimized performance
                optimized_performance = await self.measure_current_performance()
                
                # Calculate improvements
                throughput_improvement = (
                    (optimized_performance.get("throughput", 0) - baseline_performance.get("throughput", 0))
                    / baseline_performance.get("throughput", 1) * 100
                )
                
                response_time_improvement = (
                    (baseline_performance.get("response_time", 0) - optimized_performance.get("response_time", 0))
                    / baseline_performance.get("response_time", 1) * 100
                )
                
                error_rate_improvement = (
                    (baseline_performance.get("error_rate", 0) - optimized_performance.get("error_rate", 0))
                    / max(baseline_performance.get("error_rate", 0.01), 0.01) * 100
                )
                
                overall_improvement = (throughput_improvement + response_time_improvement + error_rate_improvement) / 3
                
                return OptimizationResult(
                    strategy=OptimizationStrategy.LOAD_BALANCING,
                    baseline_performance=baseline_performance,
                    optimized_performance=optimized_performance,
                    improvement_percentage=overall_improvement,
                    resource_usage_change={
                        "active_connections": optimized_performance.get("active_connections", 0) - baseline_performance.get("active_connections", 0),
                        "error_rate": baseline_performance.get("error_rate", 0) - optimized_performance.get("error_rate", 0),
                        "response_time": baseline_performance.get("response_time", 0) - optimized_performance.get("response_time", 0)
                    },
                    optimization_time=optimization_result.get("optimization_time", 0),
                    success=True
                )
            else:
                return OptimizationResult(
                    strategy=OptimizationStrategy.LOAD_BALANCING,
                    baseline_performance=baseline_performance,
                    optimized_performance={},
                    improvement_percentage=0,
                    resource_usage_change={},
                    optimization_time=0,
                    success=False
                )
                
        except Exception as e:
            logger.error(f"Load balancing optimization test failed: {e}")
            return OptimizationResult(
                strategy=OptimizationStrategy.LOAD_BALANCING,
                baseline_performance={},
                optimized_performance={},
                improvement_percentage=0,
                resource_usage_change={},
                optimization_time=0,
                success=False
            )
            
    async def test_adaptive_resource_scaling(self) -> OptimizationResult:
        """Test adaptive resource scaling for marketplace demand"""
        try:
            # Measure baseline performance
            baseline_performance = await self.measure_current_performance()
            
            # Enable adaptive scaling
            optimization_payload = {
                "optimization_strategy": "resource_scaling",
                "scaling_config": {
                    "enable_auto_scaling": True,
                    "scaling_policy": "demand_based",
                    "min_instances": 2,
                    "max_instances": 10,
                    "scale_up_threshold": 80,  # CPU/memory threshold
                    "scale_down_threshold": 30,
                    "cooldown_period": 300,
                    "target_utilization": 70
                },
                "scaling_metrics": [
                    "cpu_utilization",
                    "memory_usage",
                    "request_rate",
                    "response_time"
                ]
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/optimization/apply",
                json=optimization_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                optimization_result = response.json()
                
                # Simulate load increase to trigger scaling
                await self._simulate_load_increase()
                
                # Wait for scaling to complete
                await asyncio.sleep(15)
                
                # Measure optimized performance
                optimized_performance = await self.measure_current_performance()
                
                # Calculate improvements
                throughput_improvement = (
                    (optimized_performance.get("throughput", 0) - baseline_performance.get("throughput", 0))
                    / baseline_performance.get("throughput", 1) * 100
                )
                
                resource_efficiency = (
                    (baseline_performance.get("cpu_utilization", 0) - optimized_performance.get("cpu_utilization", 0))
                    / baseline_performance.get("cpu_utilization", 1) * 100
                )
                
                overall_improvement = (throughput_improvement + resource_efficiency) / 2
                
                return OptimizationResult(
                    strategy=OptimizationStrategy.RESOURCE_SCALING,
                    baseline_performance=baseline_performance,
                    optimized_performance=optimized_performance,
                    improvement_percentage=overall_improvement,
                    resource_usage_change={
                        "cpu_utilization": optimized_performance.get("cpu_utilization", 0) - baseline_performance.get("cpu_utilization", 0),
                        "memory_usage": optimized_performance.get("memory_usage", 0) - baseline_performance.get("memory_usage", 0),
                        "active_instances": optimization_result.get("current_instances", 1) - 1
                    },
                    optimization_time=optimization_result.get("optimization_time", 0),
                    success=True
                )
            else:
                return OptimizationResult(
                    strategy=OptimizationStrategy.RESOURCE_SCALING,
                    baseline_performance=baseline_performance,
                    optimized_performance={},
                    improvement_percentage=0,
                    resource_usage_change={},
                    optimization_time=0,
                    success=False
                )
                
        except Exception as e:
            logger.error(f"Adaptive resource scaling test failed: {e}")
            return OptimizationResult(
                strategy=OptimizationStrategy.RESOURCE_SCALING,
                baseline_performance={},
                optimized_performance={},
                improvement_percentage=0,
                resource_usage_change={},
                optimization_time=0,
                success=False
            )
            
    async def test_real_time_performance_monitoring(self) -> Dict[str, Any]:
        """Test real-time marketplace performance monitoring"""
        try:
            # Start performance monitoring
            monitoring_payload = {
                "monitoring_config": {
                    "enable_real_time_monitoring": True,
                    "sampling_interval": 5,  # seconds
                    "metrics_to_track": [
                        "response_time",
                        "throughput",
                        "error_rate",
                        "gpu_utilization",
                        "memory_usage"
                    ],
                    "alert_thresholds": {
                        "response_time": 100,  # ms
                        "error_rate": 0.05,    # 5%
                        "memory_usage": 90     # %
                    }
                }
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/monitoring/start",
                json=monitoring_payload,
                timeout=15
            )
            
            if response.status_code == 200:
                monitoring_result = response.json()
                
                # Collect monitoring data for 30 seconds
                await asyncio.sleep(30)
                
                # Get monitoring summary
                summary_response = self.session.get(
                    f"{self.marketplace_url}/v1/monitoring/summary",
                    timeout=10
                )
                
                if summary_response.status_code == 200:
                    summary_data = summary_response.json()
                    
                    return {
                        "monitoring_active": True,
                        "monitoring_period": 30,
                        "metrics_collected": summary_data.get("metrics_collected", {}),
                        "performance_summary": summary_data.get("performance_summary", {}),
                        "alerts_triggered": summary_data.get("alerts", []),
                        "data_points": summary_data.get("data_points", 0),
                        "success": True
                    }
                else:
                    return {
                        "monitoring_active": True,
                        "error": f"Failed to get monitoring summary: {summary_response.status_code}",
                        "success": False
                    }
            else:
                return {
                    "error": f"Failed to start monitoring: {response.status_code}",
                    "success": False
                }
                
        except Exception as e:
            return {
                "error": str(e),
                "success": False
            }
            
    async def _simulate_load_increase(self):
        """Simulate increased load to trigger scaling"""
        try:
            # Generate concurrent requests to increase load
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = []
                for i in range(50):
                    future = executor.submit(
                        self.session.get,
                        f"{self.marketplace_url}/v1/marketplace/search",
                        timeout=5
                    )
                    futures.append(future)
                
                # Wait for all requests to complete
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        pass  # Ignore errors during load simulation
                        
        except Exception as e:
            logger.error(f"Load simulation failed: {e}")
            
    async def run_load_test(self, config: LoadTestConfig) -> Dict[str, Any]:
        """Run comprehensive load test"""
        try:
            results = {
                "test_config": asdict(config),
                "start_time": datetime.now(),
                "request_results": [],
                "performance_metrics": {}
            }
            
            # Calculate total requests
            total_requests = config.requests_per_second * config.test_duration_seconds
            
            # Run load test
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=config.concurrent_users) as executor:
                futures = []
                
                for request_id in range(total_requests):
                    # Calculate delay for target RPS
                    delay = request_id / config.requests_per_second
                    
                    future = executor.submit(
                        self._make_request_with_delay,
                        delay,
                        request_id
                    )
                    futures.append(future)
                
                # Collect results
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results["request_results"].append(result)
                    except Exception as e:
                        results["request_results"].append({
                            "request_id": None,
                            "success": False,
                            "error": str(e),
                            "response_time": 0
                        })
            
            end_time = time.time()
            results["end_time"] = datetime.now()
            results["total_test_time"] = end_time - start_time
            
            # Calculate performance metrics
            successful_requests = [r for r in results["request_results"] if r["success"]]
            failed_requests = [r for r in results["request_results"] if not r["success"]]
            
            if successful_requests:
                response_times = [r["response_time"] for r in successful_requests]
                results["performance_metrics"] = {
                    "total_requests": len(results["request_results"]),
                    "successful_requests": len(successful_requests),
                    "failed_requests": len(failed_requests),
                    "success_rate": len(successful_requests) / len(results["request_results"]) * 100,
                    "average_response_time": statistics.mean(response_times),
                    "median_response_time": statistics.median(response_times),
                    "min_response_time": min(response_times),
                    "max_response_time": max(response_times),
                    "p95_response_time": np.percentile(response_times, 95),
                    "p99_response_time": np.percentile(response_times, 99),
                    "requests_per_second": len(successful_requests) / (end_time - start_time),
                    "error_rate": len(failed_requests) / len(results["request_results"]) * 100
                }
            else:
                results["performance_metrics"] = {
                    "total_requests": len(results["request_results"]),
                    "successful_requests": 0,
                    "failed_requests": len(failed_requests),
                    "success_rate": 0,
                    "error_rate": 100
                }
                
            return results
            
        except Exception as e:
            return {
                "error": str(e),
                "success": False
            }
            
    def _make_request_with_delay(self, delay: float, request_id: int) -> Dict[str, Any]:
        """Make HTTP request with delay for load testing"""
        try:
            # Wait for calculated delay
            time.sleep(max(0, delay - time.time()))
            
            start_time = time.time()
            response = self.session.get(
                f"{self.marketplace_url}/v1/marketplace/status",
                timeout=10
            )
            end_time = time.time()
            
            return {
                "request_id": request_id,
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "response_time": (end_time - start_time) * 1000,  # Convert to ms
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            return {
                "request_id": request_id,
                "success": False,
                "error": str(e),
                "response_time": 0,
                "timestamp": datetime.now()
            }

# Test Fixtures
@pytest.fixture
async def performance_tests():
    """Create marketplace performance test instance"""
    return MarketplacePerformanceTests()

@pytest.fixture
def load_test_config():
    """Load test configuration"""
    return LoadTestConfig(
        concurrent_users=10,
        requests_per_second=50,
        test_duration_seconds=30,
        ramp_up_period_seconds=5
    )

# Test Classes
class TestGPUAcceleration:
    """Test GPU acceleration optimization"""
    
    @pytest.mark.asyncio
    async def test_gpu_optimization_enabled(self, performance_tests):
        """Test GPU acceleration optimization"""
        result = await performance_tests.test_gpu_acceleration_optimization()
        
        assert result.success, "GPU acceleration optimization failed"
        assert result.improvement_percentage > 0, "No performance improvement detected"
        assert "gpu_utilization" in result.resource_usage_change, "No GPU utilization change measured"
        assert result.optimized_performance.get("gpu_utilization", 0) > result.baseline_performance.get("gpu_utilization", 0), "GPU utilization not increased"
        
    @pytest.mark.asyncio
    async def test_gpu_memory_optimization(self, performance_tests):
        """Test GPU memory optimization"""
        result = await performance_tests.test_gpu_acceleration_optimization()
        
        assert result.success, "GPU memory optimization test failed"
        assert result.optimized_performance.get("memory_usage", 0) <= 90, "Memory usage too high after optimization"

class TestDistributedProcessing:
    """Test distributed processing framework"""
    
    @pytest.mark.asyncio
    async def test_distributed_processing_setup(self, performance_tests):
        """Test distributed processing setup"""
        result = await performance_tests.test_distributed_processing_optimization()
        
        assert result.success, "Distributed processing optimization failed"
        assert result.improvement_percentage > 0, "No throughput improvement detected"
        assert result.optimized_performance.get("throughput", 0) > result.baseline_performance.get("throughput", 0), "Throughput not improved"
        
    @pytest.mark.asyncio
    async def test_fault_tolerance(self, performance_tests):
        """Test fault tolerance in distributed processing"""
        result = await performance_tests.test_distributed_processing_optimization()
        
        assert result.success, "Fault tolerance test failed"
        assert result.optimized_performance.get("error_rate", 1.0) < 0.05, "Error rate too high"

class TestCachingOptimization:
    """Test advanced caching optimization"""
    
    @pytest.mark.asyncio
    async def test_cache_hit_rate_improvement(self, performance_tests):
        """Test cache hit rate improvement"""
        result = await performance_tests.test_caching_optimization()
        
        assert result.success, "Caching optimization failed"
        assert result.optimized_performance.get("cache_hit_rate", 0) > 0.8, "Cache hit rate too low"
        assert result.resource_usage_change.get("cache_hit_rate", 0) > 0.4, "Cache hit rate improvement too low"
        
    @pytest.mark.asyncio
    async def test_response_time_improvement(self, performance_tests):
        """Test response time improvement through caching"""
        result = await performance_tests.test_caching_optimization()
        
        assert result.success, "Response time optimization failed"
        assert result.optimized_performance.get("response_time", 1000) < result.baseline_performance.get("response_time", 1000), "Response time not improved"

class TestLoadBalancing:
    """Test load balancing optimization"""
    
    @pytest.mark.asyncio
    async def test_load_balancer_setup(self, performance_tests):
        """Test load balancer setup and configuration"""
        result = await performance_tests.test_load_balancing_optimization()
        
        assert result.success, "Load balancing optimization failed"
        assert result.optimized_performance.get("throughput", 0) > result.baseline_performance.get("throughput", 0), "Throughput not improved"
        assert result.optimized_performance.get("error_rate", 1.0) < result.baseline_performance.get("error_rate", 1.0), "Error rate not reduced"
        
    @pytest.mark.asyncio
    async def test_connection_distribution(self, performance_tests):
        """Test connection distribution across nodes"""
        result = await performance_tests.test_load_balancing_optimization()
        
        assert result.success, "Connection distribution test failed"
        assert result.resource_usage_change.get("active_connections", 0) > 0, "No active connections change"

class TestAdaptiveScaling:
    """Test adaptive resource scaling"""
    
    @pytest.mark.asyncio
    async def test_auto_scaling_triggered(self, performance_tests):
        """Test automatic scaling trigger"""
        result = await performance_tests.test_adaptive_resource_scaling()
        
        assert result.success, "Adaptive scaling test failed"
        assert result.resource_usage_change.get("active_instances", 0) > 0, "No scaling occurred"
        assert result.optimized_performance.get("throughput", 0) > result.baseline_performance.get("throughput", 0), "Throughput not improved after scaling"
        
    @pytest.mark.asyncio
    async def test_resource_efficiency(self, performance_tests):
        """Test resource efficiency after scaling"""
        result = await performance_tests.test_adaptive_resource_scaling()
        
        assert result.success, "Resource efficiency test failed"
        assert result.optimized_performance.get("cpu_utilization", 100) < 80, "CPU utilization too high after scaling"

class TestRealTimeMonitoring:
    """Test real-time performance monitoring"""
    
    @pytest.mark.asyncio
    async def test_monitoring_setup(self, performance_tests):
        """Test real-time monitoring setup"""
        result = await performance_tests.test_real_time_performance_monitoring()
        
        assert result.get("success", False), "Real-time monitoring setup failed"
        assert result.get("monitoring_active", False), "Monitoring not active"
        assert result.get("data_points", 0) > 0, "No data points collected"
        
    @pytest.mark.asyncio
    async def test_performance_metrics_collection(self, performance_tests):
        """Test performance metrics collection"""
        result = await performance_tests.test_real_time_performance_monitoring()
        
        assert result.get("success", False), "Performance metrics collection failed"
        assert "performance_summary" in result, "No performance summary provided"
        assert "metrics_collected" in result, "No metrics collected"

class TestLoadTesting:
    """Test comprehensive load testing"""
    
    @pytest.mark.asyncio
    async def test_basic_load_test(self, performance_tests, load_test_config):
        """Test basic load test functionality"""
        result = await performance_tests.run_load_test(load_test_config)
        
        assert "error" not in result, "Load test failed with error"
        assert result.get("performance_metrics", {}).get("success_rate", 0) > 95, "Success rate too low"
        assert result.get("performance_metrics", {}).get("average_response_time", 10000) < 1000, "Average response time too high"
        
    @pytest.mark.asyncio
    async def test_throughput_measurement(self, performance_tests, load_test_config):
        """Test throughput measurement accuracy"""
        result = await performance_tests.run_load_test(load_test_config)
        
        assert "error" not in result, "Throughput measurement failed"
        actual_rps = result.get("performance_metrics", {}).get("requests_per_second", 0)
        target_rps = load_test_config.requests_per_second
        assert abs(actual_rps - target_rps) / target_rps < 0.1, f"Throughput not accurate: expected {target_rps}, got {actual_rps}"
        
    @pytest.mark.asyncio
    async def test_response_time_distribution(self, performance_tests, load_test_config):
        """Test response time distribution"""
        result = await performance_tests.run_load_test(load_test_config)
        
        assert "error" not in result, "Response time distribution test failed"
        metrics = result.get("performance_metrics", {})
        assert metrics.get("p95_response_time", 10000) < 500, "P95 response time too high"
        assert metrics.get("p99_response_time", 10000) < 1000, "P99 response time too high"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
