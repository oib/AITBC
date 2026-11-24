"""Coordinator API action handler for triggering agent actions."""

import re
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AsyncAITBCHTTPClient

logger = get_logger(__name__)

# Path-segment allowlist for IDs interpolated into coordinator-api URLs.
# job_id/listing_id/to come from sealed on-chain payloads — any tx submitter
# controls them. Raw interpolation lets ``/``, ``?``, ``#``, ``%`` and
# dot-segments rewrite the request path against an API that carries the
# bridge's bearer key. Percent-encoding is NOT sufficient (%2F decodes to
# ``/`` downstream), so unsafe values are dropped instead. Legit IDs —
# 0x addresses, tx hashes, listing_NNN, UUIDs — all match.
_SAFE_PATH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def _path_id(value: Any) -> str | None:
    """Return ``value`` as a URL-path-safe segment, or None if unsafe."""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    s = str(value)
    return s if _SAFE_PATH_ID.fullmatch(s) else None


class CoordinatorAPIHandler:
    """Handles actions that trigger coordinator API endpoints."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client: AsyncAITBCHTTPClient | None = None
        self._headers = headers

    def _get_client(self) -> AsyncAITBCHTTPClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = AsyncAITBCHTTPClient(base_url=self.base_url, headers=self._headers, timeout=30)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def handle_block(self, block_data: dict[str, Any], transactions: list[dict[str, Any]]) -> None:
        """Handle a new block by triggering coordinator API actions."""
        logger.info("Handling block %s with %s transactions", block_data.get("height"), len(transactions))
        for tx in transactions:
            await self.handle_transaction(tx)

    async def handle_transaction(self, tx_data: dict[str, Any]) -> None:
        """Handle a single transaction."""
        tx_type = tx_data.get("type", "unknown")
        tx_hash = tx_data.get("hash", "unknown")
        logger.info("Handling transaction %s of type %s", tx_hash, tx_type)
        if tx_type == "ai_job":
            await self._trigger_ai_job_processing(tx_data)
        elif tx_type == "agent_message":
            await self._trigger_agent_message_processing(tx_data)
        elif tx_type == "market":
            await self._trigger_market_update(tx_data)

    async def _trigger_ai_job_processing(self, tx_data: dict[str, Any]) -> None:
        """Trigger AI job processing via coordinator API."""
        try:
            client = self._get_client()
            payload = tx_data.get("payload", {})
            job_id = _path_id(payload.get("job_id"))
            if job_id is None and payload.get("job_id"):
                logger.warning("Skipping AI job notify: unsafe job_id in tx %s", tx_data.get("hash", "unknown"))
            if job_id:
                await client.post(f"/v1/ai-jobs/{job_id}/notify", json=tx_data)
                logger.info("Successfully notified coordinator about AI job %s", job_id)
        except NetworkError as e:
            logger.error("Network error triggering AI job processing: %s", e)
        except Exception as e:
            logger.error("Error triggering AI job processing: %s", e, exc_info=True)

    async def _trigger_agent_message_processing(self, tx_data: dict[str, Any]) -> None:
        """Trigger agent message processing via coordinator API."""
        try:
            client = self._get_client()
            payload = tx_data.get("payload", {})
            recipient = _path_id(tx_data.get("to"))
            if recipient is None and tx_data.get("to"):
                logger.warning("Skipping agent message notify: unsafe recipient in tx %s", tx_data.get("hash", "unknown"))
            if recipient:
                await client.post(f"/v1/agents/{recipient}/message", json={"transaction": tx_data, "payload": payload})
                logger.info("Successfully notified coordinator about message to %s", recipient)
        except NetworkError as e:
            logger.error("Network error triggering agent message processing: %s", e)
        except Exception as e:
            logger.error("Error triggering agent message processing: %s", e, exc_info=True)

    async def _trigger_market_update(self, tx_data: dict[str, Any]) -> None:
        """Trigger market state update via coordinator API."""
        try:
            client = self._get_client()
            payload = tx_data.get("payload", {})
            listing_id = _path_id(payload.get("listing_id"))
            if listing_id is None and payload.get("listing_id"):
                logger.warning("Skipping market sync: unsafe listing_id in tx %s", tx_data.get("hash", "unknown"))
            if listing_id:
                await client.post(f"/v1/market/{listing_id}/sync", json={"transaction": tx_data})
                logger.info("Successfully updated market listing %s", listing_id)
        except NetworkError as e:
            logger.error("Network error triggering market update: %s", e)
        except Exception as e:
            logger.error("Error triggering market update: %s", e, exc_info=True)
