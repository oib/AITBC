"""Bridge RPC client for the trading service (v0.8.0 §B3).

Wraps ``TradingBridgeClient`` from ``aitbc.trading.bridge`` (Agent A's A3)
for trading-specific bridge operations. The trading service uses this to
lock escrow on the source chain, verify transfer status, and query
bridge balances when facilitating inter-chain trades.

v0.8.0 only uses lock + transfer status + balance + health.
Atomic settlement (confirm + unlock with HTLC) is deferred to v0.9.0.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.trading.bridge import TradingBridgeClient

logger = logging.getLogger(__name__)


class BridgeClient:
    """Bridge client for inter-chain trading operations.

    Wraps ``TradingBridgeClient`` (which wraps ``BridgeClient`` from
    ``aitbc.bridge``) to provide a simplified interface for the trading
    service.
    """

    def __init__(self, bridge_rpc_url: str = "http://localhost:8202", timeout: float = 10.0) -> None:
        from aitbc.trading.types import TradingConfig

        config = TradingConfig(bridge_rpc_url=bridge_rpc_url)
        self._timeout = timeout
        self._bridge = TradingBridgeClient(config=config)

    async def lock_escrow(
        self,
        source_chain: str,
        amount: int,
        sender: str,
        recipient: str,
        target_chain: str = "",
        asset: str = "native",
        signature: str = "",
    ) -> dict[str, Any]:
        """Lock funds in escrow on the source chain.

        Calls POST /bridge/lock. Returns the transfer dict including
        transfer_id. The actual escrow locking is deferred to v0.9.0
        (atomic settlement) — v0.8.0 records the intent.
        """
        return await self._bridge.lock_escrow(
            source_chain=source_chain,
            target_chain=target_chain,
            sender=sender,
            recipient=recipient,
            amount=amount,
            asset=asset,
            signature=signature,
        )

    async def get_transfer_status(self, transfer_id: str) -> dict[str, Any]:
        """Get the status of a bridge transfer."""
        return await self._bridge.get_transfer_status(transfer_id)

    async def get_chain_balance(self, chain_id: str) -> dict[str, Any]:
        """Get the bridge balance for a chain."""
        return await self._bridge.get_chain_balance(chain_id)

    async def check_health(self) -> dict[str, Any]:
        """Check bridge health."""
        return await self._bridge.check_health()

    async def close(self) -> None:
        """Close the underlying bridge client."""
        await self._bridge.close()
