"""Bridge integration utilities for inter-chain trading (v0.8.0 §A3).

Wraps ``BridgeClient`` from ``aitbc.bridge`` (v0.7.0-v0.7.2) for
trading-specific bridge operations. The trading service uses this to
lock escrow on the source chain, verify transfer status, and query
bridge balances when facilitating inter-chain trades.

The bridge RPC endpoints are on the blockchain node (port 8202, same
as the blockchain RPC). All 15 bridge endpoints from v0.7.0-v0.7.2 are
available:
- POST /bridge/lock — lock funds for cross-chain transfer
- POST /bridge/confirm — confirm and release bridged funds
- POST /bridge/unlock — refund/cancel a pending transfer
- GET  /bridge/transfer/{transfer_id} — get transfer status
- GET  /bridge/pending — list pending transfers
- GET  /bridge/balance/{chain_id} — get bridge balance per chain
- GET  /bridge/health — bridge health check

Note: v0.8.0 only uses lock + transfer status + balance + health.
Atomic settlement (confirm + unlock with HTLC) is deferred to v0.9.0.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.bridge import BridgeClient, BridgeConfig

from .types import TradingConfig

logger = logging.getLogger(__name__)


class TradingBridgeClient:
    """Bridge client wrapper for inter-chain trading operations.

    Wraps ``BridgeClient`` from ``aitbc.bridge`` with trading-specific
    methods. The bridge runs on the blockchain node (port 8202).

    Usage::

        async with TradingBridgeClient() as bridge:
            transfer = await bridge.lock_escrow(
                source_chain="ait-hub",
                amount=1000,
                sender="alice",
                recipient="bob",
            )
            status = await bridge.get_transfer_status(transfer["transfer_id"])
    """

    def __init__(
        self,
        config: TradingConfig | None = None,
        bridge_client: BridgeClient | None = None,
    ) -> None:
        self._config = config or TradingConfig()
        if bridge_client is not None:
            self._bridge = bridge_client
        else:
            bridge_config = BridgeConfig(rpc_url=self._config.bridge_rpc_url)
            self._bridge = BridgeClient(bridge_config)

    @property
    def bridge(self) -> BridgeClient:
        """The underlying BridgeClient instance."""
        return self._bridge

    async def __aenter__(self) -> TradingBridgeClient:
        await self._bridge.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self._bridge.__aexit__(exc_type, exc_val, exc_tb)

    async def lock_escrow(
        self,
        source_chain: str,
        target_chain: str,
        amount: int,
        sender: str,
        recipient: str,
        asset: str = "native",
        signature: str = "",
    ) -> dict[str, Any]:
        """Lock funds on the source chain for an inter-chain trade.

        This is the first step of cross-chain escrow — funds are locked
        on the source chain and can only be released by a bridge confirm
        (v0.9.0) or refunded by a bridge unlock.

        Returns the bridge transfer dict including ``transfer_id``.
        """
        result = await self._bridge.lock(
            target_chain=target_chain,
            sender=sender,
            recipient=recipient,
            amount=amount,
            asset=asset,
            signature=signature,
            source_chain=source_chain,
        )
        return result

    async def get_transfer_status(self, transfer_id: str) -> dict[str, Any]:
        """Get the status of a bridge transfer.

        Used to check if a locked escrow transfer has been confirmed on
        the destination chain (v0.9.0) or is still pending.
        """
        result = await self._bridge.get_transfer(transfer_id)
        return result

    async def list_pending_transfers(self, chain_id: str | None = None) -> list[dict[str, Any]]:
        """List pending bridge transfers.

        Useful for monitoring stuck transfers and for the matching engine
        to find trades that are awaiting confirmation.
        """
        return await self._bridge.list_pending(chain_id=chain_id)

    async def get_chain_balance(self, chain_id: str) -> dict[str, Any]:
        """Get the bridge balance for a chain.

        Returns the total locked amount for the specified chain.
        """
        result = await self._bridge.get_balance(chain_id)
        return result

    async def check_health(self) -> dict[str, Any]:
        """Check bridge health.

        Returns active transfer count, pending count, and configuration.
        """
        result = await self._bridge.health()
        return result

    async def close(self) -> None:
        """Close the underlying bridge client."""
        await self._bridge.close()
