from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .protocols.communication import CommunicationManager
    from .protocols.message_types import MessageProcessor
    from .routing.agent_discovery import AgentDiscoveryService, AgentRegistry
    from .routing.load_balancer import LoadBalancer, TaskDistributor

agent_registry: Optional[AgentRegistry] = None
discovery_service: Optional[AgentDiscoveryService] = None
load_balancer: Optional[LoadBalancer] = None
task_distributor: Optional[TaskDistributor] = None
communication_manager: Optional[CommunicationManager] = None
message_processor: Optional[MessageProcessor] = None
