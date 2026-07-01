"""Settlement service RPC client (v0.9.0 §A3).

Async HTTP client that wraps the blockchain node's settlement endpoints
(Agent B B5) and the trading service's settlement endpoints (Agent B B6).
Used by the CLI and other services to create escrows, lock funds, verify
locks, execute trades, settle atomically, and handle refunds/disputes.

The client is async-first (``httpx.AsyncClient``) and supports both
context-manager usage (``async with SettlementClient() as c: ...``) and
explicit ``close()``. Methods raise ``httpx.HTTPStatusError`` on non-2xx
responses; callers are responsible for retry/backoff.

Endpoint mapping (Agent B B5 — blockchain node, port 8202):
- POST /rpc/bridge/settlement/create           -> create_escrow
- POST /rpc/bridge/settlement/{id}/lock        -> lock_escrow
- POST /rpc/bridge/settlement/{id}/verify      -> verify_lock
- POST /rpc/bridge/settlement/{id}/execute     -> execute_trade
- POST /rpc/bridge/settlement/{id}/settle      -> settle
- POST /rpc/bridge/settlement/{id}/refund      -> refund
- GET  /rpc/bridge/settlement/{id}             -> get_escrow
- POST /rpc/bridge/settlement/{id}/extend-timeout -> extend_timeout
- GET  /rpc/bridge/settlement/{id}/proofs      -> get_proofs
- POST /rpc/bridge/settlement/{id}/dispute     -> file_dispute
- POST /rpc/bridge/settlement/{id}/resolve     -> resolve_dispute

Trading service endpoints (Agent B B6 — port 8104):
- POST /v1/trading/trades/{id}/lock-escrow      -> lock_escrow_for_trade
- POST /v1/trading/trades/{id}/settle           -> settle_trade
- GET  /v1/trading/trades/{id}/settlement-status -> get_trade_settlement_status
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from .types import SettlementConfig

logger = logging.getLogger(__name__)


class SettlementClient:
    """HTTP client for atomic cross-chain settlement RPC endpoints.

    Wraps the blockchain node's settlement endpoints (Agent B B5) for
    low-level escrow operations and the trading service's settlement
    endpoints (Agent B B6) for trade-level operations.

    The blockchain node runs on port 8202 and the trading service on
    port 8104 (verified in ``aitbc/constants.py:50`` and
    ``apps/trading/src/trading_service/main.py:469``).
    """

    def __init__(self, config: SettlementConfig | None = None) -> None:
        self._config = config or SettlementConfig()
        self._client: httpx.AsyncClient | None = None

    @property
    def config(self) -> SettlementConfig:
        """The active settlement configuration."""
        return self._config

    async def __aenter__(self) -> SettlementClient:
        self._client = httpx.AsyncClient(
            base_url=self._config.settlement_rpc_url,
            timeout=self._config.timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.settlement_rpc_url,
                timeout=self._config.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Escrow lifecycle operations (blockchain node)
    # ------------------------------------------------------------------

    async def create_escrow(
        self,
        trade_id: str,
        source_chain: str,
        dest_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        timeout_seconds: int | None = None,
        asset: str = "native",
    ) -> dict[str, Any]:
        """Create a new cross-chain escrow for atomic settlement.

        Generates an HTLC secret and hashlock, calculates timelocks for
        both chains, and creates an escrow record on the blockchain node.

        Returns the escrow record including ``escrow_id``, ``secret_hash``,
        ``source_timelock``, and ``dest_timelock``.
        """
        payload: dict[str, Any] = {
            "trade_id": trade_id,
            "source_chain": source_chain,
            "dest_chain": dest_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "asset": asset,
        }
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        resp = await self._ensure_client().post("/rpc/bridge/settlement/create", json=payload)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def lock_escrow(self, escrow_id: str) -> dict[str, Any]:
        """Lock funds on the source chain for an escrow.

        Initiates the HTLC contract on the source chain, locking funds
        with the pre-computed hashlock and timelock. Returns the lock
        proof and source lock transaction hash.
        """
        resp = await self._ensure_client().post(f"/rpc/bridge/settlement/{escrow_id}/lock")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def verify_lock(self, escrow_id: str) -> dict[str, Any]:
        """Verify the lock proof on the destination chain.

        Uses the bridge proof verification (v0.7.2 in-process verifier
        or external oracle with fallback, v0.7.4) to verify that funds
        were actually locked on the source chain.
        """
        resp = await self._ensure_client().post(f"/rpc/bridge/settlement/{escrow_id}/verify")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def execute_trade(self, escrow_id: str) -> dict[str, Any]:
        """Execute the trade on the destination chain.

        Marks the trade as executed on the destination chain (e.g., AI
        service delivered, compute job completed). Generates the
        execution proof.
        """
        resp = await self._ensure_client().post(f"/rpc/bridge/settlement/{escrow_id}/execute")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def settle(self, escrow_id: str, secret: str) -> dict[str, Any]:
        """Settle the escrow atomically by revealing the secret.

        Reveals the HTLC secret on the destination chain to claim funds,
        then uses the revealed secret to release funds on the source
        chain. Both chains settle atomically.

        Args:
            escrow_id: The escrow ID to settle
            secret: The HTLC secret (hex string) that matches the hashlock
        """
        resp = await self._ensure_client().post(
            f"/rpc/bridge/settlement/{escrow_id}/settle",
            json={"secret": secret},
        )
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def refund(self, escrow_id: str) -> dict[str, Any]:
        """Refund the escrow on both chains after timeout.

        Initiates refund on both chains when the timelock has expired.
        Both chains must refund atomically — no partial state.
        """
        resp = await self._ensure_client().post(f"/rpc/bridge/settlement/{escrow_id}/refund")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_escrow(self, escrow_id: str) -> dict[str, Any]:
        """Get full escrow details by ID."""
        resp = await self._ensure_client().get(f"/rpc/bridge/settlement/{escrow_id}")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_escrow_status(self, escrow_id: str) -> str:
        """Get the current status of an escrow.

        Returns the EscrowStatus value as a string (e.g., "pending",
        "locked", "completed", "refunded").
        """
        data = await self.get_escrow(escrow_id)
        return str(data.get("status", "unknown"))

    # ------------------------------------------------------------------
    # Timeout management
    # ------------------------------------------------------------------

    async def extend_timeout(self, escrow_id: str, extension_seconds: int) -> dict[str, Any]:
        """Extend the escrow timeout.

        Requires mutual agreement (multi-sig) from both parties. The
        total extension cannot exceed ``max_timeout_extension_seconds``
        from the original timeout.
        """
        resp = await self._ensure_client().post(
            f"/rpc/bridge/settlement/{escrow_id}/extend-timeout",
            json={"extension_seconds": extension_seconds},
        )
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def check_timeout(self, escrow_id: str) -> dict[str, Any]:
        """Check if an escrow has timed out and needs refunding.

        Returns ``{"timed_out": bool, "source_expired": bool,
        "dest_expired": bool}``.
        """
        data = await self.get_escrow(escrow_id)
        return {
            "timed_out": data.get("status") == "refunded" or data.get("timed_out", False),
            "source_expired": data.get("source_expired", False),
            "dest_expired": data.get("dest_expired", False),
        }

    # ------------------------------------------------------------------
    # Proof operations
    # ------------------------------------------------------------------

    async def get_lock_proof(self, escrow_id: str) -> dict[str, Any]:
        """Get the lock proof for an escrow."""
        data = await self.get_proofs(escrow_id)
        proofs = data.get("proofs", [])
        for p in proofs:
            if p.get("proof_type") == "lock":
                return cast(dict[str, Any], p)
        return {}

    async def get_execution_proof(self, escrow_id: str) -> dict[str, Any]:
        """Get the execution proof for an escrow."""
        data = await self.get_proofs(escrow_id)
        proofs = data.get("proofs", [])
        for p in proofs:
            if p.get("proof_type") == "execution":
                return cast(dict[str, Any], p)
        return {}

    async def get_release_proof(self, escrow_id: str) -> dict[str, Any]:
        """Get the release proof for an escrow."""
        data = await self.get_proofs(escrow_id)
        proofs = data.get("proofs", [])
        for p in proofs:
            if p.get("proof_type") == "release":
                return cast(dict[str, Any], p)
        return {}

    async def get_settlement_proof(self, escrow_id: str) -> dict[str, Any]:
        """Get the settlement proof for an escrow."""
        data = await self.get_proofs(escrow_id)
        proofs = data.get("proofs", [])
        for p in proofs:
            if p.get("proof_type") == "settlement":
                return cast(dict[str, Any], p)
        return {}

    async def get_proofs(self, escrow_id: str) -> dict[str, Any]:
        """Get the full proof chain for an escrow."""
        resp = await self._ensure_client().get(f"/rpc/bridge/settlement/{escrow_id}/proofs")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def verify_proof_chain(self, escrow_id: str) -> dict[str, Any]:
        """Verify the integrity of the proof chain for an escrow.

        Returns ``{"valid": bool, "errors": list[str]}``.
        """
        data = await self.get_proofs(escrow_id)
        return {
            "valid": data.get("valid", False),
            "errors": data.get("errors", []),
        }

    # ------------------------------------------------------------------
    # Dispute resolution
    # ------------------------------------------------------------------

    async def file_dispute(self, escrow_id: str, reason: str, evidence: str = "") -> dict[str, Any]:
        """File a dispute for an escrow.

        Puts the escrow into ``disputed`` status, halting automatic
        timeout/refund until the dispute is resolved.
        """
        resp = await self._ensure_client().post(
            f"/rpc/bridge/settlement/{escrow_id}/dispute",
            json={"reason": reason, "evidence": evidence},
        )
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def resolve_dispute(self, escrow_id: str, resolution: str) -> dict[str, Any]:
        """Resolve a dispute for an escrow.

        Args:
            escrow_id: The escrow ID in dispute
            resolution: "complete" (release to seller) or "refund" (refund buyer)
        """
        resp = await self._ensure_client().post(
            f"/rpc/bridge/settlement/{escrow_id}/resolve",
            json={"resolution": resolution},
        )
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    # ------------------------------------------------------------------
    # Trading service endpoints (port 8104)
    # ------------------------------------------------------------------

    async def lock_escrow_for_trade(self, trade_id: str, timeout_seconds: int | None = None) -> dict[str, Any]:
        """Lock escrow for an existing inter-chain trade.

        Wraps the trading service endpoint which coordinates with the
        blockchain node's settlement RPC. This is the high-level entry
        point used by the CLI ``trade lock-escrow`` command.
        """
        url = f"{self._config.trading_rpc_url}/v1/trading/trades/{trade_id}/lock-escrow"
        payload: dict[str, Any] = {}
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        resp = await self._ensure_client().post(url, json=payload)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def settle_trade(self, trade_id: str, secret: str) -> dict[str, Any]:
        """Settle an inter-chain trade by revealing the HTLC secret.

        Wraps the trading service endpoint which coordinates with the
        blockchain node's settlement RPC. This is the high-level entry
        point used by the CLI ``trade settle`` command.
        """
        url = f"{self._config.trading_rpc_url}/v1/trading/trades/{trade_id}/settle"
        resp = await self._ensure_client().post(url, json={"secret": secret})
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_trade_settlement_status(self, trade_id: str) -> dict[str, Any]:
        """Get the settlement status for an inter-chain trade.

        Returns the escrow status, settlement phase, and proof chain
        verification result.
        """
        url = f"{self._config.trading_rpc_url}/v1/trading/trades/{trade_id}/settlement-status"
        resp = await self._ensure_client().get(url)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())
