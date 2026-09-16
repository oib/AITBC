"""Swarm coordination router — intentionally unimplemented.

The mock endpoints that lived here were removed: they fabricated node lists
(``10.0.0.x``), task queues, cluster records, and stats (``nodes_online: 3``)
behind a ``settings.debug`` gate. The router stays mounted at ``/v1`` so the
module/import contract is stable, but it registers no routes — every
``/v1/swarm/*`` request returns 404 in every environment.

When a real swarm service is built, the canonical protocol is the
agent-collective model in ``aitbc_agent.swarm_coordinator``
(``/v1/swarm/{swarm_id}/register|broadcast|messages|decisions/participate``):
signed memberships, message passing, vote-weighted decisions — not the
compute-cluster shape the removed mocks served. Compute-node registry must
reuse the existing node registry rather than duplicate it. Mutating
endpoints must be gated on ``verify_rpc_api_key`` with signature-verified
membership (``identity.sign_message``) from day one. The models below keep
the request/response shapes as a sketch for that work.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/swarm", tags=["Swarm"])


class SwarmInfo(BaseModel):
    """Swarm information model."""

    swarm_id: str
    name: str
    status: str
    agent_count: int
    task_count: int


class JoinRequest(BaseModel):
    """Swarm join request model."""

    role: str
    capability: str
    priority: str
    region: str | None = None


class CoordinateRequest(BaseModel):
    """Swarm coordinate request model."""

    task: str
    collaborators: int
    strategy: str
    timeout_seconds: int


class TaskStatus(BaseModel):
    """Swarm task status model."""

    task_id: str
    status: str
    progress: int
    active_collaborators: int
    total_collaborators: int


class ConsensusRequest(BaseModel):
    """Swarm consensus request model."""

    consensus_threshold: float


class RegisterNodeRequest(BaseModel):
    """Request to register a compute node."""

    node_id: str
    address: str
    capabilities: list[str]
    cpu_cores: int
    memory_gb: int
    gpu_count: int


class ReportTaskRequest(BaseModel):
    """Request to report task status."""

    task_id: str
    node_id: str
    status: str
    result: dict[str, Any] | None = None


class CreateClusterRequest(BaseModel):
    """Request to create a compute cluster."""

    name: str
    description: str | None = None
    node_ids: list[str]
