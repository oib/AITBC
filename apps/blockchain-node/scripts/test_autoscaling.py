#!/usr/bin/env python3
"""
Autoscaling Validation Script

This script generates synthetic traffic to test and validate HPA behavior.
It monitors pod counts and metrics while generating load to ensure autoscaling works as expected.

Usage:
    python test_autoscaling.py --service coordinator --namespace default --target-url http://localhost:8011 --duration 300
"""

import asyncio
import aiohttp
import time
import argparse
import logging
import json
from typing import List, Dict, Any
from datetime import datetime
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AutoscalingTest:
    """Test suite for validating autoscaling behavior"""
    
    def __init__(self, service_name: str, namespace: str, target_url: str):
        self.service_name = service_name
        self.namespace = namespace
        self.target_url = target_url
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_pod_count(self) -> int:
        """Get current number of pods for the service"""
        cmd = [
            "kubectl", "get", "pods",
            "-n", self.namespace,
            "-l", f"app.kubernetes.io/name={self.service_name}",
            "-o", "jsonpath='{.items[*].status.phase}'"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            # Count Running pods
            phases = result.stdout.strip().strip("'").split()
            return len([p for p in phases if p == "Running"])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get pod count: {e}")
            return 0
    
    async def get_hpa_status(self) -> Dict[str, Any]:
        """Get current HPA status"""
        cmd = [
            "kubectl", "get", "hpa",
            "-n", self.namespace,
            f"{self.service_name}",
            "-o", "json"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            return {
                "min_replicas": data["spec"]["minReplicas"],
                "max_replicas": data["spec"]["maxReplicas"],
                "current_replicas": data["status"]["currentReplicas"],
                "desired_replicas": data["status"]["desiredReplicas"],
                "current_cpu": data["status"].get("currentCPUUtilizationPercentage"),
                "target_cpu": None
            }
            
            # Extract target CPU from metrics
            for metric in data["spec"]["metrics"]:
                if metric["type"] == "Resource" and metric["resource"]["name"] == "cpu":
                    self.target_cpu = metric["resource"]["target"]["averageUtilization"]
                    break
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get HPA status: {e}")
            return {}
    
    async def generate_load(self, duration: int, concurrent_requests: int = 50):
        """Generate sustained load on the service"""
        logger.info(f"Generating load for {duration}s with {concurrent_requests} concurrent requests")
        
        async def make_request():
            try:
                if self.service_name == "coordinator":
                    # Test marketplace endpoints
                    endpoints = [
                        "/v1/marketplace/offers",
                        "/v1/marketplace/stats"
                    ]
                    endpoint = endpoints[hash(time.time()) % len(endpoints)]
                    async with self.session.get(f"{self.target_url}{endpoint}") as response:
                        return response.status == 200
                elif self.service_name == "blockchain-node":
                    # Test blockchain endpoints
                    payload = {
                        "from": "0xtest_sender",
                        "to": "0xtest_receiver",
                        "value": "1000",
                        "nonce": int(time.time()),
                        "data": "0x",
                        "gas_limit": 21000,
                        "gas_price": "1000000000"
                    }
                    async with self.session.post(f"{self.target_url}/v1/transactions", json=payload) as response:
                        return response.status == 200
                else:
                    # Generic health check
                    async with self.session.get(f"{self.target_url}/v1/health") as response:
                        return response.status == 200
            except Exception as e:
                logger.debug(f"Request failed: {e}")
                return False
        
        # Generate sustained load
        start_time = time.time()
        tasks = []
        
        while time.time() - start_time < duration:
            # Create batch of concurrent requests
            batch = [make_request() for _ in range(concurrent_requests)]
            tasks.extend(batch)
            
            # Wait for batch to complete
            await asyncio.gather(*batch, return_exceptions=True)
            
            # Brief pause between batches
            await asyncio.sleep(0.1)
        
        logger.info(f"Load generation completed")
    
    async def monitor_scaling(self, duration: int, interval: int = 10):
        """Monitor pod scaling during load test"""
        logger.info(f"Monitoring scaling for {duration}s")
        
        results = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            timestamp = datetime.now().isoformat()
            pod_count = await self.get_pod_count()
            hpa_status = await self.get_hpa_status()
            
            result = {
                "timestamp": timestamp,
                "pod_count": pod_count,
                "hpa_status": hpa_status
            }
            
            results.append(result)
            logger.info(f"[{timestamp}] Pods: {pod_count}, HPA: {hpa_status}")
            
            await asyncio.sleep(interval)
        
        return results
    
    async def run_test(self, load_duration: int = 300, monitor_duration: int = 400):
        """Run complete autoscaling test"""
        logger.info(f"Starting autoscaling test for {self.service_name}")
        
        # Record initial state
        initial_pods = await self.get_pod_count()
        initial_hpa = await self.get_hpa_status()
        
        logger.info(f"Initial state - Pods: {initial_pods}, HPA: {initial_hpa}")
        
        # Start monitoring in background
        monitor_task = asyncio.create_task(
            self.monitor_scaling(monitor_duration)
        )
        
        # Wait a bit to establish baseline
        await asyncio.sleep(30)
        
        # Generate load
        await self.generate_load(load_duration)
        
        # Wait for scaling to stabilize
        await asyncio.sleep(60)
        
        # Get monitoring results
        monitoring_results = await monitor_task
        
        # Analyze results
        max_pods = max(r["pod_count"] for r in monitoring_results)
        min_pods = min(r["pod_count"] for r in monitoring_results)
        scaled_up = max_pods > initial_pods
        
        logger.info("\n=== Test Results ===")
        logger.info(f"Initial pods: {initial_pods}")
        logger.info(f"Min pods during test: {min_pods}")
        logger.info(f"Max pods during test: {max_pods}")
        logger.info(f"Scaling occurred: {scaled_up}")
        
        if scaled_up:
            logger.info("✅ Autoscaling test PASSED - Service scaled up under load")
        else:
            logger.warning("⚠️ Autoscaling test FAILED - Service did not scale up")
            logger.warning("Check:")
            logger.warning("  - HPA configuration")
            logger.warning("  - Metrics server is running")
            logger.warning("  - Resource requests/limits are set")
            logger.warning("  - Load was sufficient to trigger scaling")
        
        # Save results
        results_file = f"autoscaling_test_{self.service_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, "w") as f:
            json.dump({
                "service": self.service_name,
                "namespace": self.namespace,
                "initial_pods": initial_pods,
                "max_pods": max_pods,
                "min_pods": min_pods,
                "scaled_up": scaled_up,
                "monitoring_data": monitoring_results
            }, f, indent=2)
        
        logger.info(f"Detailed results saved to: {results_file}")
        
        return scaled_up


async def main():
    parser = argparse.ArgumentParser(description="Autoscaling Validation Test")
    parser.add_argument("--service", required=True,
                       choices=["coordinator", "blockchain-node", "wallet-daemon"],
                       help="Service to test")
    parser.add_argument("--namespace", default="default",
                       help="Kubernetes namespace")
    parser.add_argument("--target-url", required=True,
                       help="Service URL to generate load against")
    parser.add_argument("--load-duration", type=int, default=300,
                       help="Duration of load generation in seconds")
    parser.add_argument("--monitor-duration", type=int, default=400,
                       help="Total monitoring duration in seconds")
    parser.add_argument("--local-mode", action="store_true",
                       help="Run in local mode without Kubernetes (load test only)")
    
    args = parser.parse_args()
    
    if not args.local_mode:
        # Verify kubectl is available
        try:
            subprocess.run(["kubectl", "version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("kubectl is not available or not configured")
            logger.info("Use --local-mode to run load test without Kubernetes monitoring")
            sys.exit(1)
    
    # Run test
    async with AutoscalingTest(args.service, args.namespace, args.target_url) as test:
        if args.local_mode:
            # Local mode: just test load generation
            logger.info(f"Running load test for {args.service} in local mode")
            await test.generate_load(args.load_duration)
            logger.info("Load test completed successfully")
            success = True
        else:
            # Full autoscaling test
            success = await test.run_test(args.load_duration, args.monitor_duration)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
