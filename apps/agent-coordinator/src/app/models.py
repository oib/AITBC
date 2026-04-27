from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentRegistrationRequest(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="Type of agent")
    capabilities: List[str] = Field(default_factory=list, description="Agent capabilities")
    services: List[str] = Field(default_factory=list, description="Available services")
    endpoints: Dict[str, str] = Field(default_factory=dict, description="Service endpoints")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class AgentStatusUpdate(BaseModel):
    status: str = Field(..., description="Agent status")
    load_metrics: Dict[str, float] = Field(default_factory=dict, description="Load metrics")


class TaskSubmission(BaseModel):
    task_data: Dict[str, Any] = Field(..., description="Task data")
    priority: str = Field("normal", description="Task priority")
    requirements: Optional[Dict[str, Any]] = Field(None, description="Task requirements")


class MessageRequest(BaseModel):
    receiver_id: str = Field(..., description="Receiver agent ID")
    message_type: str = Field(..., description="Message type")
    payload: Dict[str, Any] = Field(..., description="Message payload")
    priority: str = Field("normal", description="Message priority")
