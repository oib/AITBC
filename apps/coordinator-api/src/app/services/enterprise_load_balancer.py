"""
Advanced Load Balancing - Phase 6.4 Implementation
Intelligent traffic distribution with AI-powered auto-scaling and performance optimization
"""

import statistics
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from enum import StrEnum
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)


class LoadBalancingAlgorithm(StrEnum):
    """Load balancing algorithms"""

    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    LEAST_RESPONSE_TIME = "least_response_time"
    RESOURCE_BASED = "resource_based"
    PREDICTIVE_AI = "predictive_ai"
    ADAPTIVE = "adaptive"


class ScalingPolicy(StrEnum):
    """Auto-scaling policies"""

    MANUAL = "manual"
    THRESHOLD_BASED = "threshold_based"
    PREDICTIVE = "predictive"
    HYBRID = "hybrid"


class HealthStatus(StrEnum):
    """Health status"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    MAINTENANCE = "maintenance"


@dataclass
class BackendServer:
    """Backend server configuration"""

    server_id: str
    host: str
    port: int
    weight: float = 1.0
    max_connections: int = 1000
    current_connections: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    response_time_ms: float = 0.0
    request_count: int = 0
    error_count: int = 0
    health_status: HealthStatus = HealthStatus.HEALTHY
    last_health_check: datetime = field(default_factory=datetime.now(datetime.UTC))
    capabilities: dict[str, Any] = field(default_factory=dict)
    region: str = "default"
    created_at: datetime = field(default_factory=datetime.now(datetime.UTC))


@dataclass
class ScalingMetric:
    """Scaling metric configuration"""

    metric_name: str
    threshold_min: float
    threshold_max: float
    scaling_factor: float
    cooldown_period: timedelta
    measurement_window: timedelta


@dataclass
class TrafficPattern:
    """Traffic pattern for predictive scaling"""

    pattern_id: str
    name: str
    time_windows: list[dict[str, Any]]  # List of time windows with expected load
    day_of_week: int  # 0-6 (Monday-Sunday)
    seasonal_factor: float = 1.0
    confidence_score: float = 0.0


class PredictiveScaler:
    """AI-powered predictive auto-scaling"""

    def __init__(self):
        self.traffic_history = []
        self.scaling_predictions = {}
        self.traffic_patterns = {}
        self.model_weights = {}
        self.logger = get_logger("predictive_scaler")

    async def record_traffic(self, timestamp: datetime, request_count: int, response_time_ms: float, error_rate: float):
        """Record traffic metrics"""

        traffic_record = {
            "timestamp": timestamp,
            "request_count": request_count,
            "response_time_ms": response_time_ms,
            "error_rate": error_rate,
            "hour": timestamp.hour,
            "day_of_week": timestamp.weekday(),
            "day_of_month": timestamp.day,
            "month": timestamp.month,
        }

        self.traffic_history.append(traffic_record)

        # Keep only last 30 days of history
        cutoff = datetime.now(datetime.UTC) - timedelta(days=30)
        self.traffic_history = [record for record in self.traffic_history if record["timestamp"] > cutoff]

        # Update traffic patterns
        await self._update_traffic_patterns()

    async def _update_traffic_patterns(self):
        """Update traffic patterns based on historical data"""

        if len(self.traffic_history) < 168:  # Need at least 1 week of data
            return

        # Group by hour and day of week
        patterns = {}

        for record in self.traffic_history:
            key = f"{record['day_of_week']}_{record['hour']}"

            if key not in patterns:
                patterns[key] = {"request_counts": [], "response_times": [], "error_rates": []}

            patterns[key]["request_counts"].append(record["request_count"])
            patterns[key]["response_times"].append(record["response_time_ms"])
            patterns[key]["error_rates"].append(record["error_rate"])

        # Calculate pattern statistics
        for key, data in patterns.items():
            day_of_week, hour = key.split("_")

            pattern = TrafficPattern(
                pattern_id=key,
                name=f"Pattern Day {day_of_week} Hour {hour}",
                time_windows=[
                    {
                        "hour": int(hour),
                        "avg_requests": statistics.mean(data["request_counts"]),
                        "max_requests": max(data["request_counts"]),
                        "min_requests": min(data["request_counts"]),
                        "std_requests": statistics.stdev(data["request_counts"]) if len(data["request_counts"]) > 1 else 0,
                        "avg_response_time": statistics.mean(data["response_times"]),
                        "avg_error_rate": statistics.mean(data["error_rates"]),
                    }
                ],
                day_of_week=int(day_of_week),
                confidence_score=min(len(data["request_counts"]) / 100, 1.0),  # Confidence based on data points
            )

            self.traffic_patterns[key] = pattern

    async def predict_traffic(self, prediction_window: timedelta = timedelta(hours=1)) -> dict[str, Any]:
        """Predict traffic for the next time window"""

        try:
            current_time = datetime.now(datetime.UTC)
            current_time + prediction_window

            # Get current pattern
            current_pattern_key = f"{current_time.weekday()}_{current_time.hour}"
            current_pattern = self.traffic_patterns.get(current_pattern_key)

            if not current_pattern:
                # Fallback to simple prediction
                return await self._simple_prediction(prediction_window)

            # Get historical data for similar time periods
            similar_patterns = [
                pattern
                for pattern in self.traffic_patterns.values()
                if pattern.day_of_week == current_time.weekday()
                and abs(pattern.time_windows[0]["hour"] - current_time.hour) <= 2
            ]

            if not similar_patterns:
                return await self._simple_prediction(prediction_window)

            # Calculate weighted prediction
            total_weight = 0
            weighted_requests = 0
            weighted_response_time = 0
            weighted_error_rate = 0

            for pattern in similar_patterns:
                weight = pattern.confidence_score
                window_data = pattern.time_windows[0]

                weighted_requests += window_data["avg_requests"] * weight
                weighted_response_time += window_data["avg_response_time"] * weight
                weighted_error_rate += window_data["avg_error_rate"] * weight
                total_weight += weight

            if total_weight > 0:
                predicted_requests = weighted_requests / total_weight
                predicted_response_time = weighted_response_time / total_weight
                predicted_error_rate = weighted_error_rate / total_weight
            else:
                return await self._simple_prediction(prediction_window)

            # Apply seasonal factors
            seasonal_factor = self._get_seasonal_factor(current_time)
            predicted_requests *= seasonal_factor

            return {
                "prediction_window_hours": prediction_window.total_seconds() / 3600,
                "predicted_requests_per_hour": int(predicted_requests),
                "predicted_response_time_ms": predicted_response_time,
                "predicted_error_rate": predicted_error_rate,
                "confidence_score": min(total_weight / len(similar_patterns), 1.0),
                "seasonal_factor": seasonal_factor,
                "pattern_based": True,
                "prediction_timestamp": current_time.isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Traffic prediction failed: {e}")
            return await self._simple_prediction(prediction_window)

    async def _simple_prediction(self, prediction_window: timedelta) -> dict[str, Any]:
        """Simple prediction based on recent averages"""

        if not self.traffic_history:
            return {
                "prediction_window_hours": prediction_window.total_seconds() / 3600,
                "predicted_requests_per_hour": 1000,  # Default
                "predicted_response_time_ms": 100.0,
                "predicted_error_rate": 0.01,
                "confidence_score": 0.1,
                "pattern_based": False,
                "prediction_timestamp": datetime.now(datetime.UTC).isoformat(),
            }

        # Calculate recent averages
        recent_records = self.traffic_history[-24:]  # Last 24 records

        avg_requests = statistics.mean([r["request_count"] for r in recent_records])
        avg_response_time = statistics.mean([r["response_time_ms"] for r in recent_records])
        avg_error_rate = statistics.mean([r["error_rate"] for r in recent_records])

        return {
            "prediction_window_hours": prediction_window.total_seconds() / 3600,
            "predicted_requests_per_hour": int(avg_requests),
            "predicted_response_time_ms": avg_response_time,
            "predicted_error_rate": avg_error_rate,
            "confidence_score": 0.3,
            "pattern_based": False,
            "prediction_timestamp": datetime.now(datetime.UTC).isoformat(),
        }

    def _get_seasonal_factor(self, timestamp: datetime) -> float:
        """Get seasonal adjustment factor"""

        # Simple seasonal factors (can be enhanced with more sophisticated models)
        month = timestamp.month

        seasonal_factors = {
            1: 0.8,  # January - post-holiday dip
            2: 0.9,  # February
            3: 1.0,  # March
            4: 1.1,  # April - spring increase
            5: 1.2,  # May
            6: 1.1,  # June
            7: 1.0,  # July - summer
            8: 0.9,  # August
            9: 1.1,  # September - back to business
            10: 1.2,  # October
            11: 1.3,  # November - holiday season start
            12: 1.4,  # December - peak holiday season
        }

        return seasonal_factors.get(month, 1.0)

    async def get_scaling_recommendation(self, current_servers: int, current_capacity: int) -> dict[str, Any]:
        """Get scaling recommendation based on predictions"""

        try:
            # Get traffic prediction
            prediction = await self.predict_traffic(timedelta(hours=1))

            predicted_requests = prediction["predicted_requests_per_hour"]
            current_capacity_per_server = current_capacity // max(current_servers, 1)

            # Calculate required servers
            required_servers = max(1, int(predicted_requests / current_capacity_per_server))

            # Apply buffer (20% extra capacity)
            required_servers = int(required_servers * 1.2)

            scaling_action = "none"
            if required_servers > current_servers:
                scaling_action = "scale_up"
                scale_to = required_servers
            elif required_servers < current_servers * 0.7:  # Scale down if underutilized
                scaling_action = "scale_down"
                scale_to = max(1, required_servers)
            else:
                scale_to = current_servers

            return {
                "current_servers": current_servers,
                "recommended_servers": scale_to,
                "scaling_action": scaling_action,
                "predicted_load": predicted_requests,
                "current_capacity_per_server": current_capacity_per_server,
                "confidence_score": prediction["confidence_score"],
                "reason": f"Predicted {predicted_requests} requests/hour vs current capacity {current_servers * current_capacity_per_server}",
                "recommendation_timestamp": datetime.now(datetime.UTC).isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Scaling recommendation failed: {e}")
            return {
                "scaling_action": "none",
                "reason": f"Prediction failed: {str(e)}",
                "recommendation_timestamp": datetime.now(datetime.UTC).isoformat(),
            }


class AdvancedLoadBalancer:
    """Advanced load balancer with multiple algorithms and AI optimization"""

    def __init__(self):
        self.backends = {}
        self.algorithm = LoadBalancingAlgorithm.ADAPTIVE
        self.current_index = 0
        self.request_history = []
        self.performance_metrics = {}
        self.predictive_scaler = PredictiveScaler()
        self.scaling_metrics = {}
        self.logger = get_logger("advanced_load_balancer")

    async def add_backend(self, server: BackendServer) -> bool:
        """Add backend server"""

        try:
            self.backends[server.server_id] = server

            # Initialize performance metrics
            self.performance_metrics[server.server_id] = {
                "avg_response_time": 0.0,
                "error_rate": 0.0,
                "throughput": 0.0,
                "uptime": 1.0,
                "last_updated": datetime.now(datetime.UTC),
            }

            self.logger.info(f"Backend server added: {server.server_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add backend server: {e}")
            return False

    async def remove_backend(self, server_id: str) -> bool:
        """Remove backend server"""

        if server_id in self.backends:
            del self.backends[server_id]
            del self.performance_metrics[server_id]

            self.logger.info(f"Backend server removed: {server_id}")
            return True

        return False

    async def select_backend(self, request_context: dict[str, Any] | None = None) -> str | None:
        """Select backend server based on algorithm"""

        try:
            # Filter healthy backends
            healthy_backends = {
                sid: server for sid, server in self.backends.items() if server.health_status == HealthStatus.HEALTHY
            }

            if not healthy_backends:
                return None

            # Select backend based on algorithm
            if self.algorithm == LoadBalancingAlgorithm.ROUND_ROBIN:
                return await self._select_round_robin(healthy_backends)
            elif self.algorithm == LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN:
                return await self._select_weighted_round_robin(healthy_backends)
            elif self.algorithm == LoadBalancingAlgorithm.LEAST_CONNECTIONS:
                return await self._select_least_connections(healthy_backends)
            elif self.algorithm == LoadBalancingAlgorithm.LEAST_RESPONSE_TIME:
                return await self._select_least_response_time(healthy_backends)
            elif self.algorithm == LoadBalancingAlgorithm.RESOURCE_BASED:
                return await self._select_resource_based(healthy_backends)
            elif self.algorithm == LoadBalancingAlgorithm.PREDICTIVE_AI:
                return await self._select_predictive_ai(healthy_backends, request_context)
            elif self.algorithm == LoadBalancingAlgorithm.ADAPTIVE:
                return await self._select_adaptive(healthy_backends, request_context)
            else:
                return await self._select_round_robin(healthy_backends)

        except Exception as e:
            self.logger.error(f"Backend selection failed: {e}")
            return None

    async def _select_round_robin(self, backends: dict[str, BackendServer]) -> str:
        """Round robin selection"""

        backend_ids = list(backends.keys())

        if not backend_ids:
            return None

        selected = backend_ids[self.current_index % len(backend_ids)]
        self.current_index += 1

        return selected

    async def _select_weighted_round_robin(self, backends: dict[str, BackendServer]) -> str:
        """Weighted round robin selection"""

        # Calculate total weight
        total_weight = sum(server.weight for server in backends.values())

        if total_weight <= 0:
            return await self._select_round_robin(backends)

        # Select based on weights
        import random

        rand_value = random.uniform(0, total_weight)

        current_weight = 0
        for server_id, server in backends.items():
            current_weight += server.weight
            if rand_value <= current_weight:
                return server_id

        # Fallback
        return list(backends.keys())[0]

    async def _select_least_connections(self, backends: dict[str, BackendServer]) -> str:
        """Select backend with least connections"""

        min_connections = float("inf")
        selected_backend = None

        for server_id, server in backends.items():
            if server.current_connections < min_connections:
                min_connections = server.current_connections
                selected_backend = server_id

        return selected_backend

    async def _select_least_response_time(self, backends: dict[str, BackendServer]) -> str:
        """Select backend with least response time"""

        min_response_time = float("inf")
        selected_backend = None

        for server_id, server in backends.items():
            if server.response_time_ms < min_response_time:
                min_response_time = server.response_time_ms
                selected_backend = server_id

        return selected_backend

    async def _select_resource_based(self, backends: dict[str, BackendServer]) -> str:
        """Select backend based on resource utilization"""

        best_score = -1
        selected_backend = None

        for server_id, server in backends.items():
            # Calculate resource score (lower is better)
            cpu_score = 1.0 - (server.cpu_usage / 100.0)
            memory_score = 1.0 - (server.memory_usage / 100.0)
            connection_score = 1.0 - (server.current_connections / server.max_connections)

            # Weighted score
            resource_score = cpu_score * 0.4 + memory_score * 0.3 + connection_score * 0.3

            if resource_score > best_score:
                best_score = resource_score
                selected_backend = server_id

        return selected_backend

    async def _select_predictive_ai(
        self, backends: dict[str, BackendServer], request_context: dict[str, Any] | None
    ) -> str:
        """AI-powered predictive selection"""

        # Get performance predictions for each backend
        backend_scores = {}

        for server_id, server in backends.items():
            # Predict performance based on historical data
            self.performance_metrics.get(server_id, {})

            # Calculate predicted response time
            predicted_response_time = (
                server.response_time_ms
                * (1 + server.cpu_usage / 100)
                * (1 + server.memory_usage / 100)
                * (1 + server.current_connections / server.max_connections)
            )

            # Calculate score (lower response time is better)
            score = 1.0 / (1.0 + predicted_response_time / 100.0)

            # Apply context-based adjustments
            if request_context:
                # Consider request type, user location, etc.
                context_multiplier = await self._calculate_context_multiplier(server, request_context)
                score *= context_multiplier

            backend_scores[server_id] = score

        # Select best scoring backend
        if backend_scores:
            return max(backend_scores, key=backend_scores.get)

        return await self._select_least_connections(backends)

    async def _select_adaptive(self, backends: dict[str, BackendServer], request_context: dict[str, Any] | None) -> str:
        """Adaptive selection based on current conditions"""

        # Analyze current system state
        total_connections = sum(server.current_connections for server in backends.values())
        avg_response_time = statistics.mean([server.response_time_ms for server in backends.values()])

        # Choose algorithm based on conditions
        if total_connections > sum(server.max_connections for server in backends.values()) * 0.8:
            # High load - use resource-based
            return await self._select_resource_based(backends)
        elif avg_response_time > 200:
            # High latency - use least response time
            return await self._select_least_response_time(backends)
        else:
            # Normal conditions - use weighted round robin
            return await self._select_weighted_round_robin(backends)

    async def _calculate_context_multiplier(self, server: BackendServer, request_context: dict[str, Any]) -> float:
        """Calculate context-based multiplier for backend selection"""

        multiplier = 1.0

        # Consider geographic location
        if "user_location" in request_context and "region" in server.capabilities:
            user_region = request_context["user_location"].get("region")
            server_region = server.capabilities["region"]

            if user_region == server_region:
                multiplier *= 1.2  # Prefer same region
            elif self._regions_in_same_continent(user_region, server_region):
                multiplier *= 1.1  # Slight preference for same continent

        # Consider request type
        request_type = request_context.get("request_type", "general")
        server_specializations = server.capabilities.get("specializations", [])

        if request_type in server_specializations:
            multiplier *= 1.3  # Strong preference for specialized backends

        # Consider user tier
        user_tier = request_context.get("user_tier", "standard")
        if user_tier == "premium" and server.capabilities.get("premium_support", False):
            multiplier *= 1.15

        return multiplier

    def _regions_in_same_continent(self, region1: str, region2: str) -> bool:
        """Check if two regions are in the same continent"""

        continent_mapping = {
            "NA": ["US", "CA", "MX"],
            "EU": ["GB", "DE", "FR", "IT", "ES", "NL", "BE", "AT", "CH", "SE", "NO", "DK", "FI"],
            "APAC": ["JP", "KR", "SG", "AU", "IN", "TH", "MY", "ID", "PH", "VN"],
            "LATAM": ["BR", "MX", "AR", "CL", "CO", "PE", "VE"],
        }

        for _continent, regions in continent_mapping.items():
            if region1 in regions and region2 in regions:
                return True

        return False

    async def record_request(
        self, server_id: str, response_time_ms: float, success: bool, timestamp: datetime | None = None
    ):
        """Record request metrics"""

        if timestamp is None:
            timestamp = datetime.now(datetime.UTC)

        # Update backend server metrics
        if server_id in self.backends:
            server = self.backends[server_id]
            server.request_count += 1
            server.response_time_ms = server.response_time_ms * 0.9 + response_time_ms * 0.1  # EMA

            if not success:
                server.error_count += 1

        # Record in history
        request_record = {
            "timestamp": timestamp,
            "server_id": server_id,
            "response_time_ms": response_time_ms,
            "success": success,
        }

        self.request_history.append(request_record)

        # Keep only last 10000 records
        if len(self.request_history) > 10000:
            self.request_history = self.request_history[-10000:]

        # Update predictive scaler
        await self.predictive_scaler.record_traffic(
            timestamp, 1, response_time_ms, 0.0 if success else 1.0  # One request  # Error rate
        )

    async def update_backend_health(
        self, server_id: str, health_status: HealthStatus, cpu_usage: float, memory_usage: float, current_connections: int
    ):
        """Update backend health metrics"""

        if server_id in self.backends:
            server = self.backends[server_id]
            server.health_status = health_status
            server.cpu_usage = cpu_usage
            server.memory_usage = memory_usage
            server.current_connections = current_connections
            server.last_health_check = datetime.now(datetime.UTC)

    async def get_load_balancing_metrics(self) -> dict[str, Any]:
        """Get comprehensive load balancing metrics"""

        try:
            total_requests = sum(server.request_count for server in self.backends.values())
            total_errors = sum(server.error_count for server in self.backends.values())
            total_connections = sum(server.current_connections for server in self.backends.values())

            error_rate = (total_errors / total_requests) if total_requests > 0 else 0.0

            # Calculate average response time
            avg_response_time = 0.0
            if self.backends:
                avg_response_time = statistics.mean([server.response_time_ms for server in self.backends.values()])

            # Backend distribution
            backend_distribution = {}
            for server_id, server in self.backends.items():
                backend_distribution[server_id] = {
                    "requests": server.request_count,
                    "errors": server.error_count,
                    "connections": server.current_connections,
                    "response_time_ms": server.response_time_ms,
                    "cpu_usage": server.cpu_usage,
                    "memory_usage": server.memory_usage,
                    "health_status": server.health_status.value,
                    "weight": server.weight,
                }

            # Get scaling recommendation
            scaling_recommendation = await self.predictive_scaler.get_scaling_recommendation(
                len(self.backends), sum(server.max_connections for server in self.backends.values())
            )

            return {
                "total_backends": len(self.backends),
                "healthy_backends": len([s for s in self.backends.values() if s.health_status == HealthStatus.HEALTHY]),
                "total_requests": total_requests,
                "total_errors": total_errors,
                "error_rate": error_rate,
                "average_response_time_ms": avg_response_time,
                "total_connections": total_connections,
                "algorithm": self.algorithm.value,
                "backend_distribution": backend_distribution,
                "scaling_recommendation": scaling_recommendation,
                "timestamp": datetime.now(datetime.UTC).isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Metrics retrieval failed: {e}")
            return {"error": str(e)}

    async def set_algorithm(self, algorithm: LoadBalancingAlgorithm):
        """Set load balancing algorithm"""

        self.algorithm = algorithm
        self.logger.info(f"Load balancing algorithm changed to: {algorithm.value}")

    async def auto_scale(self, min_servers: int = 1, max_servers: int = 10) -> dict[str, Any]:
        """Perform auto-scaling based on predictions"""

        try:
            # Get scaling recommendation
            recommendation = await self.predictive_scaler.get_scaling_recommendation(
                len(self.backends), sum(server.max_connections for server in self.backends.values())
            )

            action = recommendation["scaling_action"]
            target_servers = recommendation["recommended_servers"]

            # Apply scaling limits
            target_servers = max(min_servers, min(max_servers, target_servers))

            scaling_result = {
                "action": action,
                "current_servers": len(self.backends),
                "target_servers": target_servers,
                "confidence": recommendation.get("confidence_score", 0.0),
                "reason": recommendation.get("reason", ""),
                "timestamp": datetime.now(datetime.UTC).isoformat(),
            }

            # In production, implement actual scaling logic here
            # For now, just return the recommendation

            self.logger.info(f"Auto-scaling recommendation: {action} to {target_servers} servers")

            return scaling_result

        except Exception as e:
            self.logger.error(f"Auto-scaling failed: {e}")
            return {"error": str(e)}


# Global load balancer instance
advanced_load_balancer = None


async def get_advanced_load_balancer() -> AdvancedLoadBalancer:
    """Get or create global advanced load balancer"""

    global advanced_load_balancer
    if advanced_load_balancer is None:
        advanced_load_balancer = AdvancedLoadBalancer()

        # Add default backends
        default_backends = [
            BackendServer(
                server_id="backend_1", host="10.0.1.10", port=8080, weight=1.0, max_connections=1000, region="us_east"
            ),
            BackendServer(
                server_id="backend_2", host="10.0.1.11", port=8080, weight=1.0, max_connections=1000, region="us_east"
            ),
            BackendServer(
                server_id="backend_3", host="10.0.1.12", port=8080, weight=0.8, max_connections=800, region="eu_west"
            ),
        ]

        for backend in default_backends:
            await advanced_load_balancer.add_backend(backend)

    return advanced_load_balancer
