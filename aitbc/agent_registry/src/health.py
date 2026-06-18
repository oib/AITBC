"""
Agent Health Tracking Module
Handles agent health monitoring, status updates, and cleanup
"""

import logging
import time
from decimal import Decimal
from typing import Any

from .registration import AgentInfo, AgentStatus, AgentType, CapabilityType

logger = logging.getLogger(__name__)


def log_info(msg: str):
    logger.info(msg)


class AgentHealthTracker:
    """Agent health monitoring and status management"""

    def __init__(self, agents: dict[str, AgentInfo], capability_index: dict[CapabilityType, set[str]], type_index: dict):
        """
        Initialize health tracker

        Args:
            agents: Dictionary of agent_id -> AgentInfo
            capability_index: Capability type -> set of agent_ids
            type_index: Agent type -> set of agent_ids
        """
        self.agents = agents
        self.capability_index = capability_index
        self.type_index = type_index
        self.inactivity_threshold = 86400 * 7  # 7 days

    def update_agent_status(self, agent_id: str, status: AgentStatus) -> tuple[bool, str]:
        """Update agent status"""
        if agent_id not in self.agents:
            return False, "Agent not found"

        agent = self.agents[agent_id]
        old_status = agent.status
        agent.status = status
        agent.last_active = time.time()

        log_info(f"Agent {agent_id} status changed: {old_status.value} -> {status.value}")
        return True, "Status updated successfully"

    def check_agent_health(self, agent_id: str) -> dict[str, Any] | None:
        """Check health status of an agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return None

        current_time = time.time()
        time_since_active = current_time - agent.last_active
        is_inactive = time_since_active > self.inactivity_threshold

        return {
            "agent_id": agent_id,
            "status": agent.status.value,
            "last_active": agent.last_active,
            "time_since_active_seconds": time_since_active,
            "is_inactive": is_inactive,
            "reputation_score": agent.reputation_score,
            "total_jobs_completed": agent.total_jobs_completed,
        }

    def cleanup_inactive_agents(self) -> tuple[int, str]:
        """Clean up inactive agents"""
        current_time = time.time()
        cleaned_count = 0

        for agent_id, agent in list(self.agents.items()):
            if agent.status == AgentStatus.INACTIVE and current_time - agent.last_active > self.inactivity_threshold:
                # Remove from registry
                del self.agents[agent_id]

                # Update indexes
                self.type_index[agent.agent_type].discard(agent_id)
                for capability in agent.capabilities:
                    self.capability_index[capability.capability_type].discard(agent_id)

                cleaned_count += 1

        if cleaned_count > 0:
            log_info(f"Cleaned up {cleaned_count} inactive agents")

        return cleaned_count, f"Cleaned up {cleaned_count} inactive agents"

    def get_agent_statistics(self, agent_id: str) -> dict | None:
        """Get detailed statistics for an agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return None

        # Calculate additional statistics
        avg_job_earnings = (
            agent.total_earnings / agent.total_jobs_completed if agent.total_jobs_completed > 0 else Decimal("0")
        )
        days_active = (time.time() - agent.registration_time) / 86400
        jobs_per_day = agent.total_jobs_completed / days_active if days_active > 0 else 0

        return {
            "agent_id": agent_id,
            "name": agent.name,
            "type": agent.agent_type.value,
            "status": agent.status.value,
            "reputation_score": agent.reputation_score,
            "total_jobs_completed": agent.total_jobs_completed,
            "total_earnings": float(agent.total_earnings),
            "avg_job_earnings": float(avg_job_earnings),
            "jobs_per_day": jobs_per_day,
            "days_active": int(days_active),
            "capabilities_count": len(agent.capabilities),
            "last_active": agent.last_active,
            "registration_time": agent.registration_time,
        }

    def get_registry_statistics(self) -> dict:
        """Get registry-wide statistics"""
        total_agents = len(self.agents)
        active_agents = len([a for a in self.agents.values() if a.status == AgentStatus.ACTIVE])

        # Count by type
        type_counts = {}
        for agent_type in AgentType:
            type_counts[agent_type.value] = len(self.type_index[agent_type])

        # Count by capability
        capability_counts = {}
        for capability_type in CapabilityType:
            capability_counts[capability_type.value] = len(self.capability_index[capability_type])

        # Reputation statistics
        reputations = [a.reputation_score for a in self.agents.values()]
        avg_reputation = sum(reputations) / len(reputations) if reputations else 0

        # Earnings statistics
        total_earnings = sum(a.total_earnings for a in self.agents.values())

        return {
            "total_agents": total_agents,
            "active_agents": active_agents,
            "inactive_agents": total_agents - active_agents,
            "agent_types": type_counts,
            "capabilities": capability_counts,
            "average_reputation": avg_reputation,
            "total_earnings": float(total_earnings),
        }
