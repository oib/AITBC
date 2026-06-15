"""
Agent Discovery and Registration System for AITBC Agent Coordination
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

redis_client: Any = None
try:
    import redis.asyncio as redis

    redis_client = redis
except ImportError:
    pass
from aitbc import get_logger

from ..protocols.communication import AgentMessage, MessageType
from ..protocols.message_types import DiscoveryMessage

logger = get_logger(__name__)


class AgentStatus(StrEnum):
    """Agent status enumeration"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    BUSY = "busy"
    MAINTENANCE = "maintenance"
    ERROR = "error"


class AgentType(StrEnum):
    """Agent type enumeration"""

    COORDINATOR = "coordinator"
    WORKER = "worker"
    SPECIALIST = "specialist"
    MONITOR = "monitor"
    GATEWAY = "gateway"
    ORCHESTRATOR = "orchestrator"


@dataclass
class AgentInfo:
    """Agent information structure"""

    agent_id: str
    agent_type: AgentType
    status: AgentStatus
    capabilities: list[str]
    services: list[str]
    endpoints: dict[str, str]
    metadata: dict[str, Any]
    last_heartbeat: datetime
    registration_time: datetime
    load_metrics: dict[str, float] = field(default_factory=dict)
    health_score: float = 1.0
    version: str = "1.0.0"
    tags: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "services": self.services,
            "endpoints": self.endpoints,
            "metadata": self.metadata,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "registration_time": self.registration_time.isoformat(),
            "load_metrics": self.load_metrics,
            "health_score": self.health_score,
            "version": self.version,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentInfo:
        """Create from dictionary"""
        data["agent_type"] = AgentType(data["agent_type"])
        data["status"] = AgentStatus(data["status"])
        data["last_heartbeat"] = datetime.fromisoformat(data["last_heartbeat"])
        data["registration_time"] = datetime.fromisoformat(data["registration_time"])
        data["tags"] = set(data.get("tags", []))
        return cls(**data)


class AgentRegistry:
    """Central agent registry for discovery and management"""

    def __init__(self, redis_url: str = "redis://localhost:6379/1") -> None:
        self.redis_url = redis_url
        self.redis_client: Any = None
        self.agents: dict[str, AgentInfo] = {}
        self.service_index: dict[str, set[str]] = {}
        self.capability_index: dict[str, set[str]] = {}
        self.type_index: dict[AgentType, set[str]] = {}
        self.heartbeat_interval = 30
        self.cleanup_interval = 60
        self.max_heartbeat_age = 120

    async def start(self) -> None:
        """Start the registry service"""
        self.redis_client = redis_client.from_url(self.redis_url)
        await self._load_agents_from_redis()
        asyncio.create_task(self._heartbeat_monitor())
        asyncio.create_task(self._cleanup_inactive_agents())
        logger.info("Agent registry started")

    async def stop(self) -> None:
        """Stop the registry service"""
        if self.redis_client:
            await self.redis_client.aclose()
        logger.info("Agent registry stopped")

    async def register_agent(self, agent_info: AgentInfo) -> bool:
        """Register a new agent"""
        try:
            self.agents[agent_info.agent_id] = agent_info
            self._update_indexes(agent_info)
            await self._save_agent_to_redis(agent_info)
            await self._publish_agent_event("agent_registered", agent_info)
            logger.info("Agent %s registered successfully", agent_info.agent_id)
            return True
        except Exception as e:
            logger.error("Error registering agent %s: %s", agent_info.agent_id, e)
            return False

    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent"""
        try:
            if agent_id not in self.agents:
                logger.warning("Agent %s not found for unregistration", agent_id)
                return False
            agent_info = self.agents[agent_id]
            del self.agents[agent_id]
            self._remove_from_indexes(agent_info)
            await self._remove_agent_from_redis(agent_id)
            await self._publish_agent_event("agent_unregistered", agent_info)
            logger.info("Agent %s unregistered successfully", agent_id)
            return True
        except Exception as e:
            logger.error("Error unregistering agent %s: %s", agent_id, e)
            return False

    async def update_agent_status(
        self, agent_id: str, status: AgentStatus, load_metrics: dict[str, float] | None = None
    ) -> bool:
        """Update agent status and metrics"""
        try:
            if agent_id not in self.agents:
                logger.warning("Agent %s not found for status update", agent_id)
                return False
            agent_info = self.agents[agent_id]
            agent_info.status = status
            agent_info.last_heartbeat = datetime.now(UTC)
            if load_metrics:
                agent_info.load_metrics.update(load_metrics)
            agent_info.health_score = self._calculate_health_score(agent_info)
            await self._save_agent_to_redis(agent_info)
            await self._publish_agent_event("agent_status_updated", agent_info)
            return True
        except Exception as e:
            logger.error("Error updating agent status %s: %s", agent_id, e)
            return False

    async def update_agent_heartbeat(self, agent_id: str) -> bool:
        """Update agent heartbeat"""
        try:
            if agent_id not in self.agents:
                logger.warning("Agent %s not found for heartbeat", agent_id)
                return False
            agent_info = self.agents[agent_id]
            agent_info.last_heartbeat = datetime.now(UTC)
            agent_info.health_score = self._calculate_health_score(agent_info)
            await self._save_agent_to_redis(agent_info)
            return True
        except Exception as e:
            logger.error("Error updating heartbeat for %s: %s", agent_id, e)
            return False

    async def discover_agents(self, query: dict[str, Any]) -> list[AgentInfo]:
        """Discover agents based on query criteria"""
        results = []
        try:
            candidate_agents = list(self.agents.values())
            if "agent_type" in query:
                agent_type = AgentType(query["agent_type"])
                candidate_agents = [a for a in candidate_agents if a.agent_type == agent_type]
            if "status" in query:
                status = AgentStatus(query["status"])
                candidate_agents = [a for a in candidate_agents if a.status == status]
            if "capabilities" in query:
                required_capabilities = set(query["capabilities"])
                candidate_agents = [a for a in candidate_agents if required_capabilities.issubset(a.capabilities)]
            if "services" in query:
                required_services = set(query["services"])
                candidate_agents = [a for a in candidate_agents if required_services.issubset(a.services)]
            if "tags" in query:
                required_tags = set(query["tags"])
                candidate_agents = [a for a in candidate_agents if required_tags.issubset(a.tags)]
            if "min_health_score" in query:
                min_score = query["min_health_score"]
                candidate_agents = [a for a in candidate_agents if a.health_score >= min_score]
            results = sorted(candidate_agents, key=lambda a: a.health_score, reverse=True)
            if "limit" in query:
                results = results[: query["limit"]]
            logger.info("Discovered %s agents for query: %s", len(results), query)
            return results
        except Exception as e:
            logger.error("Error discovering agents: %s", e)
            return []

    async def get_agent_by_id(self, agent_id: str) -> AgentInfo | None:
        """Get agent information by ID"""
        return self.agents.get(agent_id)

    async def get_agents_by_service(self, service: str) -> list[AgentInfo]:
        """Get agents that provide a specific service"""
        agent_ids = self.service_index.get(service, set())
        return [self.agents[agent_id] for agent_id in agent_ids if agent_id in self.agents]

    async def get_agents_by_capability(self, capability: str) -> list[AgentInfo]:
        """Get agents that have a specific capability"""
        agent_ids = self.capability_index.get(capability, set())
        return [self.agents[agent_id] for agent_id in agent_ids if agent_id in self.agents]

    async def get_agents_by_type(self, agent_type: AgentType) -> list[AgentInfo]:
        """Get agents of a specific type"""
        agent_ids = self.type_index.get(agent_type, set())
        return [self.agents[agent_id] for agent_id in agent_ids if agent_id in self.agents]

    async def get_registry_stats(self) -> dict[str, Any]:
        """Get registry statistics"""
        total_agents = len(self.agents)
        status_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        for agent_info in self.agents.values():
            status = agent_info.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            agent_type = agent_info.agent_type.value
            type_counts[agent_type] = type_counts.get(agent_type, 0) + 1
        return {
            "total_agents": total_agents,
            "status_counts": status_counts,
            "type_counts": type_counts,
            "service_count": len(self.service_index),
            "capability_count": len(self.capability_index),
            "last_cleanup": datetime.now(UTC).isoformat(),
        }

    def _update_indexes(self, agent_info: AgentInfo) -> None:
        """Update search indexes"""
        for service in agent_info.services:
            if service not in self.service_index:
                self.service_index[service] = set()
            self.service_index[service].add(agent_info.agent_id)
        for capability in agent_info.capabilities:
            if capability not in self.capability_index:
                self.capability_index[capability] = set()
            self.capability_index[capability].add(agent_info.agent_id)
        if agent_info.agent_type not in self.type_index:
            self.type_index[agent_info.agent_type] = set()
        self.type_index[agent_info.agent_type].add(agent_info.agent_id)

    def _remove_from_indexes(self, agent_info: AgentInfo) -> None:
        """Remove agent from search indexes"""
        for service in agent_info.services:
            if service in self.service_index:
                self.service_index[service].discard(agent_info.agent_id)
                if not self.service_index[service]:
                    del self.service_index[service]
        for capability in agent_info.capabilities:
            if capability in self.capability_index:
                self.capability_index[capability].discard(agent_info.agent_id)
                if not self.capability_index[capability]:
                    del self.capability_index[capability]
        if agent_info.agent_type in self.type_index:
            self.type_index[agent_info.agent_type].discard(agent_info.agent_id)
            if not self.type_index[agent_info.agent_type]:
                del self.type_index[agent_info.agent_type]

    def _calculate_health_score(self, agent_info: AgentInfo) -> float:
        """Calculate agent health score"""
        base_score = 1.0
        if agent_info.load_metrics:
            avg_load = sum(agent_info.load_metrics.values()) / len(agent_info.load_metrics)
            if avg_load > 0.8:
                base_score -= 0.3
            elif avg_load > 0.6:
                base_score -= 0.1
        if agent_info.status == AgentStatus.ERROR:
            base_score -= 0.5
        elif agent_info.status == AgentStatus.MAINTENANCE:
            base_score -= 0.2
        elif agent_info.status == AgentStatus.BUSY:
            base_score -= 0.1
        heartbeat_age = (datetime.now(UTC) - agent_info.last_heartbeat).total_seconds()
        if heartbeat_age > self.max_heartbeat_age:
            base_score -= 0.5
        elif heartbeat_age > self.max_heartbeat_age / 2:
            base_score -= 0.2
        return max(0.0, min(1.0, base_score))

    async def _save_agent_to_redis(self, agent_info: AgentInfo) -> None:
        """Save agent information to Redis"""
        if not self.redis_client:
            return
        key = f"agent:{agent_info.agent_id}"
        await self.redis_client.set(key, json.dumps(agent_info.to_dict()), ex=timedelta(hours=24))

    async def _remove_agent_from_redis(self, agent_id: str) -> None:
        """Remove agent from Redis"""
        if not self.redis_client:
            return
        key = f"agent:{agent_id}"
        await self.redis_client.delete(key)

    async def _load_agents_from_redis(self) -> None:
        """Load agents from Redis"""
        if not self.redis_client:
            return
        try:
            keys = await self.redis_client.keys("agent:*")
            for key in keys:
                data = await self.redis_client.get(key)
                if data:
                    agent_info = AgentInfo.from_dict(json.loads(data))
                    self.agents[agent_info.agent_id] = agent_info
                    self._update_indexes(agent_info)
            logger.info("Loaded %s agents from Redis", len(self.agents))
        except Exception as e:
            logger.error("Error loading agents from Redis: %s", e)

    async def _publish_agent_event(self, event_type: str, agent_info: AgentInfo) -> None:
        """Publish agent event to Redis"""
        if not self.redis_client:
            return
        event = {"event_type": event_type, "timestamp": datetime.now(UTC).isoformat(), "agent_info": agent_info.to_dict()}
        await self.redis_client.publish("agent_events", json.dumps(event))

    async def _heartbeat_monitor(self) -> None:
        """Monitor agent heartbeats"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                now = datetime.now(UTC)
                for agent_id, agent_info in list(self.agents.items()):
                    heartbeat_age = (now - agent_info.last_heartbeat).total_seconds()
                    if heartbeat_age > self.max_heartbeat_age:
                        if agent_info.status != AgentStatus.INACTIVE:
                            await self.update_agent_status(agent_id, AgentStatus.INACTIVE)
                            logger.warning("Agent %s marked as inactive due to old heartbeat", agent_id)
            except Exception as e:
                logger.error("Error in heartbeat monitor: %s", e)
                await asyncio.sleep(5)

    async def _cleanup_inactive_agents(self) -> None:
        """Clean up inactive agents"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                now = datetime.now(UTC)
                max_inactive_age = timedelta(hours=1)
                for agent_id, agent_info in list(self.agents.items()):
                    if agent_info.status == AgentStatus.INACTIVE:
                        inactive_age = now - agent_info.last_heartbeat
                        if inactive_age > max_inactive_age:
                            await self.unregister_agent(agent_id)
                            logger.info("Removed inactive agent %s", agent_id)
            except Exception as e:
                logger.error("Error in cleanup task: %s", e)
                await asyncio.sleep(5)


class AgentDiscoveryService:
    """Service for agent discovery and registration"""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self.discovery_handlers: dict[str, Callable[[Any], Any]] = {}

    def register_discovery_handler(self, handler_name: str, handler: Callable[[Any], Any]) -> None:
        """Register a discovery handler"""
        self.discovery_handlers[handler_name] = handler
        logger.info("Registered discovery handler: %s", handler_name)

    async def handle_discovery_request(self, message: AgentMessage) -> AgentMessage | None:
        """Handle agent discovery request"""
        try:
            discovery_data = DiscoveryMessage(**message.payload)
            agent_info = AgentInfo(
                agent_id=discovery_data.agent_id,
                agent_type=AgentType(discovery_data.agent_type),
                status=AgentStatus.ACTIVE,
                capabilities=discovery_data.capabilities,
                services=discovery_data.services,
                endpoints=discovery_data.endpoints,
                metadata=discovery_data.metadata,
                last_heartbeat=datetime.now(UTC),
                registration_time=datetime.now(UTC),
            )
            if discovery_data.agent_id in self.registry.agents:
                await self.registry.update_agent_status(discovery_data.agent_id, AgentStatus.ACTIVE)
            else:
                await self.registry.register_agent(agent_info)
            available_agents = await self.registry.discover_agents({"status": "active", "limit": 50})
            response_data = {
                "discovery_agents": [agent.to_dict() for agent in available_agents],
                "registry_stats": await self.registry.get_registry_stats(),
            }
            response = AgentMessage(
                sender_id="discovery_service",
                receiver_id=message.sender_id,
                message_type=MessageType.DISCOVERY,
                payload=response_data,
                correlation_id=message.id,
            )
            return response
        except Exception as e:
            logger.error("Error handling discovery request: %s", e)
            return None

    async def find_best_agent(self, requirements: dict[str, Any]) -> AgentInfo | None:
        """Find the best agent for given requirements"""
        try:
            query = {}
            if "agent_type" in requirements:
                query["agent_type"] = requirements["agent_type"]
            if "capabilities" in requirements:
                query["capabilities"] = requirements["capabilities"]
            if "services" in requirements:
                query["services"] = requirements["services"]
            if "min_health_score" in requirements:
                query["min_health_score"] = requirements["min_health_score"]
            agents = await self.registry.discover_agents(query)
            if not agents:
                return None
            return agents[0]
        except Exception as e:
            logger.error("Error finding best agent: %s", e)
            return None

    async def get_service_endpoints(self, service: str) -> dict[str, list[str]]:
        """Get all endpoints for a specific service"""
        try:
            agents = await self.registry.get_agents_by_service(service)
            endpoints: dict[str, list[str]] = {}
            for agent in agents:
                for service_name, endpoint in agent.endpoints.items():
                    if service_name not in endpoints:
                        endpoints[service_name] = []
                    endpoints[service_name].append(endpoint)
            return endpoints
        except Exception as e:
            logger.error("Error getting service endpoints: %s", e)
            return {}


def create_agent_info(
    agent_id: str, agent_type: str, capabilities: list[str], services: list[str], endpoints: dict[str, str]
) -> AgentInfo:
    """Create agent information"""
    return AgentInfo(
        agent_id=agent_id,
        agent_type=AgentType(agent_type),
        status=AgentStatus.ACTIVE,
        capabilities=capabilities,
        services=services,
        endpoints=endpoints,
        metadata={},
        last_heartbeat=datetime.now(UTC),
        registration_time=datetime.now(UTC),
    )


async def example_usage() -> None:
    """Example of how to use the agent discovery system"""
    registry = AgentRegistry()
    await registry.start()
    discovery_service = AgentDiscoveryService(registry)
    agent_info = create_agent_info(
        agent_id="agent-001",
        agent_type="worker",
        capabilities=["data_processing", "analysis"],
        services=["process_data", "analyze_results"],
        endpoints={"http": "http://localhost:8001", "ws": "ws://localhost:8002"},
    )
    await registry.register_agent(agent_info)
    agents = await registry.discover_agents({"capabilities": ["data_processing"], "status": "active"})
    logger.info("Found %s agents", len(agents))
    best_agent = await discovery_service.find_best_agent({"capabilities": ["data_processing"], "min_health_score": 0.8})
    if best_agent:
        logger.info("Best agent: %s", best_agent.agent_id)
    await registry.stop()


if __name__ == "__main__":
    asyncio.run(example_usage())
