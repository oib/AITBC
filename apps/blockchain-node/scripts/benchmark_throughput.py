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

import argparse
import asyncio
import json
import logging
import statistics
import time
from dataclasses import dataclass
from typing import Any

import aiohttp
import psutil

from aitbc.logging import get_logger

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = get_logger(__name__)


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
        self.base_url = base_url.rstrip("/")
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def submit_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a single transaction"""
        start_time = time.time()
        try:
            async with self.session.post(f"{self.base_url}/v1/transactions", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    latency = (time.time() - start_time) * 1000
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


def generate_test_transaction(i: int) -> dict[str, Any]:
    """Generate a test transaction"""
    return {
        "from": f"0xtest_sender_{i % 100:040x}",
        "to": f"0xtest_receiver_{i % 50:040x}",
        "value": str((i + 1) * 1000),
        "nonce": i,
        "data": f"0x{hash(i) % 1000000:06x}",
        "gas_limit": 21000,
        "gas_price": "1000000000",
    }


async def worker_task(
    benchmark: BlockchainBenchmark, worker_id: int, transactions_per_worker: int, results: list[dict[str, Any]]
) -> None:
    """Worker task that submits transactions"""
    logger.info("Worker %s starting", worker_id)
    for i in range(transactions_per_worker):
        tx = generate_test_transaction(worker_id * transactions_per_worker + i)
        result = await benchmark.submit_transaction(tx)
        results.append(result)
        if not result["success"]:
            logger.warning("Worker %s transaction failed: %s", worker_id, result.get("error", "unknown"))
    logger.info("Worker %s completed", worker_id)


async def run_benchmark(base_url: str, concurrent_clients: int, duration: int, target_tps: int = None) -> BenchmarkResult:
    """Run the benchmark"""
    logger.info("Starting benchmark: %s concurrent clients for %ss", concurrent_clients, duration)
    process = psutil.Process()
    cpu_samples = []
    memory_samples = []

    async def monitor_resources():
        while True:
            cpu_samples.append(process.cpu_percent())
            memory_samples.append(process.memory_info().rss / 1024 / 1024)
            await asyncio.sleep(1)

    if target_tps:
        total_transactions = target_tps * duration
    else:
        total_transactions = concurrent_clients * 100
    transactions_per_worker = total_transactions // concurrent_clients
    results = []
    async with BlockchainBenchmark(base_url) as benchmark:
        monitor_task = asyncio.create_task(monitor_resources())
        start_height = await benchmark.get_block_height()
        start_time = time.time()
        tasks = [worker_task(benchmark, i, transactions_per_worker, results) for i in range(concurrent_clients)]
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=duration)
        except TimeoutError:
            logger.warning("Benchmark timed out")
            for task in tasks:
                task.cancel()
        end_time = time.time()
        actual_duration = end_time - start_time
        monitor_task.cancel()
        end_height = await benchmark.get_block_height()
        successful_tx = [r for r in results if r["success"]]
        latencies = [r["latency"] for r in successful_tx if "latency" in r]
        if latencies:
            latency_p50 = statistics.median(latencies)
            latency_p95 = statistics.quantiles(latencies, n=20)[18]
            latency_p99 = statistics.quantiles(latencies, n=100)[98]
        else:
            latency_p50 = latency_p95 = latency_p99 = 0
        tps = len(successful_tx) / actual_duration if actual_duration > 0 else 0
        avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0
        avg_memory = statistics.mean(memory_samples) if memory_samples else 0
        errors = len(results) - len(successful_tx)
        logger.info("Benchmark completed:")
        logger.info("  Duration: %ss", actual_duration)
        logger.info("  Transactions: %s successful, %s failed", len(successful_tx), errors)
        logger.info("  TPS: %s", tps)
        logger.info("  Latency p50/p95/p99: %s/%s/%sms", latency_p50, latency_p95, latency_p99)
        logger.info("  CPU Usage: %s%", avg_cpu)
        logger.info("  Memory Usage: %sMB", avg_memory)
        logger.info("  Blocks processed: %s", end_height - start_height)
        return BenchmarkResult(
            total_transactions=len(successful_tx),
            duration=actual_duration,
            tps=tps,
            latency_p50=latency_p50,
            latency_p95=latency_p95,
            latency_p99=latency_p99,
            cpu_usage=avg_cpu,
            memory_usage=avg_memory,
            errors=errors,
        )


async def main():
    parser = argparse.ArgumentParser(description="Blockchain Node Throughput Benchmark")
    parser.add_argument("--target-url", default="http://localhost:8080", help="Blockchain node RPC URL")
    parser.add_argument("--concurrent-clients", type=int, default=50, help="Number of concurrent client connections")
    parser.add_argument("--duration", type=int, default=60, help="Benchmark duration in seconds")
    parser.add_argument("--target-tps", type=int, help="Target TPS to achieve (calculates transaction count)")
    parser.add_argument("--output", help="Output results to JSON file")
    args = parser.parse_args()
    result = await run_benchmark(
        base_url=args.target_url,
        concurrent_clients=args.concurrent_clients,
        duration=args.duration,
        target_tps=args.target_tps,
    )
    if args.output:
        with open(args.output, "w") as f:
            json.dump(
                {
                    "total_transactions": result.total_transactions,
                    "duration": result.duration,
                    "tps": result.tps,
                    "latency_p50": result.latency_p50,
                    "latency_p95": result.latency_p95,
                    "latency_p99": result.latency_p99,
                    "cpu_usage": result.cpu_usage,
                    "memory_usage": result.memory_usage,
                    "errors": result.errors,
                },
                f,
                indent=2,
            )
        logger.info("Results saved to %s", args.output)
    logger.info("\n=== Scaling Recommendations ===")
    if result.tps < 100:
        logger.info("• Low TPS detected. Consider optimizing transaction processing")
    if result.latency_p95 > 1000:
        logger.info("• High latency detected. Consider increasing resources or optimizing database queries")
    if result.cpu_usage > 80:
        logger.info("• High CPU usage. Horizontal scaling recommended")
    if result.memory_usage > 1024:
        logger.info("• High memory usage. Monitor for memory leaks")
    logger.info("\nRecommended minimum resources for current load:")
    logger.info("• CPU: %s% (with headroom)", result.cpu_usage * 1.5)
    logger.info("• Memory: %sMB (with headroom)", result.memory_usage * 1.5)
    logger.info("• Horizontal scaling threshold: ~%s TPS per node", result.tps * 0.7)


if __name__ == "__main__":
    asyncio.run(main())
