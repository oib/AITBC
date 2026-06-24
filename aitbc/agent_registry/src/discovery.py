"""
Agent Discovery Module
Handles agent discovery, search, and filtering
"""

import logging
from decimal import Decimal
from typing import Any

from .registration import AgentInfo, AgentStatus, CapabilityType

logger = logging.getLogger(__name__)


def log_info(msg: str):
    logger.info(msg)


class AgentDiscovery:
    """Agent discovery and search functionality"""

    def __init__(self, agents: dict[str, AgentInfo], capability_index: dict[CapabilityType, set[str]], type_index: dict):
        """
        Initialize agent discovery

        Args:
            agents: Dictionary of agent_id -> AgentInfo
            capability_index: Capability type -> set of agent_ids
            type_index: Agent type -> set of agent_ids
        """
        self.agents = agents
        self.capability_index = capability_index
        self.type_index = type_index

    def find_agents_by_capability(
        self, capability_type: CapabilityType, filters: dict[str, Any] | None = None
    ) -> list[AgentInfo]:
        """Find agents by capability type"""
        agent_ids = self.capability_index.get(capability_type, set())

        agents = []
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if agent and agent.status == AgentStatus.ACTIVE and self._matches_filters(agent, filters):
                agents.append(agent)

        # Sort by reputation (highest first)
        agents.sort(key=lambda x: x.reputation_score, reverse=True)
        return agents

    def find_agents_by_type(self, agent_type, filters: dict[str, Any] | None = None) -> list[AgentInfo]:
        """Find agents by type"""
        agent_ids = self.type_index.get(agent_type, set())

        agents = []
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if agent and agent.status == AgentStatus.ACTIVE and self._matches_filters(agent, filters):
                agents.append(agent)

        # Sort by reputation (highest first)
        agents.sort(key=lambda x: x.reputation_score, reverse=True)
        return agents

    def search_agents(self, query: str, limit: int = 50) -> list[AgentInfo]:
        """Search agents by name or capability"""
        query_lower = query.lower()
        results = []

        for agent in self.agents.values():
            if agent.status != AgentStatus.ACTIVE:
                continue

            # Search in name
            if query_lower in agent.name.lower():
                results.append(agent)
                continue

            # Search in capabilities
            for capability in agent.capabilities:
                if query_lower in capability.name.lower() or query_lower in capability.capability_type.value:
                    results.append(agent)
                    break

        # Sort by relevance (reputation)
        results.sort(key=lambda x: x.reputation_score, reverse=True)
        return results[:limit]

    def _matches_filters(self, agent: AgentInfo, filters: dict[str, Any] | None) -> bool:
        """Check if agent matches filters"""
        if not filters:
            return True

        # Reputation filter
        if "min_reputation" in filters and agent.reputation_score < filters["min_reputation"]:
            return False

        # Cost filter
        if "max_cost_per_use" in filters:
            max_cost = Decimal(str(filters["max_cost_per_use"]))
            if any(cap.cost_per_use > max_cost for cap in agent.capabilities):
                return False

        # Availability filter
        if "min_availability" in filters:
            min_availability = filters["min_availability"]
            if any(cap.availability < min_availability for cap in agent.capabilities):
                return False

        # Location filter (if implemented)
        if "location" in filters:
            agent_location = agent.metadata.get("location")
            if agent_location != filters["location"]:
                return False

        return True
