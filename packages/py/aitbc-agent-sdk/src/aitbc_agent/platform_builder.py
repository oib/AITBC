"""
Platform Builder - factory for constructing AITBC agent platform configurations
"""

import logging
from typing import Dict, List, Any, Optional
from .agent import Agent, AgentCapabilities, AgentIdentity
from .compute_provider import ComputeProvider
from .compute_consumer import ComputeConsumer
from .swarm_coordinator import SwarmCoordinator

logger = logging.getLogger(__name__)


class PlatformBuilder:
    """Builder pattern for constructing AITBC agent platforms"""

    def __init__(self, platform_name: str = "default") -> None:
        self.platform_name = platform_name
        self.agents: List[Agent] = []
        self.config: Dict[str, Any] = {}

    def with_config(self, config: Dict[str, Any]) -> "PlatformBuilder":
        """Set platform configuration"""
        self.config.update(config)
        return self

    def add_provider(self, name: str, capabilities: Dict[str, Any]) -> "PlatformBuilder":
        """Add a compute provider agent"""
        agent = Agent.create(name, "compute_provider", capabilities)
        self.agents.append(agent)
        logger.info(f"Added provider: {name}")
        return self

    def add_consumer(self, name: str, capabilities: Dict[str, Any]) -> "PlatformBuilder":
        """Add a compute consumer agent"""
        agent = Agent.create(name, "compute_consumer", capabilities)
        self.agents.append(agent)
        logger.info(f"Added consumer: {name}")
        return self

    def build(self) -> Dict[str, Any]:
        """Build and return the platform configuration"""
        return {
            "platform_name": self.platform_name,
            "agents": [a.to_dict() for a in self.agents],
            "config": self.config,
            "agent_count": len(self.agents),
        }
