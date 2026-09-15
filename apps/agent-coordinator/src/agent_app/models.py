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
    # v2.0 phase A: registry identity binding
    # (docs/agent-coordinator/agent-signed-envelopes.md §3). identity_address is
    # the secp256k1 wallet that receives this agent's escrow payouts;
    # identity_proof signs the canonical claim
    # {"agent_id","identity_address","chain_id","nonce","registered_at"} where
    # nonce is a one-time value from GET /v1/agents/nonce.
    identity_address: str | None = Field(None, description="secp256k1 identity/payout address to bind to agent_id")
    identity_proof: str | None = Field(None, description="Signature by identity_address over the registration claim")
    identity_nonce: str | None = Field(None, description="One-time nonce from GET /v1/agents/nonce")
    registered_at: str | None = Field(None, description="Client ISO timestamp covered by identity_proof")


class IdentityRotationRequest(BaseModel):
    """Dual-proof identity rotation for ``PUT /v1/agents/{agent_id}/identity`` (doc §7).

    ``new_proof`` is the new key's signature over the same registration claim
    shape used at registration (fresh one-time ``identity_nonce`` included).
    ``rotation_proof`` is the *currently bound* key's signature over
    ``{"agent_id","old_address","new_address","timestamp"}``.
    """

    new_address: str = Field(..., description="New secp256k1 identity/payout address")
    new_proof: str = Field(..., description="Signature by new_address over the registration claim")
    rotation_proof: str = Field(..., description="Signature by the currently bound key over the rotation claim")
    identity_nonce: str = Field(..., description="One-time nonce from GET /v1/agents/nonce covered by new_proof")
    registered_at: str = Field(..., description="Client ISO timestamp covered by new_proof")
    rotation_timestamp: str = Field(..., description="Client ISO timestamp covered by rotation_proof")
    chain_id: str | None = Field(None, description="Chain ID covered by new_proof")


class AgentStatusUpdate(BaseModel):
    status: str = Field(..., description="Agent status")
    load_metrics: dict[str, float] = Field(default_factory=dict, description="Load metrics")


class TaskPayment(BaseModel):
    """Payment details for task execution escrow (v0.6.5).

    ``lock_tx``/``lock_signature`` carry the buyer-signed ESCROW_LOCK
    transaction (same shape ``market escrow`` submits to /rpc/escrow/create).
    When present, the coordinator locks the escrow on-chain; when absent the
    escrow is bookkeeping-only (no chain transaction).
    """

    amount: int = Field(..., description="Payment amount in smallest units")
    fee: int = Field(0, description="Transaction fee")
    requester: str = Field(..., description="Requester address (pays for task)")
    agent: str = Field(..., description="Agent address (receives payment)")
    timeout_seconds: float = Field(3600.0, description="Escrow timeout")
    lock_tx: dict[str, Any] | None = Field(None, description="Buyer-signed ESCROW_LOCK transaction")
    lock_signature: str | None = Field(None, description="Signature over lock_tx")
    # P2.4/GAP-43: forwarded to the chain at release time; the chain stakes that
    # share of the released amount for the escrow's recorded provider.
    auto_reinvest_pct: float | None = Field(
        None, ge=0, le=100, description="Percentage of released payment to auto-stake as reinvestment"
    )


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
