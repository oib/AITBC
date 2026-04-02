"""
Agent Discovery and Registration System for AITBC Agent Coordination
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import uuid
import hashlib
from enum import Enum
import redis.asyncio as redis
from pydantic import BaseModel, Field

from ..protocols.message_types import DiscoveryMessage, create_discovery_message
from ..protocols.communication import AgentMessage, MessageType

logger = logging.getLogger(__name__)

class AgentStatus(str, Enum):
    """Agent status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BUSY = "busy"
    MAINTENANCE = "maintenance"
    ERROR = "error"

class AgentType(str, Enum):
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
    capabilities: List[str]
    services: List[str]
    endpoints: Dict[str, str]
    metadata: Dict[str, Any]
    last_heartbeat: datetime
    registration_time: datetime
    load_metrics: Dict[str, float] = field(default_factory=dict)
    health_score: float = 1.0
    version: str = "1.0.0"
    tags: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict[str, Any]:
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
            "tags": list(self.tags)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentInfo":
        """Create from dictionary"""
        data["agent_type"] = AgentType(data["agent_type"])
        data["status"] = AgentStatus(data["status"])
        data["last_heartbeat"] = datetime.fromisoformat(data["last_heartbeat"])
        data["registration_time"] = datetime.fromisoformat(data["registration_time"])
        data["tags"] = set(data.get("tags", []))
        return cls(**data)

class AgentRegistry:
    """Central agent registry for discovery and management"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/1"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.agents: Dict[str, AgentInfo] = {}
        self.service_index: Dict[str, Set[str]] = {}  # service -> agent_ids
        self.capability_index: Dict[str, Set[str]] = {}  # capability -> agent_ids
        self.type_index: Dict[AgentType, Set[str]] = {}  # agent_type -> agent_ids
        self.heartbeat_interval = 30  # seconds
        self.cleanup_interval = 60  # seconds
        self.max_heartbeat_age = 120  # seconds
        
    async def start(self):
        """Start the registry service"""
        self.redis_client = redis.from_url(self.redis_url)
        
        # Load existing agents from Redis
        await self._load_agents_from_redis()
        
        # Start background tasks
        asyncio.create_task(self._heartbeat_monitor())
        asyncio.create_task(self._cleanup_inactive_agents())
        
        logger.info("Agent registry started")
    
    async def stop(self):
        """Stop the registry service"""
        if self.redis_client:
            await self.redis_client.close()
        logger.info("Agent registry stopped")
    
    async def register_agent(self, agent_info: AgentInfo) -> bool:
        """Register a new agent"""
        try:
            # Add to local registry
            self.agents[agent_info.agent_id] = agent_info
            
            # Update indexes
            self._update_indexes(agent_info)
            
            # Save to Redis
            await self._save_agent_to_redis(agent_info)
            
            # Publish registration event
            await self._publish_agent_event("agent_registered", agent_info)
            
            logger.info(f"Agent {agent_info.agent_id} registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error registering agent {agent_info.agent_id}: {e}")
            return False
    
    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent"""
        try:
            if agent_id not in self.agents:
                logger.warning(f"Agent {agent_id} not found for unregistration")
                return False
            
            agent_info = self.agents[agent_id]
            
            # Remove from local registry
            del self.agents[agent_id]
            
            # Update indexes
            self._remove_from_indexes(agent_info)
            
            # Remove from Redis
            await self._remove_agent_from_redis(agent_id)
            
            # Publish unregistration event
            await self._publish_agent_event("agent_unregistered", agent_info)
            
            logger.info(f"Agent {agent_id} unregistered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error unregistering agent {agent_id}: {e}")
            return False
    
    async def update_agent_status(self, agent_id: str, status: AgentStatus, load_metrics: Optional[Dict[str, float]] = None) -> bool:
        """Update agent status and metrics"""
        try:
            if agent_id not in self.agents:
                logger.warning(f"Agent {agent_id} not found for status update")
                return False
            
            agent_info = self.agents[agent_id]
            agent_info.status = status
            agent_info.last_heartbeat = datetime.utcnow()
            
            if load_metrics:
                agent_info.load_metrics.update(load_metrics)
            
            # Update health score
            agent_info.health_score = self._calculate_health_score(agent_info)
            
            # Save to Redis
            await self._save_agent_to_redis(agent_info)
            
            # Publish status update event
            await self._publish_agent_event("agent_status_updated", agent_info)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating agent status {agent_id}: {e}")
            return False
    
    async def update_agent_heartbeat(self, agent_id: str) -> bool:
        """Update agent heartbeat"""
        try:
            if agent_id not in self.agents:
                logger.warning(f"Agent {agent_id} not found for heartbeat")
                return False
            
            agent_info = self.agents[agent_id]
            agent_info.last_heartbeat = datetime.utcnow()
            
            # Update health score
            agent_info.health_score = self._calculate_health_score(agent_info)
            
            # Save to Redis
            await self._save_agent_to_redis(agent_info)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating heartbeat for {agent_id}: {e}")
            return False
    
    async def discover_agents(self, query: Dict[str, Any]) -> List[AgentInfo]:
        """Discover agents based on query criteria"""
        results = []
        
        try:
            # Start with all agents
            candidate_agents = list(self.agents.values())
            
            # Apply filters
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
            
            # Sort by health score (highest first)
            results = sorted(candidate_agents, key=lambda a: a.health_score, reverse=True)
            
            # Limit results if specified
            if "limit" in query:
                results = results[:query["limit"]]
            
            logger.info(f"Discovered {len(results)} agents for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"Error discovering agents: {e}")
            return []
    
    async def get_agent_by_id(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent information by ID"""
        return self.agents.get(agent_id)
    
    async def get_agents_by_service(self, service: str) -> List[AgentInfo]:
        """Get agents that provide a specific service"""
        agent_ids = self.service_index.get(service, set())
        return [self.agents[agent_id] for agent_id in agent_ids if agent_id in self.agents]
    
    async def get_agents_by_capability(self, capability: str) -> List[AgentInfo]:
        """Get agents that have a specific capability"""
        agent_ids = self.capability_index.get(capability, set())
        return [self.agents[agent_id] for agent_id in agent_ids if agent_id in self.agents]
    
    async def get_agents_by_type(self, agent_type: AgentType) -> List[AgentInfo]:
        """Get agents of a specific type"""
        agent_ids = self.type_index.get(agent_type, set())
        return [self.agents[agent_id] for agent_id in agent_ids if agent_id in self.agents]
    
    async def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        total_agents = len(self.agents)
        status_counts = {}
        type_counts = {}
        
        for agent_info in self.agents.values():
            # Count by status
            status = agent_info.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # Count by type
            agent_type = agent_info.agent_type.value
            type_counts[agent_type] = type_counts.get(agent_type, 0) + 1
        
        return {
            "total_agents": total_agents,
            "status_counts": status_counts,
            "type_counts": type_counts,
            "service_count": len(self.service_index),
            "capability_count": len(self.capability_index),
            "last_cleanup": datetime.utcnow().isoformat()
        }
    
    def _update_indexes(self, agent_info: AgentInfo):
        """Update search indexes"""
        # Service index
        for service in agent_info.services:
            if service not in self.service_index:
                self.service_index[service] = set()
            self.service_index[service].add(agent_info.agent_id)
        
        # Capability index
        for capability in agent_info.capabilities:
            if capability not in self.capability_index:
                self.capability_index[capability] = set()
            self.capability_index[capability].add(agent_info.agent_id)
        
        # Type index
        if agent_info.agent_type not in self.type_index:
            self.type_index[agent_info.agent_type] = set()
        self.type_index[agent_info.agent_type].add(agent_info.agent_id)
    
    def _remove_from_indexes(self, agent_info: AgentInfo):
        """Remove agent from search indexes"""
        # Service index
        for service in agent_info.services:
            if service in self.service_index:
                self.service_index[service].discard(agent_info.agent_id)
                if not self.service_index[service]:
                    del self.service_index[service]
        
        # Capability index
        for capability in agent_info.capabilities:
            if capability in self.capability_index:
                self.capability_index[capability].discard(agent_info.agent_id)
                if not self.capability_index[capability]:
                    del self.capability_index[capability]
        
        # Type index
        if agent_info.agent_type in self.type_index:
            self.type_index[agent_info.agent_type].discard(agent_info.agent_id)
            if not self.type_index[agent_info.agent_type]:
                del self.type_index[agent_info.agent_type]
    
    def _calculate_health_score(self, agent_info: AgentInfo) -> float:
        """Calculate agent health score"""
        base_score = 1.0
        
        # Penalty for high load
        if agent_info.load_metrics:
            avg_load = sum(agent_info.load_metrics.values()) / len(agent_info.load_metrics)
            if avg_load > 0.8:
                base_score -= 0.3
            elif avg_load > 0.6:
                base_score -= 0.1
        
        # Penalty for error status
        if agent_info.status == AgentStatus.ERROR:
            base_score -= 0.5
        elif agent_info.status == AgentStatus.MAINTENANCE:
            base_score -= 0.2
        elif agent_info.status == AgentStatus.BUSY:
            base_score -= 0.1
        
        # Penalty for old heartbeat
        heartbeat_age = (datetime.utcnow() - agent_info.last_heartbeat).total_seconds()
        if heartbeat_age > self.max_heartbeat_age:
            base_score -= 0.5
        elif heartbeat_age > self.max_heartbeat_age / 2:
            base_score -= 0.2
        
        return max(0.0, min(1.0, base_score))
    
    async def _save_agent_to_redis(self, agent_info: AgentInfo):
        """Save agent information to Redis"""
        if not self.redis_client:
            return
        
        key = f"agent:{agent_info.agent_id}"
        await self.redis_client.setex(
            key,
            timedelta(hours=24),  # 24 hour TTL
            json.dumps(agent_info.to_dict())
        )
    
    async def _remove_agent_from_redis(self, agent_id: str):
        """Remove agent from Redis"""
        if not self.redis_client:
            return
        
        key = f"agent:{agent_id}"
        await self.redis_client.delete(key)
    
    async def _load_agents_from_redis(self):
        """Load agents from Redis"""
        if not self.redis_client:
            return
        
        try:
            # Get all agent keys
            keys = await self.redis_client.keys("agent:*")
            
            for key in keys:
                data = await self.redis_client.get(key)
                if data:
                    agent_info = AgentInfo.from_dict(json.loads(data))
                    self.agents[agent_info.agent_id] = agent_info
                    self._update_indexes(agent_info)
            
            logger.info(f"Loaded {len(self.agents)} agents from Redis")
            
        except Exception as e:
            logger.error(f"Error loading agents from Redis: {e}")
    
    async def _publish_agent_event(self, event_type: str, agent_info: AgentInfo):
        """Publish agent event to Redis"""
        if not self.redis_client:
            return
        
        event = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "agent_info": agent_info.to_dict()
        }
        
        await self.redis_client.publish("agent_events", json.dumps(event))
    
    async def _heartbeat_monitor(self):
        """Monitor agent heartbeats"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                # Check for agents with old heartbeats
                now = datetime.utcnow()
                for agent_id, agent_info in list(self.agents.items()):
                    heartbeat_age = (now - agent_info.last_heartbeat).total_seconds()
                    
                    if heartbeat_age > self.max_heartbeat_age:
                        # Mark as inactive
                        if agent_info.status != AgentStatus.INACTIVE:
                            await self.update_agent_status(agent_id, AgentStatus.INACTIVE)
                            logger.warning(f"Agent {agent_id} marked as inactive due to old heartbeat")
                
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(5)
    
    async def _cleanup_inactive_agents(self):
        """Clean up inactive agents"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                # Remove agents that have been inactive too long
                now = datetime.utcnow()
                max_inactive_age = timedelta(hours=1)  # 1 hour
                
                for agent_id, agent_info in list(self.agents.items()):
                    if agent_info.status == AgentStatus.INACTIVE:
                        inactive_age = now - agent_info.last_heartbeat
                        if inactive_age > max_inactive_age:
                            await self.unregister_agent(agent_id)
                            logger.info(f"Removed inactive agent {agent_id}")
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(5)

class AgentDiscoveryService:
    """Service for agent discovery and registration"""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.discovery_handlers: Dict[str, Callable] = {}
        
    def register_discovery_handler(self, handler_name: str, handler: Callable):
        """Register a discovery handler"""
        self.discovery_handlers[handler_name] = handler
        logger.info(f"Registered discovery handler: {handler_name}")
    
    async def handle_discovery_request(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle agent discovery request"""
        try:
            discovery_data = DiscoveryMessage(**message.payload)
            
            # Update or register agent
            agent_info = AgentInfo(
                agent_id=discovery_data.agent_id,
                agent_type=AgentType(discovery_data.agent_type),
                status=AgentStatus.ACTIVE,
                capabilities=discovery_data.capabilities,
                services=discovery_data.services,
                endpoints=discovery_data.endpoints,
                metadata=discovery_data.metadata,
                last_heartbeat=datetime.utcnow(),
                registration_time=datetime.utcnow()
            )
            
            # Register or update agent
            if discovery_data.agent_id in self.registry.agents:
                await self.registry.update_agent_status(discovery_data.agent_id, AgentStatus.ACTIVE)
            else:
                await self.registry.register_agent(agent_info)
            
            # Send response with available agents
            available_agents = await self.registry.discover_agents({
                "status": "active",
                "limit": 50
            })
            
            response_data = {
                "discovery_agents": [agent.to_dict() for agent in available_agents],
                "registry_stats": await self.registry.get_registry_stats()
            }
            
            response = AgentMessage(
                sender_id="discovery_service",
                receiver_id=message.sender_id,
                message_type=MessageType.DISCOVERY,
                payload=response_data,
                correlation_id=message.id
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error handling discovery request: {e}")
            return None
    
    async def find_best_agent(self, requirements: Dict[str, Any]) -> Optional[AgentInfo]:
        """Find the best agent for given requirements"""
        try:
            # Build discovery query
            query = {}
            
            if "agent_type" in requirements:
                query["agent_type"] = requirements["agent_type"]
            
            if "capabilities" in requirements:
                query["capabilities"] = requirements["capabilities"]
            
            if "services" in requirements:
                query["services"] = requirements["services"]
            
            if "min_health_score" in requirements:
                query["min_health_score"] = requirements["min_health_score"]
            
            # Discover agents
            agents = await self.registry.discover_agents(query)
            
            if not agents:
                return None
            
            # Select best agent (highest health score)
            return agents[0]
            
        except Exception as e:
            logger.error(f"Error finding best agent: {e}")
            return None
    
    async def get_service_endpoints(self, service: str) -> Dict[str, List[str]]:
        """Get all endpoints for a specific service"""
        try:
            agents = await self.registry.get_agents_by_service(service)
            endpoints = {}
            
            for agent in agents:
                for service_name, endpoint in agent.endpoints.items():
                    if service_name not in endpoints:
                        endpoints[service_name] = []
                    endpoints[service_name].append(endpoint)
            
            return endpoints
            
        except Exception as e:
            logger.error(f"Error getting service endpoints: {e}")
            return {}

# Factory functions
def create_agent_info(agent_id: str, agent_type: str, capabilities: List[str], services: List[str], endpoints: Dict[str, str]) -> AgentInfo:
    """Create agent information"""
    return AgentInfo(
        agent_id=agent_id,
        agent_type=AgentType(agent_type),
        status=AgentStatus.ACTIVE,
        capabilities=capabilities,
        services=services,
        endpoints=endpoints,
        metadata={},
        last_heartbeat=datetime.utcnow(),
        registration_time=datetime.utcnow()
    )

# Example usage
async def example_usage():
    """Example of how to use the agent discovery system"""
    
    # Create registry
    registry = AgentRegistry()
    await registry.start()
    
    # Create discovery service
    discovery_service = AgentDiscoveryService(registry)
    
    # Register an agent
    agent_info = create_agent_info(
        agent_id="agent-001",
        agent_type="worker",
        capabilities=["data_processing", "analysis"],
        services=["process_data", "analyze_results"],
        endpoints={"http": "http://localhost:8001", "ws": "ws://localhost:8002"}
    )
    
    await registry.register_agent(agent_info)
    
    # Discover agents
    agents = await registry.discover_agents({
        "capabilities": ["data_processing"],
        "status": "active"
    })
    
    print(f"Found {len(agents)} agents")
    
    # Find best agent
    best_agent = await discovery_service.find_best_agent({
        "capabilities": ["data_processing"],
        "min_health_score": 0.8
    })
    
    if best_agent:
        print(f"Best agent: {best_agent.agent_id}")
    
    await registry.stop()

if __name__ == "__main__":
    asyncio.run(example_usage())
