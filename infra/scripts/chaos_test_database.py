#!/usr/bin/env python3
"""
Chaos Testing Script - Database Failure
Tests system resilience when PostgreSQL database becomes unavailable
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


class ChaosTestDatabase:
    """Chaos testing for database failure scenarios"""
    
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self.session = None
        self.metrics = {
            "test_start": None,
            "test_end": None,
            "failure_start": None,
            "failure_end": None,
            "recovery_time": None,
            "mttr": None,
            "error_count": 0,
            "success_count": 0,
            "scenario": "database_failure",
            "failure_type": None
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def get_postgresql_pod(self) -> Optional[str]:
        """Get PostgreSQL pod name"""
        cmd = [
            "kubectl", "get", "pods",
            "-n", self.namespace,
            "-l", "app.kubernetes.io/name=postgresql",
            "-o", "jsonpath={.items[0].metadata.name}"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            pod = result.stdout.strip()
            return pod if pod else None
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get PostgreSQL pod: {e}")
            return None
    
    def simulate_database_connection_failure(self) -> bool:
        """Simulate database connection failure by blocking port 5432"""
        pod = self.get_postgresql_pod()
        if not pod:
            return False
        
        try:
            # Block incoming connections to PostgreSQL
            cmd = [
                "kubectl", "exec", "-n", self.namespace, pod, "--",
                "iptables", "-A", "INPUT", "-p", "tcp", "--dport", "5432", "-j", "DROP"
            ]
            subprocess.run(cmd, check=True)
            
            # Block outgoing connections from PostgreSQL
            cmd = [
                "kubectl", "exec", "-n", self.namespace, pod, "--",
                "iptables", "-A", "OUTPUT", "-p", "tcp", "--sport", "5432", "-j", "DROP"
            ]
            subprocess.run(cmd, check=True)
            
            logger.info(f"Blocked PostgreSQL connections on pod {pod}")
            self.metrics["failure_type"] = "connection_blocked"
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to block PostgreSQL connections: {e}")
            return False
    
    def simulate_database_high_latency(self, latency_ms: int = 5000) -> bool:
        """Simulate high database latency using netem"""
        pod = self.get_postgresql_pod()
        if not pod:
            return False
        
        try:
            # Add latency to PostgreSQL traffic
            cmd = [
                "kubectl", "exec", "-n", self.namespace, pod, "--",
                "tc", "qdisc", "add", "dev", "eth0", "root", "netem", "delay", f"{latency_ms}ms"
            ]
            subprocess.run(cmd, check=True)
            
            logger.info(f"Added {latency_ms}ms latency to PostgreSQL on pod {pod}")
            self.metrics["failure_type"] = "high_latency"
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add latency to PostgreSQL: {e}")
            return False
    
    def restore_database(self) -> bool:
        """Restore database connections"""
        pod = self.get_postgresql_pod()
        if not pod:
            return False
        
        try:
            # Remove iptables rules
            cmd = [
                "kubectl", "exec", "-n", self.namespace, pod, "--",
                "iptables", "-F", "INPUT"
            ]
            subprocess.run(cmd, check=False)  # May fail if rules don't exist
            
            cmd = [
                "kubectl", "exec", "-n", self.namespace, pod, "--",
                "iptables", "-F", "OUTPUT"
            ]
            subprocess.run(cmd, check=False)
            
            # Remove netem qdisc
            cmd = [
                "kubectl", "exec", "-n", self.namespace, pod, "--",
                "tc", "qdisc", "del", "dev", "eth0", "root"
            ]
            subprocess.run(cmd, check=False)
            
            logger.info(f"Restored PostgreSQL connections on pod {pod}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restore PostgreSQL: {e}")
            return False
    
    async def test_database_connectivity(self) -> bool:
        """Test if coordinator can connect to database"""
        try:
            # Get coordinator pod
            cmd = [
                "kubectl", "get", "pods",
                "-n", self.namespace,
                "-l", "app.kubernetes.io/name=coordinator",
                "-o", "jsonpath={.items[0].metadata.name}"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            coordinator_pod = result.stdout.strip()
            
            if not coordinator_pod:
                return False
            
            # Test database connection from coordinator
            cmd = [
                "kubectl", "exec", "-n", self.namespace, coordinator_pod, "--",
                "python", "-c", "import psycopg2; psycopg2.connect('postgresql://aitbc:password@postgresql:5432/aitbc'); print('OK')"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            return result.returncode == 0 and "OK" in result.stdout
            
        except Exception:
            return False
    
    async def test_api_health(self) -> bool:
        """Test if coordinator API is healthy"""
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
                async with self.session.get(f"{base_url}/v1/marketplace/offers") as response:
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
    
    async def wait_for_recovery(self, timeout: int = 300) -> bool:
        """Wait for database and API to recover"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Test database connectivity
            db_connected = await self.test_database_connectivity()
            
            # Test API health
            api_healthy = await self.test_api_health()
            
            if db_connected and api_healthy:
                recovery_time = time.time() - start_time
                self.metrics["recovery_time"] = recovery_time
                logger.info(f"Database and API recovered in {recovery_time:.2f} seconds")
                return True
            
            await asyncio.sleep(5)
        
        logger.error("Database and API did not recover within timeout")
        return False
    
    async def run_test(self, failure_type: str = "connection", failure_duration: int = 60):
        """Run the complete database chaos test"""
        logger.info(f"Starting database chaos test - failure type: {failure_type}")
        self.metrics["test_start"] = datetime.utcnow().isoformat()
        
        # Phase 1: Baseline test
        logger.info("Phase 1: Baseline connectivity test")
        db_connected = await self.test_database_connectivity()
        api_healthy = await self.test_api_health()
        
        if not db_connected or not api_healthy:
            logger.error("Baseline test failed - database or API not healthy")
            return False
        
        logger.info("Baseline: Database and API are healthy")
        
        # Phase 2: Generate initial load
        logger.info("Phase 2: Generating initial load")
        await self.generate_load(30)
        
        # Phase 3: Induce database failure
        logger.info("Phase 3: Inducing database failure")
        self.metrics["failure_start"] = datetime.utcnow().isoformat()
        
        if failure_type == "connection":
            if not self.simulate_database_connection_failure():
                logger.error("Failed to induce database connection failure")
                return False
        elif failure_type == "latency":
            if not self.simulate_database_high_latency():
                logger.error("Failed to induce database latency")
                return False
        else:
            logger.error(f"Unknown failure type: {failure_type}")
            return False
        
        # Verify failure is effective
        await asyncio.sleep(5)
        db_connected = await self.test_database_connectivity()
        api_healthy = await self.test_api_health()
        
        logger.info(f"During failure - DB connected: {db_connected}, API healthy: {api_healthy}")
        
        # Phase 4: Monitor during failure
        logger.info(f"Phase 4: Monitoring system during {failure_duration}s failure")
        
        # Generate load during failure
        await self.generate_load(failure_duration)
        
        # Phase 5: Restore database and monitor recovery
        logger.info("Phase 5: Restoring database")
        self.metrics["failure_end"] = datetime.utcnow().isoformat()
        
        if not self.restore_database():
            logger.error("Failed to restore database")
            return False
        
        # Wait for recovery
        if not await self.wait_for_recovery():
            logger.error("System did not recover after database restoration")
            return False
        
        # Phase 6: Post-recovery load test
        logger.info("Phase 6: Post-recovery load test")
        await self.generate_load(60)
        
        # Final metrics
        self.metrics["test_end"] = datetime.utcnow().isoformat()
        self.metrics["mttr"] = self.metrics["recovery_time"]
        
        # Save results
        self.save_results()
        
        logger.info("Database chaos test completed successfully")
        return True
    
    def save_results(self):
        """Save test results to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chaos_test_database_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(self.metrics, f, indent=2)
        
        logger.info(f"Test results saved to: {filename}")
        
        # Print summary
        print("\n=== Chaos Test Summary ===")
        print(f"Scenario: {self.metrics['scenario']}")
        print(f"Failure Type: {self.metrics['failure_type']}")
        print(f"Test Duration: {self.metrics['test_start']} to {self.metrics['test_end']}")
        print(f"Failure Duration: {self.metrics['failure_start']} to {self.metrics['failure_end']}")
        print(f"MTTR: {self.metrics['mttr']:.2f} seconds" if self.metrics['mttr'] else "MTTR: N/A")
        print(f"Success Requests: {self.metrics['success_count']}")
        print(f"Error Requests: {self.metrics['error_count']}")


async def main():
    parser = argparse.ArgumentParser(description="Chaos test for database failure")
    parser.add_argument("--namespace", default="default", help="Kubernetes namespace")
    parser.add_argument("--failure-type", choices=["connection", "latency"], default="connection", help="Type of failure to simulate")
    parser.add_argument("--failure-duration", type=int, default=60, help="Failure duration in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without actual chaos")
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info(f"DRY RUN: Would simulate {args.failure_type} database failure for {args.failure_duration} seconds")
        return
    
    # Verify kubectl is available
    try:
        subprocess.run(["kubectl", "version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("kubectl is not available or not configured")
        sys.exit(1)
    
    # Run test
    async with ChaosTestDatabase(args.namespace) as test:
        success = await test.run_test(args.failure_type, args.failure_duration)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
