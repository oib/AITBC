from typing import Any

from pydantic import BaseModel, Field


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


class AgentRegistrationRequest(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="Type of agent")
    capabilities: list[str] = Field(default_factory=list, description="Agent capabilities")
    services: list[str] = Field(default_factory=list, description="Available services")
    endpoints: dict[str, str] = Field(default_factory=dict, description="Service endpoints")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class AgentStatusUpdate(BaseModel):
    status: str = Field(..., description="Agent status")
    load_metrics: dict[str, float] = Field(default_factory=dict, description="Load metrics")


class TaskSubmission(BaseModel):
    task_data: dict[str, Any] = Field(..., description="Task data")
    priority: str = Field("normal", description="Task priority")
    requirements: dict[str, Any] | None = Field(None, description="Task requirements")


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
