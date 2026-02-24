"""
Performance Benchmark Tests for Enhanced Services
Validates performance claims from deployment report
"""

import asyncio
import httpx
import pytest
import json
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import psutil

# Performance targets from deployment report
PERFORMANCE_TARGETS = {
    "multimodal": {
        "text_processing": {"max_time": 0.02, "min_accuracy": 0.92},
        "image_processing": {"max_time": 0.15, "min_accuracy": 0.87},
        "audio_processing": {"max_time": 0.22, "min_accuracy": 0.89},
        "video_processing": {"max_time": 0.35, "min_accuracy": 0.85},
        "tabular_processing": {"max_time": 0.05, "min_accuracy": 0.95},
        "graph_processing": {"max_time": 0.08, "min_accuracy": 0.91}
    },
    "gpu_multimodal": {
        "cross_modal_attention": {"min_speedup": 10.0, "max_memory": 2.5},
        "multi_modal_fusion": {"min_speedup": 20.0, "max_memory": 2.0},
        "feature_extraction": {"min_speedup": 20.0, "max_memory": 3.0},
        "agent_inference": {"min_speedup": 9.0, "max_memory": 1.5},
        "learning_training": {"min_speedup": 9.4, "max_memory": 9.0}
    },
    "modality_optimization": {
        "compression_ratio": {"min_ratio": 0.3, "max_ratio": 0.5},
        "speedup": {"min_speedup": 150.0, "max_speedup": 220.0},
        "accuracy_retention": {"min_accuracy": 0.93}
    },
    "adaptive_learning": {
        "processing_time": {"max_time": 0.12},
        "convergence_episodes": {"max_episodes": 200},
        "final_reward": {"min_reward": 0.85}
    },
    "marketplace_enhanced": {
        "transaction_processing": {"max_time": 0.03},
        "royalty_calculation": {"max_time": 0.01},
        "license_verification": {"max_time": 0.02},
        "analytics_generation": {"max_time": 0.05}
    },
    "openclaw_enhanced": {
        "agent_deployment": {"max_time": 0.05},
        "orchestration_latency": {"max_time": 0.02},
        "edge_deployment": {"max_time": 0.08},
        "hybrid_efficiency": {"min_efficiency": 0.80}
    }
}

# Service endpoints
SERVICES = {
    "multimodal": "http://localhost:8002",
    "gpu_multimodal": "http://localhost:8003",
    "modality_optimization": "http://localhost:8004",
    "adaptive_learning": "http://localhost:8005",
    "marketplace_enhanced": "http://localhost:8006",
    "openclaw_enhanced": "http://localhost:8007"
}


class PerformanceBenchmarkTester:
    """Performance testing framework for enhanced services"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        self.results = {}
        self.system_metrics = {}
    
    async def setup_test_environment(self) -> bool:
        """Setup and verify all services"""
        print("🔧 Setting up performance benchmark environment...")
        
        # Check system resources
        self.system_metrics = {
            "cpu_cores": psutil.cpu_count(),
            "memory_total_gb": psutil.virtual_memory().total / (1024**3),
            "memory_available_gb": psutil.virtual_memory().available / (1024**3),
            "disk_free_gb": psutil.disk_usage('/').free / (1024**3)
        }
        
        print(f"  🖥️  System: {self.system_metrics['cpu_cores']} cores, {self.system_metrics['memory_total_gb']:.1f}GB RAM")
        
        # Check services
        healthy_services = []
        for service_name, service_url in SERVICES.items():
            try:
                response = await self.client.get(f"{service_url}/health")
                if response.status_code == 200:
                    healthy_services.append(service_name)
                    print(f"  ✅ {service_name} healthy")
                else:
                    print(f"  ❌ {service_name} unhealthy: {response.status_code}")
            except Exception as e:
                print(f"  ❌ {service_name} unavailable: {e}")
        
        if len(healthy_services) < 4:
            print(f"  ⚠️  Only {len(healthy_services)}/{len(SERVICES)} services available")
            return False
        
        print("  ✅ Performance benchmark environment ready")
        return True
    
    async def cleanup_test_environment(self):
        """Cleanup test environment"""
        await self.client.aclose()
    
    async def benchmark_multimodal_performance(self) -> Dict[str, Any]:
        """Benchmark multi-modal processing performance"""
        print("\n🤖 Benchmarking Multi-Modal Performance...")
        
        results = {}
        
        # Test text processing
        print("  📝 Testing text processing...")
        text_times = []
        for i in range(10):
            start_time = time.time()
            response = await self.client.post(
                f"{SERVICES['multimodal']}/process",
                json={
                    "agent_id": f"benchmark-text-{i}",
                    "inputs": {"text": "This is a benchmark test for text processing performance."},
                    "processing_mode": "text_analysis"
                }
            )
            end_time = time.time()
            
            if response.status_code == 200:
                text_times.append(end_time - start_time)
        
        if text_times:
            avg_time = statistics.mean(text_times)
            target = PERFORMANCE_TARGETS["multimodal"]["text_processing"]
            results["text_processing"] = {
                "avg_time": avg_time,
                "target_time": target["max_time"],
                "meets_target": avg_time <= target["max_time"],
                "samples": len(text_times)
            }
            status = "✅" if results["text_processing"]["meets_target"] else "❌"
            print(f"    {status} Text: {avg_time:.3f}s (target: ≤{target['max_time']}s)")
        
        # Test image processing
        print("  🖼️  Testing image processing...")
        image_times = []
        for i in range(5):  # Fewer samples for image processing
            start_time = time.time()
            response = await self.client.post(
                f"{SERVICES['multimodal']}/process",
                json={
                    "agent_id": f"benchmark-image-{i}",
                    "inputs": {"image_url": "https://example.com/test-image.jpg", "format": "jpeg"},
                    "processing_mode": "image_analysis"
                }
            )
            end_time = time.time()
            
            if response.status_code == 200:
                image_times.append(end_time - start_time)
        
        if image_times:
            avg_time = statistics.mean(image_times)
            target = PERFORMANCE_TARGETS["multimodal"]["image_processing"]
            results["image_processing"] = {
                "avg_time": avg_time,
                "target_time": target["max_time"],
                "meets_target": avg_time <= target["max_time"],
                "samples": len(image_times)
            }
            status = "✅" if results["image_processing"]["meets_target"] else "❌"
            print(f"    {status} Image: {avg_time:.3f}s (target: ≤{target['max_time']}s)")
        
        return results
    
    async def benchmark_gpu_performance(self) -> Dict[str, Any]:
        """Benchmark GPU acceleration performance"""
        print("\n🚀 Benchmarking GPU Performance...")
        
        results = {}
        
        # Check GPU availability first
        gpu_health = await self.client.get(f"{SERVICES['gpu_multimodal']}/health")
        if gpu_health.status_code != 200:
            print("  ❌ GPU service not available")
            return {"error": "GPU service not available"}
        
        gpu_info = gpu_health.json().get("gpu", {})
        if not gpu_info.get("available", False):
            print("  ❌ GPU not available")
            return {"error": "GPU not available"}
        
        print(f"  🎮 GPU: {gpu_info.get('name', 'Unknown')} ({gpu_info.get('memory_total_gb', 0)}GB)")
        
        # Test cross-modal attention
        print("  🧠 Testing cross-modal attention...")
        attention_speedups = []
        
        for i in range(5):
            # GPU processing
            start_time = time.time()
            gpu_response = await self.client.post(
                f"{SERVICES['gpu_multimodal']}/attention",
                json={
                    "modality_features": {
                        "text": [0.1, 0.2, 0.3, 0.4, 0.5] * 20,
                        "image": [0.5, 0.4, 0.3, 0.2, 0.1] * 20,
                        "audio": [0.3, 0.3, 0.3, 0.3, 0.3] * 20
                    },
                    "attention_config": {"attention_type": "cross_modal", "num_heads": 8}
                }
            )
            gpu_time = time.time() - start_time
            
            if gpu_response.status_code == 200:
                gpu_result = gpu_response.json()
                speedup = gpu_result.get("speedup", 0)
                if speedup > 0:
                    attention_speedups.append(speedup)
        
        if attention_speedups:
            avg_speedup = statistics.mean(attention_speedups)
            target = PERFORMANCE_TARGETS["gpu_multimodal"]["cross_modal_attention"]
            results["cross_modal_attention"] = {
                "avg_speedup": avg_speedup,
                "target_speedup": target["min_speedup"],
                "meets_target": avg_speedup >= target["min_speedup"],
                "samples": len(attention_speedups)
            }
            status = "✅" if results["cross_modal_attention"]["meets_target"] else "❌"
            print(f"    {status} Cross-modal attention: {avg_speedup:.1f}x speedup (target: ≥{target['min_speedup']}x)")
        
        # Test multi-modal fusion
        print("  🔀 Testing multi-modal fusion...")
        fusion_speedups = []
        
        for i in range(5):
            start_time = time.time()
            fusion_response = await self.client.post(
                f"{SERVICES['gpu_multimodal']}/fusion",
                json={
                    "modality_data": {
                        "text_features": [0.1, 0.2, 0.3] * 50,
                        "image_features": [0.4, 0.5, 0.6] * 50,
                        "audio_features": [0.7, 0.8, 0.9] * 50
                    },
                    "fusion_config": {"fusion_type": "attention_based", "output_dim": 256}
                }
            )
            fusion_time = time.time() - start_time
            
            if fusion_response.status_code == 200:
                fusion_result = fusion_response.json()
                speedup = fusion_result.get("speedup", 0)
                if speedup > 0:
                    fusion_speedups.append(speedup)
        
        if fusion_speedups:
            avg_speedup = statistics.mean(fusion_speedups)
            target = PERFORMANCE_TARGETS["gpu_multimodal"]["multi_modal_fusion"]
            results["multi_modal_fusion"] = {
                "avg_speedup": avg_speedup,
                "target_speedup": target["min_speedup"],
                "meets_target": avg_speedup >= target["min_speedup"],
                "samples": len(fusion_speedups)
            }
            status = "✅" if results["multi_modal_fusion"]["meets_target"] else "❌"
            print(f"    {status} Multi-modal fusion: {avg_speedup:.1f}x speedup (target: ≥{target['min_speedup']}x)")
        
        return results
    
    async def benchmark_marketplace_performance(self) -> Dict[str, Any]:
        """Benchmark marketplace transaction performance"""
        print("\n🏪 Benchmarking Marketplace Performance...")
        
        results = {}
        
        # Test transaction processing
        print("  💸 Testing transaction processing...")
        transaction_times = []
        
        for i in range(10):
            start_time = time.time()
            response = await self.client.post(
                f"{SERVICES['marketplace_enhanced']}/v1/trading/execute",
                json={
                    "bid_id": f"benchmark-bid-{i}",
                    "buyer_address": "0x1234567890123456789012345678901234567890",
                    "payment_method": "crypto",
                    "amount": 0.1
                }
            )
            end_time = time.time()
            
            # Even if it fails, measure response time
            transaction_times.append(end_time - start_time)
        
        if transaction_times:
            avg_time = statistics.mean(transaction_times)
            target = PERFORMANCE_TARGETS["marketplace_enhanced"]["transaction_processing"]
            results["transaction_processing"] = {
                "avg_time": avg_time,
                "target_time": target["max_time"],
                "meets_target": avg_time <= target["max_time"],
                "samples": len(transaction_times)
            }
            status = "✅" if results["transaction_processing"]["meets_target"] else "❌"
            print(f"    {status} Transaction processing: {avg_time:.3f}s (target: ≤{target['max_time']}s)")
        
        # Test royalty calculation
        print("  💰 Testing royalty calculation...")
        royalty_times = []
        
        for i in range(20):  # More samples for faster operation
            start_time = time.time()
            response = await self.client.post(
                f"{SERVICES['marketplace_enhanced']}/v1/analytics/royalties",
                json={
                    "model_id": f"benchmark-model-{i}",
                    "transaction_amount": 0.5,
                    "royalty_config": {
                        "creator_percentage": 15.0,
                        "platform_percentage": 5.0
                    }
                }
            )
            end_time = time.time()
            
            royalty_times.append(end_time - start_time)
        
        if royalty_times:
            avg_time = statistics.mean(royalty_times)
            target = PERFORMANCE_TARGETS["marketplace_enhanced"]["royalty_calculation"]
            results["royalty_calculation"] = {
                "avg_time": avg_time,
                "target_time": target["max_time"],
                "meets_target": avg_time <= target["max_time"],
                "samples": len(royalty_times)
            }
            status = "✅" if results["royalty_calculation"]["meets_target"] else "❌"
            print(f"    {status} Royalty calculation: {avg_time:.3f}s (target: ≤{target['max_time']}s)")
        
        return results
    
    async def benchmark_concurrent_performance(self) -> Dict[str, Any]:
        """Benchmark concurrent request handling"""
        print("\n⚡ Benchmarking Concurrent Performance...")
        
        results = {}
        
        # Test concurrent requests to multi-modal service
        print("  🔄 Testing concurrent multi-modal requests...")
        
        async def make_request(request_id: int) -> Tuple[float, bool]:
            """Make a single request and return (time, success)"""
            start_time = time.time()
            try:
                response = await self.client.post(
                    f"{SERVICES['multimodal']}/process",
                    json={
                        "agent_id": f"concurrent-test-{request_id}",
                        "inputs": {"text": f"Concurrent test request {request_id}"},
                        "processing_mode": "text_analysis"
                    }
                )
                end_time = time.time()
                return (end_time - start_time, response.status_code == 200)
            except Exception:
                end_time = time.time()
                return (end_time - start_time, False)
        
        # Test with different concurrency levels
        concurrency_levels = [1, 5, 10, 20]
        
        for concurrency in concurrency_levels:
            print(f"    Testing {concurrency} concurrent requests...")
            
            start_time = time.time()
            tasks = [make_request(i) for i in range(concurrency)]
            request_results = await asyncio.gather(*tasks)
            total_time = time.time() - start_time
            
            # Analyze results
            times = [r[0] for r in request_results]
            successes = [r[1] for r in request_results]
            success_rate = sum(successes) / len(successes)
            avg_response_time = statistics.mean(times)
            max_response_time = max(times)
            
            results[f"concurrent_{concurrency}"] = {
                "concurrency": concurrency,
                "total_time": total_time,
                "success_rate": success_rate,
                "avg_response_time": avg_response_time,
                "max_response_time": max_response_time,
                "requests_per_second": concurrency / total_time
            }
            
            status = "✅" if success_rate >= 0.9 else "❌"
            print(f"      {status} {concurrency} concurrent: {success_rate:.1%} success, {avg_response_time:.3f}s avg")
        
        return results
    
    async def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all performance benchmarks"""
        print("🎯 Starting Performance Benchmark Suite")
        print("="*60)
        
        benchmark_start = time.time()
        all_results = {}
        
        # Run individual benchmarks
        try:
            all_results["multimodal"] = await self.benchmark_multimodal_performance()
        except Exception as e:
            all_results["multimodal"] = {"error": str(e)}
        
        try:
            all_results["gpu_multimodal"] = await self.benchmark_gpu_performance()
        except Exception as e:
            all_results["gpu_multimodal"] = {"error": str(e)}
        
        try:
            all_results["marketplace"] = await self.benchmark_marketplace_performance()
        except Exception as e:
            all_results["marketplace"] = {"error": str(e)}
        
        try:
            all_results["concurrent"] = await self.benchmark_concurrent_performance()
        except Exception as e:
            all_results["concurrent"] = {"error": str(e)}
        
        total_duration = time.time() - benchmark_start
        
        # Calculate overall performance score
        total_tests = 0
        passed_tests = 0
        
        for service_results in all_results.values():
            if isinstance(service_results, dict) and "error" not in service_results:
                for test_result in service_results.values():
                    if isinstance(test_result, dict) and "meets_target" in test_result:
                        total_tests += 1
                        if test_result["meets_target"]:
                            passed_tests += 1
        
        overall_score = passed_tests / total_tests if total_tests > 0 else 0
        
        print("\n" + "="*60)
        print("  PERFORMANCE BENCHMARK SUMMARY")
        print("="*60)
        print(f"Total Duration: {total_duration:.1f}s")
        print(f"Tests Passed: {passed_tests}/{total_tests}")
        print(f"Performance Score: {overall_score:.1%}")
        print(f"Overall Status: {'✅ EXCELLENT' if overall_score >= 0.9 else '⚠️  GOOD' if overall_score >= 0.7 else '❌ NEEDS IMPROVEMENT'}")
        
        return {
            "overall_score": overall_score,
            "total_duration": total_duration,
            "tests_passed": passed_tests,
            "total_tests": total_tests,
            "system_metrics": self.system_metrics,
            "results": all_results
        }


# Pytest test functions
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.performance
async def test_multimodal_performance_benchmarks():
    """Test multi-modal service performance against targets"""
    tester = PerformanceBenchmarkTester()
    
    try:
        if not await tester.setup_test_environment():
            pytest.skip("Services not available for performance testing")
        
        results = await tester.benchmark_multimodal_performance()
        
        # Verify key performance targets
        if "text_processing" in results:
            assert results["text_processing"]["meets_target"], f"Text processing too slow: {results['text_processing']['avg_time']:.3f}s"
        
        if "image_processing" in results:
            assert results["image_processing"]["meets_target"], f"Image processing too slow: {results['image_processing']['avg_time']:.3f}s"
        
        print(f"✅ Multi-modal performance benchmarks passed")
        
    finally:
        await tester.cleanup_test_environment()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.performance
async def test_gpu_acceleration_benchmarks():
    """Test GPU acceleration performance against targets"""
    tester = PerformanceBenchmarkTester()
    
    try:
        if not await tester.setup_test_environment():
            pytest.skip("Services not available for performance testing")
        
        results = await tester.benchmark_gpu_performance()
        
        # Skip if GPU not available
        if "error" in results:
            pytest.skip("GPU not available for testing")
        
        # Verify GPU performance targets
        if "cross_modal_attention" in results:
            assert results["cross_modal_attention"]["meets_target"], f"Cross-modal attention speedup too low: {results['cross_modal_attention']['avg_speedup']:.1f}x"
        
        if "multi_modal_fusion" in results:
            assert results["multi_modal_fusion"]["meets_target"], f"Multi-modal fusion speedup too low: {results['multi_modal_fusion']['avg_speedup']:.1f}x"
        
        print(f"✅ GPU acceleration benchmarks passed")
        
    finally:
        await tester.cleanup_test_environment()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.performance
async def test_marketplace_performance_benchmarks():
    """Test marketplace service performance against targets"""
    tester = PerformanceBenchmarkTester()
    
    try:
        if not await tester.setup_test_environment():
            pytest.skip("Services not available for performance testing")
        
        results = await tester.benchmark_marketplace_performance()
        
        # Verify marketplace performance targets
        if "transaction_processing" in results:
            assert results["transaction_processing"]["meets_target"], f"Transaction processing too slow: {results['transaction_processing']['avg_time']:.3f}s"
        
        if "royalty_calculation" in results:
            assert results["royalty_calculation"]["meets_target"], f"Royalty calculation too slow: {results['royalty_calculation']['avg_time']:.3f}s"
        
        print(f"✅ Marketplace performance benchmarks passed")
        
    finally:
        await tester.cleanup_test_environment()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.performance
async def test_concurrent_performance_benchmarks():
    """Test concurrent request handling performance"""
    tester = PerformanceBenchmarkTester()
    
    try:
        if not await tester.setup_test_environment():
            pytest.skip("Services not available for performance testing")
        
        results = await tester.benchmark_concurrent_performance()
        
        # Verify concurrent performance
        for concurrency_level, result in results.items():
            if isinstance(result, dict):
                assert result["success_rate"] >= 0.8, f"Success rate too low for {concurrency_level}: {result['success_rate']:.1%}"
        
        print(f"✅ Concurrent performance benchmarks passed")
        
    finally:
        await tester.cleanup_test_environment()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.performance
async def test_complete_performance_suite():
    """Run complete performance benchmark suite"""
    tester = PerformanceBenchmarkTester()
    
    try:
        if not await tester.setup_test_environment():
            pytest.skip("Services not available for performance testing")
        
        results = await tester.run_all_benchmarks()
        
        # Verify overall performance
        assert results["overall_score"] >= 0.6, f"Overall performance score too low: {results['overall_score']:.1%}"
        assert results["total_duration"] < 300.0, "Performance suite took too long"
        
        print(f"✅ Complete performance suite: {results['overall_score']:.1%} score")
        
    finally:
        await tester.cleanup_test_environment()


if __name__ == "__main__":
    # Run benchmarks manually
    async def main():
        tester = PerformanceBenchmarkTester()
        
        try:
            if await tester.setup_test_environment():
                results = await tester.run_all_benchmarks()
                
                print(f"\n🎯 Performance Benchmark Complete:")
                print(f"Score: {results['overall_score']:.1%}")
                print(f"Duration: {results['total_duration']:.1f}s")
                print(f"Tests: {results['tests_passed']}/{results['total_tests']}")
                
        finally:
            await tester.cleanup_test_environment()
    
    asyncio.run(main())
