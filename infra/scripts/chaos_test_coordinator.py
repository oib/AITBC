#!/usr/bin/env python3
"""
Chaos Testing Script - Coordinator API Outage
Tests system resilience when coordinator API becomes unavailable
"""

import asyncio
import aiohttp
import argparse
import json
import time
import logging
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ChaosTestCoordinator:
    """Chaos testing for coordinator API outage scenarios"""
    
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self.session = None
        self.metrics = {
            "test_start": None,
            "test_end": None,
            "outage_start": None,
            "outage_end": None,
            "recovery_time": None,
            "mttr": None,
            "error_count": 0,
            "success_count": 0,
            "scenario": "coordinator_outage"
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def get_coordinator_pods(self) -> List[str]:
        """Get list of coordinator pods"""
        cmd = [
            "kubectl", "get", "pods",
            "-n", self.namespace,
            "-l", "app.kubernetes.io/name=coordinator",
            "-o", "jsonpath={.items[*].metadata.name}"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            pods = result.stdout.strip().split()
            return pods
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get coordinator pods: {e}")
            return []
    
    def delete_coordinator_pods(self) -> bool:
        """Delete all coordinator pods to simulate outage"""
        try:
            cmd = [
                "kubectl", "delete", "pods",
                "-n", self.namespace,
                "-l", "app.kubernetes.io/name=coordinator",
                "--force", "--grace-period=0"
            ]
            subprocess.run(cmd, check=True)
            logger.info("Coordinator pods deleted successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to delete coordinator pods: {e}")
            return False
    
    async def wait_for_pods_termination(self, timeout: int = 60) -> bool:
        """Wait for all coordinator pods to terminate"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            pods = self.get_coordinator_pods()
            if not pods:
                logger.info("All coordinator pods terminated")
                return True
            await asyncio.sleep(2)
        
        logger.error("Timeout waiting for pods to terminate")
        return False
    
    async def wait_for_recovery(self, timeout: int = 300) -> bool:
        """Wait for coordinator service to recover"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check if pods are running
                pods = self.get_coordinator_pods()
                if not pods:
                    await asyncio.sleep(5)
                    continue
                
                # Check if at least one pod is ready
                ready_cmd = [
                    "kubectl", "get", "pods",
                    "-n", self.namespace,
                    "-l", "app.kubernetes.io/name=coordinator",
                    "-o", "jsonpath={.items[?(@.status.phase=='Running')].metadata.name}"
                ]
                result = subprocess.run(ready_cmd, capture_output=True, text=True)
                if result.stdout.strip():
                    # Test API health
                    if self.test_health_endpoint():
                        recovery_time = time.time() - start_time
                        self.metrics["recovery_time"] = recovery_time
                        logger.info(f"Service recovered in {recovery_time:.2f} seconds")
                        return True
                
            except Exception as e:
                logger.debug(f"Recovery check failed: {e}")
            
            await asyncio.sleep(5)
        
        logger.error("Service did not recover within timeout")
        return False
    
    def test_health_endpoint(self) -> bool:
        """Test if coordinator health endpoint is responding"""
        try:
            # Get service URL
            cmd = [
                "kubectl", "get", "svc", "coordinator",
                "-n", self.namespace,
                "-o", "jsonpath={.spec.clusterIP}:{.spec.ports[0].port}"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            service_url = f"http://{result.stdout.strip()}/v1/health"
            
            # Test health endpoint
            response = subprocess.run(
                ["curl", "-s", "--max-time", "5", service_url],
                capture_output=True, text=True
            )
            
            return response.returncode == 0 and "ok" in response.stdout
        except Exception:
            return False
    
    async def generate_load(self, duration: int, concurrent: int = 10):
        """Generate synthetic load on coordinator API"""
        logger.info(f"Generating load for {duration} seconds with {concurrent} concurrent requests")
        
        # Get service URL
        cmd = [
            "kubectl", "get", "svc", "coordinator",
            "-n", self.namespace,
            "-o", "jsonpath={.spec.clusterIP}:{.spec.ports[0].port}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        base_url = f"http://{result.stdout.strip()}"
        
        start_time = time.time()
        tasks = []
        
        async def make_request():
            try:
                async with self.session.get(f"{base_url}/v1/marketplace/stats") as response:
                    if response.status == 200:
                        self.metrics["success_count"] += 1
                    else:
                        self.metrics["error_count"] += 1
            except Exception:
                self.metrics["error_count"] += 1
        
        while time.time() - start_time < duration:
            # Create batch of requests
            batch = [make_request() for _ in range(concurrent)]
            tasks.extend(batch)
            
            # Wait for batch to complete
            await asyncio.gather(*batch, return_exceptions=True)
            
            # Brief pause
            await asyncio.sleep(1)
        
        logger.info(f"Load generation completed. Success: {self.metrics['success_count']}, Errors: {self.metrics['error_count']}")
    
    async def run_test(self, outage_duration: int = 60, load_duration: int = 120):
        """Run the complete chaos test"""
        logger.info("Starting coordinator outage chaos test")
        self.metrics["test_start"] = datetime.utcnow().isoformat()
        
        # Phase 1: Generate initial load
        logger.info("Phase 1: Generating initial load")
        await self.generate_load(30)
        
        # Phase 2: Induce outage
        logger.info("Phase 2: Inducing coordinator outage")
        self.metrics["outage_start"] = datetime.utcnow().isoformat()
        
        if not self.delete_coordinator_pods():
            logger.error("Failed to induce outage")
            return False
        
        if not await self.wait_for_pods_termination():
            logger.error("Pods did not terminate")
            return False
        
        # Wait for specified outage duration
        logger.info(f"Waiting for {outage_duration} seconds outage duration")
        await asyncio.sleep(outage_duration)
        
        # Phase 3: Monitor recovery
        logger.info("Phase 3: Monitoring service recovery")
        self.metrics["outage_end"] = datetime.utcnow().isoformat()
        
        if not await self.wait_for_recovery():
            logger.error("Service did not recover")
            return False
        
        # Phase 4: Post-recovery load test
        logger.info("Phase 4: Post-recovery load test")
        await self.generate_load(load_duration)
        
        # Calculate metrics
        self.metrics["test_end"] = datetime.utcnow().isoformat()
        self.metrics["mttr"] = self.metrics["recovery_time"]
        
        # Save results
        self.save_results()
        
        logger.info("Chaos test completed successfully")
        return True
    
    def save_results(self):
        """Save test results to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chaos_test_coordinator_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(self.metrics, f, indent=2)
        
        logger.info(f"Test results saved to: {filename}")
        
        # Print summary
        print("\n=== Chaos Test Summary ===")
        print(f"Scenario: {self.metrics['scenario']}")
        print(f"Test Duration: {self.metrics['test_start']} to {self.metrics['test_end']}")
        print(f"Outage Duration: {self.metrics['outage_start']} to {self.metrics['outage_end']}")
        print(f"MTTR: {self.metrics['mttr']:.2f} seconds" if self.metrics['mttr'] else "MTTR: N/A")
        print(f"Success Requests: {self.metrics['success_count']}")
        print(f"Error Requests: {self.metrics['error_count']}")
        print(f"Error Rate: {(self.metrics['error_count'] / (self.metrics['success_count'] + self.metrics['error_count']) * 100):.2f}%")


async def main():
    parser = argparse.ArgumentParser(description="Chaos test for coordinator API outage")
    parser.add_argument("--namespace", default="default", help="Kubernetes namespace")
    parser.add_argument("--outage-duration", type=int, default=60, help="Outage duration in seconds")
    parser.add_argument("--load-duration", type=int, default=120, help="Post-recovery load test duration")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without actual chaos")
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("DRY RUN: Would test coordinator outage without actual deletion")
        return
    
    # Verify kubectl is available
    try:
        subprocess.run(["kubectl", "version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("kubectl is not available or not configured")
        sys.exit(1)
    
    # Run test
    async with ChaosTestCoordinator(args.namespace) as test:
        success = await test.run_test(args.outage_duration, args.load_duration)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
