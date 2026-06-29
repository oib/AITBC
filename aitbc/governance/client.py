"""Governance service RPC client (v0.7.3 §A2).

Async HTTP client that wraps the governance service REST endpoints
(``apps/governance/src/governance_service/main.py``). Used by the CLI and
other services to create proposals, cast votes, execute proposals, and
query governance state.

The client is async-first (``httpx.AsyncClient``) and supports both
context-manager usage (``async with GovernanceClient() as c: ...``) and
explicit ``close()``. Methods raise ``httpx.HTTPStatusError`` on non-2xx
responses; callers are responsible for retry/backoff.

Endpoint mapping (verified against ``main.py``):
- POST /v1/governance/proposals            -> create_proposal
- GET  /v1/governance/proposals            -> list_proposals
- GET  /v1/governance/proposals/{id}       -> get_proposal
- POST /v1/governance/votes                -> cast_vote
- GET  /v1/governance/votes                -> list_votes
- POST /v1/governance/execute              -> execute_proposal (legacy)
- POST /v1/governance/proposals/{id}/execute -> execute_proposal (v2)
- GET  /v1/governance/status               -> get_status
- GET  /v1/governance/voting-power/{addr}  -> get_voting_power
- GET  /v1/governance/analytics            -> get_analytics
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from .types import GovernanceConfig

logger = logging.getLogger(__name__)


class GovernanceClient:
    """HTTP client for the governance service REST endpoints.

    Wraps the governance service API (``apps/governance/``) for creating
    proposals, casting votes, executing proposals, and querying state.
    The governance service runs on port 8105 by default
    (``GOVERNANCE_BIND_PORT``, verified in ``main.py:408``).
    """

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        self._config = config or GovernanceConfig()
        self._client: httpx.AsyncClient | None = None

    @property
    def config(self) -> GovernanceConfig:
        """The active governance configuration."""
        return self._config

    async def __aenter__(self) -> GovernanceClient:
        self._client = httpx.AsyncClient(
            base_url=self._config.rpc_url,
            timeout=self._config.timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.rpc_url,
                timeout=self._config.timeout,
            )
        return self._client

    # ------------------------------------------------------------------
    # Proposals
    # ------------------------------------------------------------------

    async def create_proposal(self, proposal_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new governance proposal.

        ``proposal_data`` should contain: proposer, title, description,
        proposal_type, parameters (optional), voting_starts_block,
        voting_ends_block. The governance service will submit a
        GOVERNANCE_PROPOSE transaction to the blockchain (v0.7.3 Agent B).
        """
        resp = await self._ensure_client().post("/v1/governance/proposals", json=proposal_data)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Get a proposal by ID."""
        resp = await self._ensure_client().get(f"/v1/governance/proposals/{proposal_id}")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def list_proposals(
        self,
        status: str | None = None,
        proposal_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List proposals with optional filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if proposal_type:
            params["proposal_type"] = proposal_type
        resp = await self._ensure_client().get("/v1/governance/proposals", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        # Some servers wrap in {"proposals": [...]}
        if isinstance(data, dict) and isinstance(data.get("proposals"), list):
            return cast(list[dict[str, Any]], data["proposals"])
        return []

    # ------------------------------------------------------------------
    # Votes
    # ------------------------------------------------------------------

    async def cast_vote(self, vote_data: dict[str, Any]) -> dict[str, Any]:
        """Cast a vote on a proposal.

        ``vote_data`` should contain: proposal_id, voter, vote_type
        ("for"/"against"/"abstain"), reason (optional). The governance
        service will query the voter's on-chain balance at the snapshot
        block and submit a GOVERNANCE_VOTE transaction (v0.7.3 Agent B).
        """
        resp = await self._ensure_client().post("/v1/governance/votes", json=vote_data)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def list_votes(
        self,
        proposal_id: str | None = None,
        voter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List votes with optional filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if proposal_id:
            params["proposal_id"] = proposal_id
        if voter:
            params["voter"] = voter
        resp = await self._ensure_client().get("/v1/governance/votes", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        if isinstance(data, dict) and isinstance(data.get("votes"), list):
            return cast(list[dict[str, Any]], data["votes"])
        return []

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Execute a proposal after its timelock has expired.

        Uses the v2 endpoint ``POST /v1/governance/proposals/{id}/execute``
        which is the canonical path (the legacy ``POST /v1/governance/execute``
        is kept for backward compatibility but accepts a body).
        """
        resp = await self._ensure_client().post(f"/v1/governance/proposals/{proposal_id}/execute")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    # ------------------------------------------------------------------
    # Status & analytics
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """Get governance service status."""
        resp = await self._ensure_client().get("/v1/governance/status")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_voting_power(self, address: str) -> dict[str, Any]:
        """Get the voting power (on-chain balance) for an address."""
        resp = await self._ensure_client().get(f"/v1/governance/voting-power/{address}")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_analytics(self, period: str | None = None) -> dict[str, Any]:
        """Get governance analytics for a period (e.g. 'daily', 'weekly')."""
        params: dict[str, Any] = {}
        if period:
            params["period"] = period
        resp = await self._ensure_client().get("/v1/governance/analytics", params=params)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_params(self) -> dict[str, Any]:
        """Get governance parameters (voting period, quorum, approval, timelock)."""
        resp = await self._ensure_client().get("/v1/governance/params")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def health(self) -> dict[str, Any]:
        """Check governance service health."""
        resp = await self._ensure_client().get("/health")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
