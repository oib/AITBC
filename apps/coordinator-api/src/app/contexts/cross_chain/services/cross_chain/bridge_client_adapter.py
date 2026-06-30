"""BridgeClient adapter for coordinator-api cross-chain context (v0.7.4 §B6).

Integrates ``aitbc.bridge.BridgeClient`` (the shared bridge SDK from v0.7.0)
into the coordinator-api's cross-chain context. This adapter routes bridge
operations through the blockchain-node's bridge RPC endpoints instead of
the coordinator-api's duplicate bridge implementation.

The adapter provides a thin wrapper that translates between the
coordinator-api's bridge schemas and the shared BridgeClient API.
The existing ``CrossChainBridgeService`` is kept for backward compatibility
with its SQLModel persistence layer, but new bridge RPC operations
(lock, confirm, unlock, status, balance, health) should go through
this adapter.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.bridge import BridgeClient, BridgeConfig, BridgeTransfer

logger = logging.getLogger(__name__)


class BridgeClientAdapter:
    """Adapter that wraps ``aitbc.bridge.BridgeClient`` for coordinator-api use.

    Provides methods that map to the blockchain-node bridge RPC endpoints,
    returning data in the format the coordinator-api routers expect.
    """

    def __init__(
        self,
        rpc_url: str = "http://localhost:8202",
        chain_id: str = "ait-hub",
        timeout: int = 30,
    ) -> None:
        self._config = BridgeConfig(rpc_url=rpc_url, chain_id=chain_id, timeout=timeout)
        self._client = BridgeClient(self._config)

    @property
    def client(self) -> BridgeClient:
        """Underlying BridgeClient instance."""
        return self._client

    async def lock(
        self,
        target_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        asset: str = "native",
        source_chain: str | None = None,
        signature: str = "",
    ) -> dict[str, Any]:
        """Lock assets on the source chain for bridging to target chain.

        Delegates to ``BridgeClient.lock()`` and returns the result
        in a coordinator-api-compatible dict.
        """
        result = await self._client.lock(
            target_chain=target_chain,
            sender=sender,
            recipient=recipient,
            amount=amount,
            asset=asset,
            source_chain=source_chain or self._config.chain_id,
            signature=signature,
        )
        logger.info("Bridge lock submitted: sender=%s, amount=%d, target=%s", sender, amount, target_chain)
        return result

    async def confirm(
        self,
        transfer_id: str,
        confirmer: str,
        signature: str,
        proof: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Confirm a bridge transfer on the target chain."""
        result = await self._client.confirm(
            transfer_id=transfer_id,
            confirmer=confirmer,
            signature=signature,
            proof=proof or {},
        )
        logger.info("Bridge confirm submitted: transfer_id=%s", transfer_id)
        return result

    async def unlock(
        self,
        transfer_id: str,
        sender: str,
        signature: str,
    ) -> dict[str, Any]:
        """Unlock/refund a pending bridge transfer."""
        result = await self._client.unlock(
            transfer_id=transfer_id,
            sender=sender,
            signature=signature,
        )
        logger.info("Bridge unlock submitted: transfer_id=%s", transfer_id)
        return result

    async def get_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Get the status of a bridge transfer."""
        return await self._client.get_transfer(transfer_id)

    async def list_pending(self, chain_id: str | None = None) -> list[dict[str, Any]]:
        """List pending bridge transfers."""
        return await self._client.list_pending(chain_id=chain_id)

    async def get_balance(self, chain_id: str) -> dict[str, Any]:
        """Get the bridge balance for a specific chain."""
        return await self._client.get_balance(chain_id)

    async def health(self) -> dict[str, Any]:
        """Get bridge health status."""
        return await self._client.health()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    def _transfer_to_dict(self, transfer: BridgeTransfer) -> dict[str, Any]:
        """Convert a BridgeTransfer dataclass to a coordinator-api-compatible dict."""
        return {
            "transfer_id": transfer.transfer_id,
            "source_chain": transfer.source_chain,
            "target_chain": transfer.target_chain,
            "sender": transfer.sender,
            "recipient": transfer.recipient,
            "amount": transfer.amount,
            "asset": transfer.asset,
            "status": transfer.status.value if hasattr(transfer.status, "value") else str(transfer.status),
            "source_tx_hash": transfer.source_tx_hash,
            "target_tx_hash": transfer.target_tx_hash,
            "lock_time": transfer.lock_time.isoformat() if transfer.lock_time else None,
            "confirm_time": transfer.confirm_time.isoformat() if transfer.confirm_time else None,
            "fee": transfer.fee,
        }
