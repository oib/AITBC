#!/usr/bin/env python3
"""
Chaos Testing Script - Network Partition
Tests system resilience when blockchain nodes experience network partitions
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


class ChaosTestNetwork:
    """Chaos testing for network partition scenarios"""
    
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self.session = None
        self.metrics = {
            "test_start": None,
            "test_end": None,
            "partition_start": None,
            "partition_end": None,
            "recovery_time": None,
            "mttr": None,
            "error_count": 0,
            "success_count": 0,
            "scenario": "network_partition",
            "affected_nodes": []
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def get_blockchain_pods(self) -> List[str]:
        """Get list of blockchain node pods"""
        cmd = [
            "kubectl", "get", "pods",
            "-n", self.namespace,
            "-l", "app.kubernetes.io/name=blockchain-node",
            "-o", "jsonpath={.items[*].metadata.name}"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            pods = result.stdout.strip().split()
            return pods
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get blockchain pods: {e}")
            return []
    
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
    
    def apply_network_partition(self, pods: List[str], target_pods: List[str]) -> bool:
        """Apply network partition using iptables"""
        logger.info(f"Applying network partition: blocking traffic between {len(pods)} and {len(target_pods)} pods")
        
        for pod in pods:
            if pod in target_pods:
                continue
                
            # Block traffic from this pod to target pods
            for target_pod in target_pods:
                try:
                    # Get target pod IP
                    cmd = [
                        "kubectl", "get", "pod", target_pod,
                        "-n", self.namespace,
                        "-o", "jsonpath={.status.podIP}"
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    target_ip = result.stdout.strip()
                    
                    if not target_ip:
                        continue
                    
                    # Apply iptables rule to block traffic
                    iptables_cmd = [
                        "kubectl", "exec", "-n", self.namespace, pod, "--",
                        "iptables", "-A", "OUTPUT", "-d", target_ip, "-j", "DROP"
                    ]
                    subprocess.run(iptables_cmd, check=True)
                    
                    logger.info(f"Blocked traffic from {pod} to {target_pod} ({target_ip})")
                    
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to block traffic from {pod} to {target_pod}: {e}")
                    return False
        
        self.metrics["affected_nodes"] = pods + target_pods
        return True
    
    def remove_network_partition(self, pods: List[str]) -> bool:
        """Remove network partition rules"""
        logger.info("Removing network partition rules")
        
        for pod in pods:
            try:
                # Flush OUTPUT chain (remove all rules)
                cmd = [
                    "kubectl", "exec", "-n", self.namespace, pod, "--",
                    "iptables", "-F", "OUTPUT"
                ]
                subprocess.run(cmd, check=True)
                logger.info(f"Removed network rules from {pod}")
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to remove network rules from {pod}: {e}")
                return False
        
        return True
    
    async def test_connectivity(self, pods: List[str]) -> Dict[str, bool]:
        """Test connectivity between pods"""
        results = {}
        
        for pod in pods:
            try:
                # Test if pod can reach coordinator
                cmd = [
                    "kubectl", "exec", "-n", self.namespace, pod, "--",
                    "curl", "-s", "--max-time", "5", "http://coordinator:8011/v1/health"
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                results[pod] = result.returncode == 0 and "ok" in result.stdout
                
            except Exception:
                results[pod] = False
        
        return results
    
    async def monitor_consensus(self, duration: int = 60) -> bool:
        """Monitor blockchain consensus health"""
        logger.info(f"Monitoring consensus for {duration} seconds")
        
        start_time = time.time()
        last_height = 0
        
        while time.time() - start_time < duration:
            try:
                # Get block height from a random pod
                pods = self.get_blockchain_pods()
                if not pods:
                    await asyncio.sleep(5)
                    continue
                
                # Use first pod to check height
                cmd = [
                    "kubectl", "exec", "-n", self.namespace, pods[0], "--",
                    "curl", "-s", "http://localhost:8080/v1/blocks/head"
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    try:
                        data = json.loads(result.stdout)
                        current_height = data.get("height", 0)
                        
                        # Check if blockchain is progressing
                        if current_height > last_height:
                            last_height = current_height
                            logger.info(f"Blockchain progressing, height: {current_height}")
                        elif time.time() - start_time > 30:  # Allow 30s for initial sync
                            logger.warning(f"Blockchain stuck at height {current_height}")
                    
                    except json.JSONDecodeError:
                        pass
                
            except Exception as e:
                logger.debug(f"Consensus check failed: {e}")
            
            await asyncio.sleep(5)
        
        return last_height > 0
    
    async def generate_load(self, duration: int, concurrent: int = 5):
        """Generate synthetic load on blockchain nodes"""
        logger.info(f"Generating load for {duration} seconds with {concurrent} concurrent requests")
        
        # Get service URL
        cmd = [
            "kubectl", "get", "svc", "blockchain-node",
            "-n", self.namespace,
            "-o", "jsonpath={.spec.clusterIP}:{.spec.ports[0].port}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        base_url = f"http://{result.stdout.strip()}"
        
        start_time = time.time()
        tasks = []
        
        async def make_request():
            try:
                async with self.session.get(f"{base_url}/v1/blocks/head") as response:
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
    
    async def run_test(self, partition_duration: int = 60, partition_ratio: float = 0.5):
        """Run the complete network partition chaos test"""
        logger.info("Starting network partition chaos test")
        self.metrics["test_start"] = datetime.utcnow().isoformat()
        
        # Get all blockchain pods
        all_pods = self.get_blockchain_pods()
        if not all_pods:
            logger.error("No blockchain pods found")
            return False
        
        # Determine which pods to partition
        num_partition = int(len(all_pods) * partition_ratio)
        partition_pods = all_pods[:num_partition]
        remaining_pods = all_pods[num_partition:]
        
        logger.info(f"Partitioning {len(partition_pods)} pods out of {len(all_pods)} total")
        
        # Phase 1: Baseline test
        logger.info("Phase 1: Baseline connectivity test")
        baseline_connectivity = await self.test_connectivity(all_pods)
        logger.info(f"Baseline connectivity: {sum(baseline_connectivity.values())}/{len(all_pods)} pods connected")
        
        # Phase 2: Generate initial load
        logger.info("Phase 2: Generating initial load")
        await self.generate_load(30)
        
        # Phase 3: Apply network partition
        logger.info("Phase 3: Applying network partition")
        self.metrics["partition_start"] = datetime.utcnow().isoformat()
        
        if not self.apply_network_partition(remaining_pods, partition_pods):
            logger.error("Failed to apply network partition")
            return False
        
        # Verify partition is effective
        await asyncio.sleep(5)
        partitioned_connectivity = await self.test_connectivity(all_pods)
        logger.info(f"Partitioned connectivity: {sum(partitioned_connectivity.values())}/{len(all_pods)} pods connected")
        
        # Phase 4: Monitor during partition
        logger.info(f"Phase 4: Monitoring system during {partition_duration}s partition")
        consensus_healthy = await self.monitor_consensus(partition_duration)
        
        # Phase 5: Remove partition and monitor recovery
        logger.info("Phase 5: Removing network partition")
        self.metrics["partition_end"] = datetime.utcnow().isoformat()
        
        if not self.remove_network_partition(all_pods):
            logger.error("Failed to remove network partition")
            return False
        
        # Wait for recovery
        logger.info("Waiting for network recovery...")
        await asyncio.sleep(10)
        
        # Test connectivity after recovery
        recovery_connectivity = await self.test_connectivity(all_pods)
        recovery_time = time.time()
        
        # Calculate recovery metrics
        all_connected = all(recovery_connectivity.values())
        if all_connected:
            self.metrics["recovery_time"] = recovery_time - (datetime.fromisoformat(self.metrics["partition_end"]).timestamp())
            logger.info(f"Network recovered in {self.metrics['recovery_time']:.2f} seconds")
        
        # Phase 6: Post-recovery load test
        logger.info("Phase 6: Post-recovery load test")
        await self.generate_load(60)
        
        # Final metrics
        self.metrics["test_end"] = datetime.utcnow().isoformat()
        self.metrics["mttr"] = self.metrics["recovery_time"]
        
        # Save results
        self.save_results()
        
        logger.info("Network partition chaos test completed successfully")
        return True
    
    def save_results(self):
        """Save test results to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chaos_test_network_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(self.metrics, f, indent=2)
        
        logger.info(f"Test results saved to: {filename}")
        
        # Print summary
        print("\n=== Chaos Test Summary ===")
        print(f"Scenario: {self.metrics['scenario']}")
        print(f"Test Duration: {self.metrics['test_start']} to {self.metrics['test_end']}")
        print(f"Partition Duration: {self.metrics['partition_start']} to {self.metrics['partition_end']}")
        print(f"MTTR: {self.metrics['mttr']:.2f} seconds" if self.metrics['mttr'] else "MTTR: N/A")
        print(f"Affected Nodes: {len(self.metrics['affected_nodes'])}")
        print(f"Success Requests: {self.metrics['success_count']}")
        print(f"Error Requests: {self.metrics['error_count']}")


async def main():
    parser = argparse.ArgumentParser(description="Chaos test for network partition")
    parser.add_argument("--namespace", default="default", help="Kubernetes namespace")
    parser.add_argument("--partition-duration", type=int, default=60, help="Partition duration in seconds")
    parser.add_argument("--partition-ratio", type=float, default=0.5, help="Fraction of nodes to partition (0.0-1.0)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without actual chaos")
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info(f"DRY RUN: Would partition {args.partition_ratio * 100}% of nodes for {args.partition_duration} seconds")
        return
    
    # Verify kubectl is available
    try:
        subprocess.run(["kubectl", "version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("kubectl is not available or not configured")
        sys.exit(1)
    
    # Run test
    async with ChaosTestNetwork(args.namespace) as test:
        success = await test.run_test(args.partition_duration, args.partition_ratio)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
