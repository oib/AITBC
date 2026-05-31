from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols.communication import CommunicationManager
    from .protocols.message_types import MessageProcessor
    from .routing.agent_discovery import AgentDiscoveryService, AgentRegistry
    from .routing.load_balancer import LoadBalancer, TaskDistributor

agent_registry: AgentRegistry | None = None
discovery_service: AgentDiscoveryService | None = None
load_balancer: LoadBalancer | None = None
task_distributor: TaskDistributor | None = None
communication_manager: CommunicationManager | None = None
message_processor: MessageProcessor | None = None
