from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols.communication import CommunicationManager
    from .protocols.message_types import MessageProcessor
    from .routing.agent_discovery import AgentDiscoveryService, AgentRegistry
    from .routing.load_balancer import LoadBalancer, TaskDistributor
    from .storage.message_storage import MessageStorage, PeerStorage

agent_registry: AgentRegistry | None = None
discovery_service: AgentDiscoveryService | None = None
load_balancer: LoadBalancer | None = None
task_distributor: TaskDistributor | None = None
communication_manager: CommunicationManager | None = None
message_processor: MessageProcessor | None = None
message_storage: MessageStorage | None = None
peer_storage: PeerStorage | None = None


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
