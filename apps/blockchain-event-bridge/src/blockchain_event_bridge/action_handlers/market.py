"""Market action handler for triggering market state updates."""

from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.network import AsyncAITBCHTTPClient

logger = get_logger(__name__)


class MarketHandler:
    """Handles actions that trigger market state updates."""

    def __init__(self, coordinator_api_url: str, api_key: str | None = None) -> None:
        self.base_url = coordinator_api_url.rstrip("/")
        self.api_key = api_key
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client: AsyncAITBCHTTPClient | None = None
        self._headers = headers

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def handle_block(self, block_data: dict[str, Any], transactions: list[dict[str, Any]]) -> None:
        """Handle a new block by updating market state."""
        logger.info("Processing block %s for market updates", block_data.get("height"))
        market_txs = self._filter_market_transactions(transactions)
        if market_txs:
            await self._sync_market_state(market_txs)

    def _filter_market_transactions(self, transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter transactions that affect market state."""
        market_txs = []
        for tx in transactions:
            tx_type = tx.get("type", "unknown")
            payload = tx.get("payload", {})
            if tx_type in ["market", "listing", "purchase", "service"]:
                market_txs.append(tx)
            elif isinstance(payload, dict):
                if any(key in payload for key in ["listing_id", "service_id", "market"]):
                    market_txs.append(tx)
        return market_txs

    async def _sync_market_state(self, transactions: list[dict[str, Any]]) -> None:
        """Synchronize market state with blockchain.

        coordinator-api has no transaction-ingest endpoint (the old
        ``/v1/market/sync`` never existed — ``/v1/market/sync-offers``
        is an unrelated admin action), so matching events are logged like the
        other handlers in this module until a real sync route exists.
        """
        logger.info("Would sync %s market transactions to coordinator API", len(transactions))

    async def handle_contract_event(self, event_log: dict[str, Any]) -> None:
        """Handle AgentServiceMarket contract event."""
        event_type = event_log.get("topics", [""])[0] if event_log.get("topics") else "Unknown"
        logger.info("Handling market contract event: %s", event_type)
        if "ServiceListed" in event_type:
            await self._handle_service_listed(event_log)
        elif "ServicePurchased" in event_type:
            await self._handle_service_purchased(event_log)

    async def _handle_service_listed(self, event_log: dict[str, Any]) -> None:
        """Handle ServiceListed event."""
        try:
            data = event_log.get("data", "{}")
            logger.info("ServiceListed event: %s", data)
            logger.info("Would call coordinator API market service to sync listing")
        except Exception as e:
            logger.error("Error handling ServiceListed event: %s", e, exc_info=True)

    async def _handle_service_purchased(self, event_log: dict[str, Any]) -> None:
        """Handle ServicePurchased event."""
        try:
            data = event_log.get("data", "{}")
            logger.info("ServicePurchased event: %s", data)
            logger.info("Would call coordinator API market service to sync purchase")
        except Exception as e:
            logger.error("Error handling ServicePurchased event: %s", e, exc_info=True)
