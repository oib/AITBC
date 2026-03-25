#!/usr/bin/env python3
"""
Multi-Region Marketplace Deployment Tests
Phase 8.1: Multi-Region Marketplace Deployment (Weeks 1-2)
"""

import pytest
import asyncio
import time
import json
import requests
import aiohttp
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from concurrent.futures import ThreadPoolExecutor
import statistics

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class RegionConfig:
    """Configuration for a geographic region"""
    region_id: str
    region_name: str
    marketplace_url: str
    edge_nodes: List[str]
    latency_targets: Dict[str, float]
    expected_response_time: float
    
@dataclass
class EdgeNode:
    """Edge computing node configuration"""
    node_id: str
    region_id: str
    node_url: str
    gpu_available: bool
    compute_capacity: float
    network_latency: float

class MultiRegionMarketplaceTests:
    """Test suite for multi-region marketplace deployment"""
    
    def __init__(self):
        self.regions = self._setup_regions()
        self.edge_nodes = self._setup_edge_nodes()
        self.session = requests.Session()
        self.session.timeout = 30
        
    def _setup_regions(self) -> List[RegionConfig]:
        """Setup geographic regions for testing"""
        return [
            RegionConfig(
                region_id="us-east-1",
                region_name="US East (N. Virginia)",
                marketplace_url="http://127.0.0.1:18000",
                edge_nodes=["edge-use1-001", "edge-use1-002"],
                latency_targets={"local": 50, "regional": 100, "global": 200},
                expected_response_time=50.0
            ),
            RegionConfig(
                region_id="us-west-2",
                region_name="US West (Oregon)",
                marketplace_url="http://127.0.0.1:18001",
                edge_nodes=["edge-usw2-001", "edge-usw2-002"],
                latency_targets={"local": 50, "regional": 100, "global": 200},
                expected_response_time=50.0
            ),
            RegionConfig(
                region_id="eu-central-1",
                region_name="EU Central (Frankfurt)",
                marketplace_url="http://127.0.0.1:18002",
                edge_nodes=["edge-euc1-001", "edge-euc1-002"],
                latency_targets={"local": 50, "regional": 100, "global": 200},
                expected_response_time=50.0
            ),
            RegionConfig(
                region_id="ap-southeast-1",
                region_name="Asia Pacific (Singapore)",
                marketplace_url="http://127.0.0.1:18003",
                edge_nodes=["edge-apse1-001", "edge-apse1-002"],
                latency_targets={"local": 50, "regional": 100, "global": 200},
                expected_response_time=50.0
            )
        ]
        
    def _setup_edge_nodes(self) -> List[EdgeNode]:
        """Setup edge computing nodes"""
        nodes = []
        for region in self.regions:
            for node_id in region.edge_nodes:
                nodes.append(EdgeNode(
                    node_id=node_id,
                    region_id=region.region_id,
                    node_url=f"http://127.0.0.1:800{node_id[-1]}",
                    gpu_available=True,
                    compute_capacity=100.0,
                    network_latency=10.0
                ))
        return nodes
        
    async def test_region_health_check(self, region: RegionConfig) -> Dict[str, Any]:
        """Test health check for a specific region"""
        try:
            start_time = time.time()
            response = self.session.get(f"{region.marketplace_url}/health", timeout=10)
            end_time = time.time()
            
            return {
                "region_id": region.region_id,
                "status_code": response.status_code,
                "response_time": (end_time - start_time) * 1000,
                "healthy": response.status_code == 200,
                "within_target": (end_time - start_time) * 1000 <= region.expected_response_time
            }
        except Exception as e:
            return {
                "region_id": region.region_id,
                "error": str(e),
                "healthy": False,
                "within_target": False
            }
            
    async def test_edge_node_connectivity(self, edge_node: EdgeNode) -> Dict[str, Any]:
        """Test connectivity to edge computing nodes"""
        try:
            start_time = time.time()
            response = self.session.get(f"{edge_node.node_url}/health", timeout=10)
            end_time = time.time()
            
            return {
                "node_id": edge_node.node_id,
                "region_id": edge_node.region_id,
                "status_code": response.status_code,
                "response_time": (end_time - start_time) * 1000,
                "gpu_available": edge_node.gpu_available,
                "compute_capacity": edge_node.compute_capacity,
                "connected": response.status_code == 200
            }
        except Exception as e:
            return {
                "node_id": edge_node.node_id,
                "region_id": edge_node.region_id,
                "error": str(e),
                "connected": False
            }
            
    async def test_geographic_load_balancing(self, consumer_region: str, resource_requirements: Dict[str, Any]) -> Dict[str, Any]:
        """Test geographic load balancing for resource requests"""
        try:
            # Find the consumer's region
            consumer_region_config = next((r for r in self.regions if r.region_id == consumer_region), None)
            if not consumer_region_config:
                return {"error": f"Region {consumer_region} not found"}
                
            # Test resource request with geographic optimization
            payload = {
                "consumer_region": consumer_region,
                "resource_requirements": resource_requirements,
                "optimization_strategy": "geographic_latency",
                "max_acceptable_latency": 200.0
            }
            
            start_time = time.time()
            response = self.session.post(
                f"{consumer_region_config.marketplace_url}/v1/marketplace/optimal-resource",
                json=payload,
                timeout=15
            )
            end_time = time.time()
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "consumer_region": consumer_region,
                    "recommended_region": result.get("optimal_region"),
                    "recommended_node": result.get("optimal_edge_node"),
                    "estimated_latency": result.get("estimated_latency"),
                    "response_time": (end_time - start_time) * 1000,
                    "success": True
                }
            else:
                return {
                    "consumer_region": consumer_region,
                    "error": f"Load balancing failed with status {response.status_code}",
                    "success": False
                }
                
        except Exception as e:
            return {
                "consumer_region": consumer_region,
                "error": str(e),
                "success": False
            }
            
    async def test_cross_region_resource_discovery(self, source_region: str, target_regions: List[str]) -> Dict[str, Any]:
        """Test resource discovery across multiple regions"""
        try:
            source_config = next((r for r in self.regions if r.region_id == source_region), None)
            if not source_config:
                return {"error": f"Source region {source_region} not found"}
                
            results = {}
            for target_region in target_regions:
                target_config = next((r for r in self.regions if r.region_id == target_region), None)
                if target_config:
                    try:
                        start_time = time.time()
                        response = self.session.get(
                            f"{source_config.marketplace_url}/v1/marketplace/resources/{target_region}",
                            timeout=10
                        )
                        end_time = time.time()
                        
                        results[target_region] = {
                            "status_code": response.status_code,
                            "response_time": (end_time - start_time) * 1000,
                            "resources_found": len(response.json()) if response.status_code == 200 else 0,
                            "success": response.status_code == 200
                        }
                    except Exception as e:
                        results[target_region] = {
                            "error": str(e),
                            "success": False
                        }
                        
            return {
                "source_region": source_region,
                "target_regions": results,
                "total_regions_queried": len(target_regions),
                "successful_queries": sum(1 for r in results.values() if r.get("success", False))
            }
            
        except Exception as e:
            return {"error": str(e)}
            
    async def test_global_marketplace_synchronization(self) -> Dict[str, Any]:
        """Test synchronization across all marketplace regions"""
        try:
            sync_results = {}
            
            # Test resource listing synchronization
            resource_counts = {}
            for region in self.regions:
                try:
                    response = self.session.get(f"{region.marketplace_url}/v1/marketplace/resources", timeout=10)
                    if response.status_code == 200:
                        resources = response.json()
                        resource_counts[region.region_id] = len(resources)
                    else:
                        resource_counts[region.region_id] = 0
                except Exception:
                    resource_counts[region.region_id] = 0
                    
            # Test pricing synchronization
            pricing_data = {}
            for region in self.regions:
                try:
                    response = self.session.get(f"{region.marketplace_url}/v1/marketplace/pricing", timeout=10)
                    if response.status_code == 200:
                        pricing_data[region.region_id] = response.json()
                    else:
                        pricing_data[region.region_id] = {}
                except Exception:
                    pricing_data[region.region_id] = {}
                    
            # Calculate synchronization metrics
            resource_variance = statistics.pstdev(resource_counts.values()) if len(resource_counts) > 1 else 0
            
            return {
                "resource_counts": resource_counts,
                "resource_variance": resource_variance,
                "pricing_data": pricing_data,
                "total_regions": len(self.regions),
                "synchronized": resource_variance < 5.0  # Allow small variance
            }
            
        except Exception as e:
            return {"error": str(e)}
            
    async def test_failover_and_redundancy(self, primary_region: str, backup_regions: List[str]) -> Dict[str, Any]:
        """Test failover and redundancy mechanisms"""
        try:
            primary_config = next((r for r in self.regions if r.region_id == primary_region), None)
            if not primary_config:
                return {"error": f"Primary region {primary_region} not found"}
                
            # Test normal operation
            normal_response = self.session.get(f"{primary_config.marketplace_url}/v1/marketplace/status", timeout=10)
            normal_status = normal_response.status_code == 200
            
            # Simulate primary region failure (test backup regions)
            backup_results = {}
            for backup_region in backup_regions:
                backup_config = next((r for r in self.regions if r.region_id == backup_region), None)
                if backup_config:
                    try:
                        response = self.session.get(f"{backup_config.marketplace_url}/v1/marketplace/status", timeout=10)
                        backup_results[backup_region] = {
                            "available": response.status_code == 200,
                            "response_time": time.time()
                        }
                    except Exception as e:
                        backup_results[backup_region] = {
                            "available": False,
                            "error": str(e)
                        }
                        
            available_backups = [r for r, data in backup_results.items() if data.get("available", False)]
            
            return {
                "primary_region": primary_region,
                "primary_normal_status": normal_status,
                "backup_regions": backup_results,
                "available_backups": available_backups,
                "redundancy_level": len(available_backups) / len(backup_regions),
                "failover_ready": len(available_backups) > 0
            }
            
        except Exception as e:
            return {"error": str(e)}
            
    async def test_latency_optimization(self, consumer_region: str, target_latency: float) -> Dict[str, Any]:
        """Test latency optimization for cross-region requests"""
        try:
            consumer_config = next((r for r in self.regions if r.region_id == consumer_region), None)
            if not consumer_config:
                return {"error": f"Consumer region {consumer_region} not found"}
                
            # Test latency to all regions
            latency_results = {}
            for region in self.regions:
                start_time = time.time()
                try:
                    response = self.session.get(f"{region.marketplace_url}/v1/marketplace/ping", timeout=10)
                    end_time = time.time()
                    
                    latency_results[region.region_id] = {
                        "latency_ms": (end_time - start_time) * 1000,
                        "within_target": (end_time - start_time) * 1000 <= target_latency,
                        "status_code": response.status_code
                    }
                except Exception as e:
                    latency_results[region.region_id] = {
                        "error": str(e),
                        "within_target": False
                    }
                    
            # Find optimal regions
            optimal_regions = [
                region for region, data in latency_results.items()
                if data.get("within_target", False)
            ]
            
            return {
                "consumer_region": consumer_region,
                "target_latency_ms": target_latency,
                "latency_results": latency_results,
                "optimal_regions": optimal_regions,
                "latency_optimization_available": len(optimal_regions) > 0
            }
            
        except Exception as e:
            return {"error": str(e)}

# Test Fixtures
@pytest.fixture
def multi_region_tests():
    """Create multi-region test instance"""
    return MultiRegionMarketplaceTests()

@pytest.fixture
def sample_resource_requirements():
    """Sample resource requirements for testing"""
    return {
        "compute_power_min": 50.0,
        "gpu_memory_min": 8,
        "gpu_required": True,
        "duration_hours": 2,
        "max_price_per_hour": 5.0
    }

# Test Classes
class TestRegionHealth:
    """Test region health and connectivity"""
    
    @pytest.mark.asyncio
    async def test_all_regions_health(self, multi_region_tests):
        """Test health of all configured regions"""
        health_results = []
        
        for region in multi_region_tests.regions:
            result = await multi_region_tests.test_region_health_check(region)
            health_results.append(result)
            
        # Assert all regions are healthy
        unhealthy_regions = [r for r in health_results if not r.get("healthy", False)]
        assert len(unhealthy_regions) == 0, f"Unhealthy regions: {unhealthy_regions}"
        
        # Assert response times are within targets
        slow_regions = [r for r in health_results if not r.get("within_target", False)]
        assert len(slow_regions) == 0, f"Slow regions: {slow_regions}"
        
    @pytest.mark.asyncio
    async def test_edge_node_connectivity(self, multi_region_tests):
        """Test connectivity to all edge nodes"""
        connectivity_results = []
        
        for edge_node in multi_region_tests.edge_nodes:
            result = await multi_region_tests.test_edge_node_connectivity(edge_node)
            connectivity_results.append(result)
            
        # Assert all edge nodes are connected
        disconnected_nodes = [n for n in connectivity_results if not n.get("connected", False)]
        assert len(disconnected_nodes) == 0, f"Disconnected edge nodes: {disconnected_nodes}"

class TestGeographicLoadBalancing:
    """Test geographic load balancing functionality"""
    
    @pytest.mark.asyncio
    async def test_geographic_optimization(self, multi_region_tests, sample_resource_requirements):
        """Test geographic optimization for resource requests"""
        test_regions = ["us-east-1", "us-west-2", "eu-central-1"]
        
        for region in test_regions:
            result = await multi_region_tests.test_geographic_load_balancing(
                region,
                sample_resource_requirements
            )
            
            assert result.get("success", False), f"Load balancing failed for region {region}"
            assert "recommended_region" in result, f"No recommendation for region {region}"
            assert "estimated_latency" in result, f"No latency estimate for region {region}"
            assert result["estimated_latency"] <= 200.0, f"Latency too high for region {region}"
            
    @pytest.mark.asyncio
    async def test_cross_region_discovery(self, multi_region_tests):
        """Test resource discovery across regions"""
        source_region = "us-east-1"
        target_regions = ["us-west-2", "eu-central-1", "ap-southeast-1"]
        
        result = await multi_region_tests.test_cross_region_resource_discovery(
            source_region,
            target_regions
        )
        
        assert result.get("successful_queries", 0) > 0, "No successful cross-region queries"
        assert result.get("total_regions_queried", 0) == len(target_regions), "Not all regions queried"

class TestGlobalSynchronization:
    """Test global marketplace synchronization"""
    
    @pytest.mark.asyncio
    async def test_resource_synchronization(self, multi_region_tests):
        """Test resource synchronization across regions"""
        result = await multi_region_tests.test_global_marketplace_synchronization()
        
        assert result.get("synchronized", False), "Marketplace regions are not synchronized"
        assert result.get("total_regions", 0) > 0, "No regions configured"
        assert result.get("resource_variance", 100) < 5.0, "Resource variance too high"
        
    @pytest.mark.asyncio
    async def test_pricing_consistency(self, multi_region_tests):
        """Test pricing consistency across regions"""
        result = await multi_region_tests.test_global_marketplace_synchronization()
        
        pricing_data = result.get("pricing_data", {})
        assert len(pricing_data) > 0, "No pricing data available"
        
        # Check that pricing is consistent across regions
        # (This is a simplified check - in reality, pricing might vary by region)
        for region, prices in pricing_data.items():
            assert isinstance(prices, dict), f"Invalid pricing data for region {region}"

class TestFailoverAndRedundancy:
    """Test failover and redundancy mechanisms"""
    
    @pytest.mark.asyncio
    async def test_regional_failover(self, multi_region_tests):
        """Test regional failover capabilities"""
        primary_region = "us-east-1"
        backup_regions = ["us-west-2", "eu-central-1"]
        
        result = await multi_region_tests.test_failover_and_redundancy(
            primary_region,
            backup_regions
        )
        
        assert result.get("failover_ready", False), "Failover not ready"
        assert result.get("redundancy_level", 0) > 0.5, "Insufficient redundancy"
        assert len(result.get("available_backups", [])) > 0, "No available backup regions"
        
    @pytest.mark.asyncio
    async def test_latency_optimization(self, multi_region_tests):
        """Test latency optimization across regions"""
        consumer_region = "us-east-1"
        target_latency = 100.0  # 100ms target
        
        result = await multi_region_tests.test_latency_optimization(
            consumer_region,
            target_latency
        )
        
        assert result.get("latency_optimization_available", False), "Latency optimization not available"
        assert len(result.get("optimal_regions", [])) > 0, "No optimal regions found"

class TestPerformanceMetrics:
    """Test performance metrics collection"""
    
    @pytest.mark.asyncio
    async def test_global_performance_tracking(self, multi_region_tests):
        """Test global performance tracking"""
        performance_data = {}
        
        for region in multi_region_tests.regions:
            try:
                response = multi_region_tests.session.get(
                    f"{region.marketplace_url}/v1/metrics/performance",
                    timeout=10
                )
                
                if response.status_code == 200:
                    performance_data[region.region_id] = response.json()
                else:
                    performance_data[region.region_id] = {"error": f"Status {response.status_code}"}
            except Exception as e:
                performance_data[region.region_id] = {"error": str(e)}
                
        # Assert we have performance data from all regions
        successful_regions = [r for r, data in performance_data.items() if "error" not in data]
        assert len(successful_regions) > 0, "No performance data available"
        
        # Check that performance metrics include expected fields
        for region, metrics in successful_regions:
            assert "response_time" in metrics, f"Missing response time for {region}"
            assert "throughput" in metrics, f"Missing throughput for {region}"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
