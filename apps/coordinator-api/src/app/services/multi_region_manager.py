"""
Multi-Region Deployment Manager - Phase 6.3 Implementation
Geographic load balancing, data residency compliance, and disaster recovery
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class RegionStatus(StrEnum):
    """Region deployment status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    FAILOVER = "failover"


class DataResidencyType(StrEnum):
    """Data residency requirements"""

    LOCAL = "local"
    REGIONAL = "regional"
    GLOBAL = "global"
    HYBRID = "hybrid"


class LoadBalancingStrategy(StrEnum):
    """Load balancing strategies"""

    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    GEOGRAPHIC = "geographic"
    PERFORMANCE_BASED = "performance_based"


@dataclass
class Region:
    """Geographic region configuration"""

    region_id: str
    name: str
    code: str  # ISO 3166-1 alpha-2
    location: dict[str, float]  # lat, lng
    endpoints: list[str]
    data_residency: DataResidencyType
    compliance_requirements: list[str]
    capacity: dict[str, int]  # max_users, max_requests, max_storage
    current_load: dict[str, int] = field(default_factory=dict)
    status: RegionStatus = RegionStatus.ACTIVE
    health_score: float = 1.0
    latency_ms: float = 0.0
    last_health_check: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FailoverConfig:
    """Failover configuration"""

    primary_region: str
    backup_regions: list[str]
    failover_threshold: float  # Health score threshold
    failover_timeout: timedelta
    auto_failover: bool = True
    data_sync: bool = True
    health_check_interval: timedelta = field(default_factory=lambda: timedelta(minutes=5))


@dataclass
class DataSyncConfig:
    """Data synchronization configuration"""

    sync_type: str  # real-time, batch, periodic
    sync_interval: timedelta
    conflict_resolution: str  # primary_wins, timestamp_wins, manual
    encryption_required: bool = True
    compression_enabled: bool = True


class GeographicLoadBalancer:
    """Geographic load balancer for multi-region deployment"""

    def __init__(self):
        self.regions = {}
        self.load_balancing_strategy = LoadBalancingStrategy.GEOGRAPHIC
        self.region_weights = {}
        self.request_history = {}
        self.logger = get_logger("geo_load_balancer")

    async def add_region(self, region: Region) -> bool:
        """Add region to load balancer"""

        try:
            self.regions[region.region_id] = region

            # Initialize region weights
            self.region_weights[region.region_id] = 1.0

            # Initialize request history
            self.request_history[region.region_id] = []

            self.logger.info(f"Region added to load balancer: {region.region_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add region: {e}")
            return False

    async def remove_region(self, region_id: str) -> bool:
        """Remove region from load balancer"""

        if region_id in self.regions:
            del self.regions[region_id]
            del self.region_weights[region_id]
            del self.request_history[region_id]

            self.logger.info(f"Region removed from load balancer: {region_id}")
            return True

        return False

    async def select_region(
        self, user_location: dict[str, float] | None = None, user_preferences: dict[str, Any] | None = None
    ) -> str | None:
        """Select optimal region for user request"""

        try:
            if not self.regions:
                return None

            # Filter active regions
            active_regions = {
                rid: r for rid, r in self.regions.items() if r.status == RegionStatus.ACTIVE and r.health_score >= 0.7
            }

            if not active_regions:
                return None

            # Select region based on strategy
            if self.load_balancing_strategy == LoadBalancingStrategy.GEOGRAPHIC:
                return await self._select_geographic_region(active_regions, user_location)
            elif self.load_balancing_strategy == LoadBalancingStrategy.PERFORMANCE_BASED:
                return await self._select_performance_region(active_regions)
            elif self.load_balancing_strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
                return await self._select_weighted_region(active_regions)
            else:
                return await self._select_round_robin_region(active_regions)

        except Exception as e:
            self.logger.error(f"Region selection failed: {e}")
            return None

    async def _select_geographic_region(self, regions: dict[str, Region], user_location: dict[str, float] | None) -> str:
        """Select region based on geographic proximity"""

        if not user_location:
            # Fallback to performance-based selection
            return await self._select_performance_region(regions)

        user_lat = user_location.get("latitude", 0.0)
        user_lng = user_location.get("longitude", 0.0)

        # Calculate distances to all regions
        region_distances = {}

        for region_id, region in regions.items():
            region_lat = region.location["latitude"]
            region_lng = region.location["longitude"]

            # Calculate distance using Haversine formula
            distance = self._calculate_distance(user_lat, user_lng, region_lat, region_lng)
            region_distances[region_id] = distance

        # Select closest region
        closest_region = min(region_distances, key=region_distances.get)

        return closest_region

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two geographic points"""

        # Haversine formula
        R = 6371  # Earth's radius in kilometers

        lat_diff = (lat2 - lat1) * 3.14159 / 180
        lng_diff = (lng2 - lng1) * 3.14159 / 180

        a = sin(lat_diff / 2) ** 2 + cos(lat1 * 3.14159 / 180) * cos(lat2 * 3.14159 / 180) * sin(lng_diff / 2) ** 2

        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    async def _select_performance_region(self, regions: dict[str, Region]) -> str:
        """Select region based on performance metrics"""

        # Calculate performance score for each region
        region_scores = {}

        for region_id, region in regions.items():
            # Performance score based on health, latency, and load
            health_score = region.health_score
            latency_score = max(0, 1 - (region.latency_ms / 1000))  # Normalize latency
            load_score = max(0, 1 - (region.current_load.get("requests", 0) / max(region.capacity.get("max_requests", 1), 1)))

            # Weighted score
            performance_score = health_score * 0.5 + latency_score * 0.3 + load_score * 0.2

            region_scores[region_id] = performance_score

        # Select best performing region
        best_region = max(region_scores, key=region_scores.get)

        return best_region

    async def _select_weighted_region(self, regions: dict[str, Region]) -> str:
        """Select region using weighted round robin"""

        # Calculate total weight
        total_weight = sum(self.region_weights.get(rid, 1.0) for rid in regions.keys())

        # Select region based on weights
        import random

        rand_value = random.uniform(0, total_weight)

        current_weight = 0
        for region_id in regions.keys():
            current_weight += self.region_weights.get(region_id, 1.0)
            if rand_value <= current_weight:
                return region_id

        # Fallback to first region
        return list(regions.keys())[0]

    async def _select_round_robin_region(self, regions: dict[str, Region]) -> str:
        """Select region using round robin"""

        # Simple round robin implementation
        region_ids = list(regions.keys())
        current_time = int(time.time())

        selected_index = current_time % len(region_ids)

        return region_ids[selected_index]

    async def update_region_health(self, region_id: str, health_score: float, latency_ms: float):
        """Update region health metrics"""

        if region_id in self.regions:
            region = self.regions[region_id]
            region.health_score = health_score
            region.latency_ms = latency_ms
            region.last_health_check = datetime.utcnow()

            # Update weights based on performance
            await self._update_region_weights(region_id, health_score, latency_ms)

    async def _update_region_weights(self, region_id: str, health_score: float, latency_ms: float):
        """Update region weights for load balancing"""

        # Calculate weight based on health and latency
        base_weight = 1.0
        health_multiplier = health_score
        latency_multiplier = max(0.1, 1 - (latency_ms / 1000))

        new_weight = base_weight * health_multiplier * latency_multiplier

        # Update weight with smoothing
        current_weight = self.region_weights.get(region_id, 1.0)
        smoothed_weight = current_weight * 0.8 + new_weight * 0.2

        self.region_weights[region_id] = smoothed_weight

    async def get_region_metrics(self) -> dict[str, Any]:
        """Get comprehensive region metrics"""

        metrics = {
            "total_regions": len(self.regions),
            "active_regions": len([r for r in self.regions.values() if r.status == RegionStatus.ACTIVE]),
            "average_health_score": 0.0,
            "average_latency": 0.0,
            "regions": {},
        }

        if self.regions:
            total_health = sum(r.health_score for r in self.regions.values())
            total_latency = sum(r.latency_ms for r in self.regions.values())

            metrics["average_health_score"] = total_health / len(self.regions)
            metrics["average_latency"] = total_latency / len(self.regions)

        for region_id, region in self.regions.items():
            metrics["regions"][region_id] = {
                "name": region.name,
                "code": region.code,
                "status": region.status.value,
                "health_score": region.health_score,
                "latency_ms": region.latency_ms,
                "current_load": region.current_load,
                "capacity": region.capacity,
                "weight": self.region_weights.get(region_id, 1.0),
            }

        return metrics


class DataResidencyManager:
    """Data residency compliance manager"""

    def __init__(self):
        self.residency_policies = {}
        self.data_location_map = {}
        self.transfer_logs = {}
        self.logger = get_logger("data_residency")

    async def set_residency_policy(
        self, data_type: str, residency_type: DataResidencyType, allowed_regions: list[str], restrictions: dict[str, Any]
    ):
        """Set data residency policy"""

        policy = {
            "data_type": data_type,
            "residency_type": residency_type,
            "allowed_regions": allowed_regions,
            "restrictions": restrictions,
            "created_at": datetime.utcnow(),
        }

        self.residency_policies[data_type] = policy

        self.logger.info(f"Data residency policy set: {data_type} - {residency_type.value}")

    async def check_data_transfer_allowed(self, data_type: str, source_region: str, destination_region: str) -> bool:
        """Check if data transfer is allowed under residency policies"""

        policy = self.residency_policies.get(data_type)
        if not policy:
            # Default to allowed if no policy exists
            return True

        residency_type = policy["residency_type"]
        allowed_regions = policy["allowed_regions"]
        policy["restrictions"]

        # Check residency type restrictions
        if residency_type == DataResidencyType.LOCAL:
            return source_region == destination_region
        elif residency_type == DataResidencyType.REGIONAL:
            # Check if both regions are in the same geographic area
            return self._regions_in_same_area(source_region, destination_region)
        elif residency_type == DataResidencyType.GLOBAL:
            return True
        elif residency_type == DataResidencyType.HYBRID:
            # Check hybrid policy rules
            return destination_region in allowed_regions

        return False

    def _regions_in_same_area(self, region1: str, region2: str) -> bool:
        """Check if two regions are in the same geographic area"""

        # Simplified geographic area mapping
        area_mapping = {
            "US": ["US", "CA"],
            "EU": ["GB", "DE", "FR", "IT", "ES", "NL", "BE", "AT", "CH", "SE", "NO", "DK", "FI"],
            "APAC": ["JP", "KR", "SG", "AU", "IN", "TH", "MY", "ID", "PH", "VN"],
            "LATAM": ["BR", "MX", "AR", "CL", "CO", "PE", "VE"],
        }

        for _area, regions in area_mapping.items():
            if region1 in regions and region2 in regions:
                return True

        return False

    async def log_data_transfer(
        self,
        transfer_id: str,
        data_type: str,
        source_region: str,
        destination_region: str,
        data_size: int,
        user_id: str | None = None,
    ):
        """Log data transfer for compliance"""

        transfer_log = {
            "transfer_id": transfer_id,
            "data_type": data_type,
            "source_region": source_region,
            "destination_region": destination_region,
            "data_size": data_size,
            "user_id": user_id,
            "timestamp": datetime.utcnow(),
            "compliant": await self.check_data_transfer_allowed(data_type, source_region, destination_region),
        }

        self.transfer_logs[transfer_id] = transfer_log

        self.logger.info(f"Data transfer logged: {transfer_id} - {source_region} -> {destination_region}")

    async def get_residency_report(self) -> dict[str, Any]:
        """Generate data residency compliance report"""

        total_transfers = len(self.transfer_logs)
        compliant_transfers = len([t for t in self.transfer_logs.values() if t.get("compliant", False)])

        compliance_rate = (compliant_transfers / total_transfers) if total_transfers > 0 else 1.0

        # Data distribution by region
        data_distribution = {}
        for transfer in self.transfer_logs.values():
            dest_region = transfer["destination_region"]
            data_distribution[dest_region] = data_distribution.get(dest_region, 0) + transfer["data_size"]

        return {
            "total_policies": len(self.residency_policies),
            "total_transfers": total_transfers,
            "compliant_transfers": compliant_transfers,
            "compliance_rate": compliance_rate,
            "data_distribution": data_distribution,
            "report_date": datetime.utcnow().isoformat(),
        }


class DisasterRecoveryManager:
    """Disaster recovery and failover management"""

    def __init__(self):
        self.failover_configs = {}
        self.failover_history = {}
        self.backup_status = {}
        self.recovery_time_objectives = {}
        self.logger = get_logger("disaster_recovery")

    async def configure_failover(self, config: FailoverConfig) -> bool:
        """Configure failover for primary region"""

        try:
            self.failover_configs[config.primary_region] = config

            # Initialize backup status
            for backup_region in config.backup_regions:
                self.backup_status[backup_region] = {
                    "primary_region": config.primary_region,
                    "status": "ready",
                    "last_sync": datetime.utcnow(),
                    "sync_health": 1.0,
                }

            self.logger.info(f"Failover configured: {config.primary_region}")
            return True

        except Exception as e:
            self.logger.error(f"Failover configuration failed: {e}")
            return False

    async def check_failover_needed(self, region_id: str, health_score: float) -> bool:
        """Check if failover is needed for region"""

        config = self.failover_configs.get(region_id)
        if not config:
            return False

        # Check if auto-failover is enabled
        if not config.auto_failover:
            return False

        # Check health threshold
        if health_score >= config.failover_threshold:
            return False

        # Check if failover is already in progress
        failover_id = f"{region_id}_{int(time.time())}"
        if failover_id in self.failover_history:
            return False

        return True

    async def initiate_failover(self, region_id: str, reason: str) -> str:
        """Initiate failover process"""

        config = self.failover_configs.get(region_id)
        if not config:
            raise ValueError(f"No failover configuration for region: {region_id}")

        failover_id = str(uuid4())

        failover_record = {
            "failover_id": failover_id,
            "primary_region": region_id,
            "backup_regions": config.backup_regions,
            "reason": reason,
            "initiated_at": datetime.utcnow(),
            "status": "initiated",
            "completed_at": None,
            "success": None,
        }

        self.failover_history[failover_id] = failover_record

        # Start failover process
        asyncio.create_task(self._execute_failover(failover_id, config))

        self.logger.warning(f"Failover initiated: {failover_id} - {region_id}")

        return failover_id

    async def _execute_failover(self, failover_id: str, config: FailoverConfig):
        """Execute failover process"""

        try:
            failover_record = self.failover_history[failover_id]
            failover_record["status"] = "in_progress"

            # Select best backup region
            best_backup = await self._select_best_backup_region(config.backup_regions)

            if not best_backup:
                failover_record["status"] = "failed"
                failover_record["success"] = False
                failover_record["completed_at"] = datetime.utcnow()
                return

            # Perform data sync if required
            if config.data_sync:
                sync_success = await self._sync_data_to_backup(config.primary_region, best_backup)
                if not sync_success:
                    failover_record["status"] = "failed"
                    failover_record["success"] = False
                    failover_record["completed_at"] = datetime.utcnow()
                    return

            # Update DNS/routing to point to backup
            routing_success = await self._update_routing(best_backup)
            if not routing_success:
                failover_record["status"] = "failed"
                failover_record["success"] = False
                failover_record["completed_at"] = datetime.utcnow()
                return

            # Mark failover as successful
            failover_record["status"] = "completed"
            failover_record["success"] = True
            failover_record["completed_at"] = datetime.utcnow()
            failover_record["active_region"] = best_backup

            self.logger.info(f"Failover completed successfully: {failover_id}")

        except Exception as e:
            self.logger.error(f"Failover execution failed: {e}")
            failover_record = self.failover_history[failover_id]
            failover_record["status"] = "failed"
            failover_record["success"] = False
            failover_record["completed_at"] = datetime.utcnow()

    async def _select_best_backup_region(self, backup_regions: list[str]) -> str | None:
        """Select best backup region for failover"""

        # In production, use actual health metrics
        # For now, return first available region
        return backup_regions[0] if backup_regions else None

    async def _sync_data_to_backup(self, primary_region: str, backup_region: str) -> bool:
        """Sync data to backup region"""

        try:
            # Simulate data sync
            await asyncio.sleep(2)  # Simulate sync time

            # Update backup status
            if backup_region in self.backup_status:
                self.backup_status[backup_region]["last_sync"] = datetime.utcnow()
                self.backup_status[backup_region]["sync_health"] = 1.0

            self.logger.info(f"Data sync completed: {primary_region} -> {backup_region}")
            return True

        except Exception as e:
            self.logger.error(f"Data sync failed: {e}")
            return False

    async def _update_routing(self, new_primary_region: str) -> bool:
        """Update DNS/routing to point to new primary region"""

        try:
            # Simulate routing update
            await asyncio.sleep(1)

            self.logger.info(f"Routing updated to: {new_primary_region}")
            return True

        except Exception as e:
            self.logger.error(f"Routing update failed: {e}")
            return False

    async def get_failover_status(self, region_id: str) -> dict[str, Any]:
        """Get failover status for region"""

        config = self.failover_configs.get(region_id)
        if not config:
            return {"error": f"No failover configuration for region: {region_id}"}

        # Get recent failovers
        recent_failovers = [
            f
            for f in self.failover_history.values()
            if f["primary_region"] == region_id and f["initiated_at"] > datetime.utcnow() - timedelta(days=7)
        ]

        return {
            "primary_region": region_id,
            "backup_regions": config.backup_regions,
            "auto_failover": config.auto_failover,
            "failover_threshold": config.failover_threshold,
            "recent_failovers": len(recent_failovers),
            "last_failover": recent_failovers[-1] if recent_failovers else None,
            "backup_status": {
                region: status for region, status in self.backup_status.items() if status["primary_region"] == region_id
            },
        }


class MultiRegionDeploymentManager:
    """Main multi-region deployment manager"""

    def __init__(self):
        self.load_balancer = GeographicLoadBalancer()
        self.data_residency = DataResidencyManager()
        self.disaster_recovery = DisasterRecoveryManager()
        self.regions = {}
        self.deployment_configs = {}
        self.logger = get_logger("multi_region_manager")

    async def initialize(self) -> bool:
        """Initialize multi-region deployment manager"""

        try:
            # Set up default regions
            await self._setup_default_regions()

            # Set up default data residency policies
            await self._setup_default_residency_policies()

            # Set up default failover configurations
            await self._setup_default_failover_configs()

            self.logger.info("Multi-region deployment manager initialized")
            return True

        except Exception as e:
            self.logger.error(f"Multi-region manager initialization failed: {e}")
            return False

    async def _setup_default_regions(self):
        """Set up default geographic regions"""

        default_regions = [
            Region(
                region_id="us_east",
                name="US East",
                code="US",
                location={"latitude": 40.7128, "longitude": -74.0060},
                endpoints=["https://api.aitbc.dev/us-east"],
                data_residency=DataResidencyType.REGIONAL,
                compliance_requirements=["GDPR", "CCPA", "SOC2"],
                capacity={"max_users": 100000, "max_requests": 1000000, "max_storage": 10000},
            ),
            Region(
                region_id="eu_west",
                name="EU West",
                code="GB",
                location={"latitude": 51.5074, "longitude": -0.1278},
                endpoints=["https://api.aitbc.dev/eu-west"],
                data_residency=DataResidencyType.LOCAL,
                compliance_requirements=["GDPR", "SOC2"],
                capacity={"max_users": 80000, "max_requests": 800000, "max_storage": 8000},
            ),
            Region(
                region_id="ap_southeast",
                name="AP Southeast",
                code="SG",
                location={"latitude": 1.3521, "longitude": 103.8198},
                endpoints=["https://api.aitbc.dev/ap-southeast"],
                data_residency=DataResidencyType.REGIONAL,
                compliance_requirements=["SOC2"],
                capacity={"max_users": 60000, "max_requests": 600000, "max_storage": 6000},
            ),
        ]

        for region in default_regions:
            await self.load_balancer.add_region(region)
            self.regions[region.region_id] = region

    async def _setup_default_residency_policies(self):
        """Set up default data residency policies"""

        policies = [
            ("personal_data", DataResidencyType.REGIONAL, ["US", "GB", "SG"], {}),
            ("financial_data", DataResidencyType.LOCAL, ["US", "GB", "SG"], {"encryption_required": True}),
            (
                "health_data",
                DataResidencyType.LOCAL,
                ["US", "GB", "SG"],
                {"encryption_required": True, "anonymization_required": True},
            ),
            ("public_data", DataResidencyType.GLOBAL, ["US", "GB", "SG"], {}),
        ]

        for data_type, residency_type, allowed_regions, restrictions in policies:
            await self.data_residency.set_residency_policy(data_type, residency_type, allowed_regions, restrictions)

    async def _setup_default_failover_configs(self):
        """Set up default failover configurations"""

        # US East failover to EU West and AP Southeast
        us_failover = FailoverConfig(
            primary_region="us_east",
            backup_regions=["eu_west", "ap_southeast"],
            failover_threshold=0.5,
            failover_timeout=timedelta(minutes=5),
            auto_failover=True,
            data_sync=True,
        )

        await self.disaster_recovery.configure_failover(us_failover)

        # EU West failover to US East
        eu_failover = FailoverConfig(
            primary_region="eu_west",
            backup_regions=["us_east"],
            failover_threshold=0.5,
            failover_timeout=timedelta(minutes=5),
            auto_failover=True,
            data_sync=True,
        )

        await self.disaster_recovery.configure_failover(eu_failover)

    async def handle_user_request(
        self, user_location: dict[str, float] | None = None, user_preferences: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle user request with multi-region routing"""

        try:
            # Select optimal region
            selected_region = await self.load_balancer.select_region(user_location, user_preferences)

            if not selected_region:
                return {"error": "No available regions"}

            # Update region load
            region = self.regions.get(selected_region)
            if region:
                region.current_load["requests"] = region.current_load.get("requests", 0) + 1

            # Check for failover need
            if await self.disaster_recovery.check_failover_needed(selected_region, region.health_score):
                failover_id = await self.disaster_recovery.initiate_failover(selected_region, "Health score below threshold")

                return {"region": selected_region, "status": "failover_initiated", "failover_id": failover_id}

            return {
                "region": selected_region,
                "status": "active",
                "endpoints": region.endpoints,
                "health_score": region.health_score,
                "latency_ms": region.latency_ms,
            }

        except Exception as e:
            self.logger.error(f"Request handling failed: {e}")
            return {"error": str(e)}

    async def get_deployment_status(self) -> dict[str, Any]:
        """Get comprehensive deployment status"""

        try:
            # Get load balancer metrics
            lb_metrics = await self.load_balancer.get_region_metrics()

            # Get data residency report
            residency_report = await self.data_residency.get_residency_report()

            # Get failover status for all regions
            failover_status = {}
            for region_id in self.regions.keys():
                failover_status[region_id] = await self.disaster_recovery.get_failover_status(region_id)

            return {
                "total_regions": len(self.regions),
                "active_regions": lb_metrics["active_regions"],
                "average_health_score": lb_metrics["average_health_score"],
                "average_latency": lb_metrics["average_latency"],
                "load_balancer_metrics": lb_metrics,
                "data_residency": residency_report,
                "failover_status": failover_status,
                "status": "healthy" if lb_metrics["average_health_score"] >= 0.8 else "degraded",
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Status retrieval failed: {e}")
            return {"error": str(e)}

    async def update_region_health(self, region_id: str, health_metrics: dict[str, Any]):
        """Update region health metrics"""

        health_score = health_metrics.get("health_score", 1.0)
        latency_ms = health_metrics.get("latency_ms", 0.0)
        current_load = health_metrics.get("current_load", {})

        # Update load balancer
        await self.load_balancer.update_region_health(region_id, health_score, latency_ms)

        # Update region
        if region_id in self.regions:
            region = self.regions[region_id]
            region.health_score = health_score
            region.latency_ms = latency_ms
            region.current_load.update(current_load)

        # Check for failover need
        if await self.disaster_recovery.check_failover_needed(region_id, health_score):
            await self.disaster_recovery.initiate_failover(region_id, "Health score degradation detected")


# Global multi-region manager instance
multi_region_manager = None


async def get_multi_region_manager() -> MultiRegionDeploymentManager:
    """Get or create global multi-region manager"""

    global multi_region_manager
    if multi_region_manager is None:
        multi_region_manager = MultiRegionDeploymentManager()
        await multi_region_manager.initialize()

    return multi_region_manager
