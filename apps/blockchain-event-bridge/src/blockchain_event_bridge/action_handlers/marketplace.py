"""Marketplace action handler for triggering marketplace state updates."""

import httpx
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MarketplaceHandler:
    """Handles actions that trigger marketplace state updates."""

    def __init__(self, coordinator_api_url: str, api_key: str | None = None) -> None:
        self.base_url = coordinator_api_url.rstrip("/")
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def handle_block(self, block_data: Dict[str, Any], transactions: List[Dict[str, Any]]) -> None:
        """Handle a new block by updating marketplace state."""
        logger.info(f"Processing block {block_data.get('height')} for marketplace updates")

        # Filter marketplace-related transactions
        marketplace_txs = self._filter_marketplace_transactions(transactions)

        if marketplace_txs:
            await self._sync_marketplace_state(marketplace_txs)

    def _filter_marketplace_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter transactions that affect marketplace state."""
        marketplace_txs = []

        for tx in transactions:
            tx_type = tx.get("type", "unknown")
            payload = tx.get("payload", {})

            # Check for marketplace-related transaction types
            if tx_type in ["marketplace", "listing", "purchase", "service"]:
                marketplace_txs.append(tx)
            elif isinstance(payload, dict):
                # Check for marketplace-related payload fields
                if any(key in payload for key in ["listing_id", "service_id", "marketplace"]):
                    marketplace_txs.append(tx)

        return marketplace_txs

    async def _sync_marketplace_state(self, transactions: List[Dict[str, Any]]) -> None:
        """Synchronize marketplace state with blockchain."""
        try:
            client = await self._get_client()

            # Send batch of marketplace transactions for processing
            response = await client.post(
                "/v1/marketplace/sync",
                json={"transactions": transactions}
            )
            response.raise_for_status()

            logger.info(f"Successfully synced {len(transactions)} marketplace transactions")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error syncing marketplace state: {e}")
        except Exception as e:
            logger.error(f"Error syncing marketplace state: {e}", exc_info=True)

    # Phase 2: Contract event handlers
    async def handle_contract_event(self, event_log: Dict[str, Any]) -> None:
        """Handle AgentServiceMarketplace contract event."""
        event_type = event_log.get("topics", [""])[0] if event_log.get("topics") else "Unknown"
        logger.info(f"Handling marketplace contract event: {event_type}")

        # Route based on event type
        if "ServiceListed" in event_type:
            await self._handle_service_listed(event_log)
        elif "ServicePurchased" in event_type:
            await self._handle_service_purchased(event_log)

    async def _handle_service_listed(self, event_log: Dict[str, Any]) -> None:
        """Handle ServiceListed event."""
        try:
            data = event_log.get("data", "{}")
            logger.info(f"ServiceListed event: {data}")

            # Call coordinator API to sync marketplace listing
            logger.info("Would call coordinator API marketplace service to sync listing")

        except Exception as e:
            logger.error(f"Error handling ServiceListed event: {e}", exc_info=True)

    async def _handle_service_purchased(self, event_log: Dict[str, Any]) -> None:
        """Handle ServicePurchased event."""
        try:
            data = event_log.get("data", "{}")
            logger.info(f"ServicePurchased event: {data}")

            # Call coordinator API to sync marketplace purchase
            logger.info("Would call coordinator API marketplace service to sync purchase")

        except Exception as e:
            logger.error(f"Error handling ServicePurchased event: {e}", exc_info=True)
