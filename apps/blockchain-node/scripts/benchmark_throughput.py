#!/usr/bin/env python3
"""
Blockchain Node Throughput Benchmark

This script simulates sustained load on the blockchain node to measure:
- Transactions per second (TPS)
- Latency percentiles (p50, p95, p99)
- CPU and memory usage
- Queue depth and saturation points

Usage:
    python benchmark_throughput.py --concurrent-clients 100 --duration 60 --target-url http://localhost:8080
"""

import asyncio
import aiohttp
import time
import statistics
import psutil
import argparse
import json
from typing import List, Dict, Any
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Results from a benchmark run"""
    total_transactions: int
    duration: float
    tps: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    cpu_usage: float
    memory_usage: float
    errors: int


class BlockchainBenchmark:
    """Benchmark client for blockchain node"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def submit_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a single transaction"""
        start_time = time.time()
        try:
            async with self.session.post(
                f"{self.base_url}/v1/transactions",
                json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    latency = (time.time() - start_time) * 1000  # ms
                    return {"success": True, "latency": latency, "tx_id": result.get("tx_id")}
                else:
                    return {"success": False, "error": f"HTTP {response.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_block_height(self) -> int:
        """Get current block height"""
        try:
            async with self.session.get(f"{self.base_url}/v1/blocks/head") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("height", 0)
        except Exception:
            pass
        return 0


def generate_test_transaction(i: int) -> Dict[str, Any]:
    """Generate a test transaction"""
    return {
        "from": f"0xtest_sender_{i % 100:040x}",
        "to": f"0xtest_receiver_{i % 50:040x}",
        "value": str((i + 1) * 1000),
        "nonce": i,
        "data": f"0x{hash(i) % 1000000:06x}",
        "gas_limit": 21000,
        "gas_price": "1000000000"  # 1 gwei
    }


async def worker_task(
    benchmark: BlockchainBenchmark,
    worker_id: int,
    transactions_per_worker: int,
    results: List[Dict[str, Any]]
) -> None:
    """Worker task that submits transactions"""
    logger.info(f"Worker {worker_id} starting")
    
    for i in range(transactions_per_worker):
        tx = generate_test_transaction(worker_id * transactions_per_worker + i)
        result = await benchmark.submit_transaction(tx)
        results.append(result)
        
        if not result["success"]:
            logger.warning(f"Worker {worker_id} transaction failed: {result.get('error', 'unknown')}")
    
    logger.info(f"Worker {worker_id} completed")


async def run_benchmark(
    base_url: str,
    concurrent_clients: int,
    duration: int,
    target_tps: int = None
) -> BenchmarkResult:
    """Run the benchmark"""
    logger.info(f"Starting benchmark: {concurrent_clients} concurrent clients for {duration}s")
    
    # Start resource monitoring
    process = psutil.Process()
    cpu_samples = []
    memory_samples = []
    
    async def monitor_resources():
        while True:
            cpu_samples.append(process.cpu_percent())
            memory_samples.append(process.memory_info().rss / 1024 / 1024)  # MB
            await asyncio.sleep(1)
    
    # Calculate transactions needed
    if target_tps:
        total_transactions = target_tps * duration
    else:
        total_transactions = concurrent_clients * 100  # Default: 100 tx per client
    
    transactions_per_worker = total_transactions // concurrent_clients
    results = []
    
    async with BlockchainBenchmark(base_url) as benchmark:
        # Start resource monitor
        monitor_task = asyncio.create_task(monitor_resources())
        
        # Record start block height
        start_height = await benchmark.get_block_height()
        
        # Start benchmark
        start_time = time.time()
        
        # Create worker tasks
        tasks = [
            worker_task(benchmark, i, transactions_per_worker, results)
            for i in range(concurrent_clients)
        ]
        
        # Wait for all tasks to complete or timeout
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=duration)
        except asyncio.TimeoutError:
            logger.warning("Benchmark timed out")
            for task in tasks:
                task.cancel()
        
        end_time = time.time()
        actual_duration = end_time - start_time
        
        # Stop resource monitor
        monitor_task.cancel()
        
        # Get final block height
        end_height = await benchmark.get_block_height()
        
        # Calculate metrics
        successful_tx = [r for r in results if r["success"]]
        latencies = [r["latency"] for r in successful_tx if "latency" in r]
        
        if latencies:
            latency_p50 = statistics.median(latencies)
            latency_p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
            latency_p99 = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
        else:
            latency_p50 = latency_p95 = latency_p99 = 0
        
        tps = len(successful_tx) / actual_duration if actual_duration > 0 else 0
        avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0
        avg_memory = statistics.mean(memory_samples) if memory_samples else 0
        errors = len(results) - len(successful_tx)
        
        logger.info(f"Benchmark completed:")
        logger.info(f"  Duration: {actual_duration:.2f}s")
        logger.info(f"  Transactions: {len(successful_tx)} successful, {errors} failed")
        logger.info(f"  TPS: {tps:.2f}")
        logger.info(f"  Latency p50/p95/p99: {latency_p50:.2f}/{latency_p95:.2f}/{latency_p99:.2f}ms")
        logger.info(f"  CPU Usage: {avg_cpu:.1f}%")
        logger.info(f"  Memory Usage: {avg_memory:.1f}MB")
        logger.info(f"  Blocks processed: {end_height - start_height}")
        
        return BenchmarkResult(
            total_transactions=len(successful_tx),
            duration=actual_duration,
            tps=tps,
            latency_p50=latency_p50,
            latency_p95=latency_p95,
            latency_p99=latency_p99,
            cpu_usage=avg_cpu,
            memory_usage=avg_memory,
            errors=errors
        )


async def main():
    parser = argparse.ArgumentParser(description="Blockchain Node Throughput Benchmark")
    parser.add_argument("--target-url", default="http://localhost:8080", 
                       help="Blockchain node RPC URL")
    parser.add_argument("--concurrent-clients", type=int, default=50,
                       help="Number of concurrent client connections")
    parser.add_argument("--duration", type=int, default=60,
                       help="Benchmark duration in seconds")
    parser.add_argument("--target-tps", type=int,
                       help="Target TPS to achieve (calculates transaction count)")
    parser.add_argument("--output", help="Output results to JSON file")
    
    args = parser.parse_args()
    
    # Run benchmark
    result = await run_benchmark(
        base_url=args.target_url,
        concurrent_clients=args.concurrent_clients,
        duration=args.duration,
        target_tps=args.target_tps
    )
    
    # Output results
    if args.output:
        with open(args.output, "w") as f:
            json.dump({
                "total_transactions": result.total_transactions,
                "duration": result.duration,
                "tps": result.tps,
                "latency_p50": result.latency_p50,
                "latency_p95": result.latency_p95,
                "latency_p99": result.latency_p99,
                "cpu_usage": result.cpu_usage,
                "memory_usage": result.memory_usage,
                "errors": result.errors
            }, f, indent=2)
        logger.info(f"Results saved to {args.output}")
    
    # Provide scaling recommendations
    logger.info("\n=== Scaling Recommendations ===")
    if result.tps < 100:
        logger.info("• Low TPS detected. Consider optimizing transaction processing")
    if result.latency_p95 > 1000:
        logger.info("• High latency detected. Consider increasing resources or optimizing database queries")
    if result.cpu_usage > 80:
        logger.info("• High CPU usage. Horizontal scaling recommended")
    if result.memory_usage > 1024:
        logger.info("• High memory usage. Monitor for memory leaks")
    
    logger.info(f"\nRecommended minimum resources for current load:")
    logger.info(f"• CPU: {result.cpu_usage * 1.5:.0f}% (with headroom)")
    logger.info(f"• Memory: {result.memory_usage * 1.5:.0f}MB (with headroom)")
    logger.info(f"• Horizontal scaling threshold: ~{result.tps * 0.7:.0f} TPS per node")


if __name__ == "__main__":
    asyncio.run(main())
