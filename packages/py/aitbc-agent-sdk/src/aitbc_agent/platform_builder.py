"""
Platform Builder - factory for constructing AITBC agent platform configurations
"""

from typing import Any

from aitbc.aitbc_logging import get_logger

from .agent import Agent

logger = get_logger(__name__)


class PlatformBuilder:
    """Builder pattern for constructing AITBC agent platforms"""

    def __init__(self, platform_name: str = "default") -> None:
        self.platform_name = platform_name
        self.agents: list[Agent] = []
        self.config: dict[str, Any] = {}

    def with_config(self, config: dict[str, Any]) -> "PlatformBuilder":
        """Set platform configuration"""
        self.config.update(config)
        return self

    def add_provider(
        self, name: str, capabilities: dict[str, Any]
    ) -> "PlatformBuilder":
        """Add a compute provider agent"""
        agent = Agent.create(name, "compute_provider", capabilities)
        self.agents.append(agent)
        logger.info(f"Added provider: {name}")
        return self

    def add_consumer(
        self, name: str, capabilities: dict[str, Any]
    ) -> "PlatformBuilder":
        """Add a compute consumer agent"""
        agent = Agent.create(name, "compute_consumer", capabilities)
        self.agents.append(agent)
        logger.info(f"Added consumer: {name}")
        return self

    def build(self) -> dict[str, Any]:
        """Build and return the platform configuration"""
        return {
            "platform_name": self.platform_name,
            "agents": [a.to_dict() for a in self.agents],
            "config": self.config,
            "agent_count": len(self.agents),
        }
