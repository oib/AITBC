"""Swarm coordination router — intentionally unimplemented.

The mock endpoints that lived here were removed: they fabricated swarm joins,
task statuses, consensus outcomes, dashboards, and miner/job lists behind a
``settings.debug`` gate. The router registers no routes — every ``/v1/swarm/*``
request returns 404 in every environment.

When a real swarm service is built, the canonical protocol is the
agent-collective model in ``aitbc_agent.swarm_coordinator``
(``/v1/swarm/{swarm_id}/register|broadcast|messages|decisions/participate``):
signed memberships, message passing, vote-weighted decisions. Mutating
endpoints must require authenticated, signature-verified membership from day
one. The models below keep the request/response shapes (including the v0.6.5
``chain_id`` fields) as a sketch for that work.
"""

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
    chain_id: str | None = None  # v0.6.5


class CoordinateRequest(BaseModel):
    """Swarm coordinate request model."""

    task: str
    collaborators: int
    strategy: str
    timeout_seconds: int
    chain_id: str | None = None  # v0.6.5


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
