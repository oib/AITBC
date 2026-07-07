from typing import Any

from pydantic import BaseModel, Field


class AgentRegistrationRequest(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="Type of agent")
    capabilities: list[str] = Field(default_factory=list, description="Agent capabilities")
    services: list[str] = Field(default_factory=list, description="Available services")
    endpoints: dict[str, str] = Field(default_factory=dict, description="Service endpoints")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    # v0.6.5: chain/island awareness
    chain_id: str | None = Field(None, description="Chain ID this agent operates on")
    island_id: str | None = Field(None, description="Island ID this agent is on")


class AgentStatusUpdate(BaseModel):
    status: str = Field(..., description="Agent status")
    load_metrics: dict[str, float] = Field(default_factory=dict, description="Load metrics")


class TaskPayment(BaseModel):
    """Payment details for task execution escrow (v0.6.5)."""

    amount: int = Field(..., description="Payment amount in smallest units")
    fee: int = Field(0, description="Transaction fee")
    requester: str = Field(..., description="Requester address (pays for task)")
    agent: str = Field(..., description="Agent address (receives payment)")
    timeout_seconds: float = Field(3600.0, description="Escrow timeout")


class TaskSubmission(BaseModel):
    task_data: dict[str, Any] = Field(..., description="Task data")
    priority: str = Field("normal", description="Task priority")
    requirements: dict[str, Any] | None = Field(None, description="Task requirements")
    # v0.6.5: chain awareness + payment
    chain_id: str | None = Field(None, description="Chain ID to execute task on")
    payment: TaskPayment | None = Field(None, description="Payment for task execution escrow")


class MessageRequest(BaseModel):
    receiver_id: str = Field(..., description="Receiver agent ID")
    message_type: str = Field(..., description="Message type")
    payload: dict[str, Any] = Field(..., description="Message payload")
    priority: str = Field("normal", description="Message priority")
    protocol: str = Field("hierarchical", description="Communication protocol (hierarchical, peer_to_peer, broadcast)")


class BroadcastRequest(BaseModel):
    message_type: str = Field(..., description="Message type")
    payload: dict[str, Any] = Field(..., description="Message payload")
    priority: str = Field("normal", description="Message priority")
    agent_type: str | None = Field(None, description="Filter by agent type")
    capabilities: list[str] | None = Field(None, description="Filter by capabilities")
