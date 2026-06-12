"""Coordinator API action handler for triggering hermes agent actions."""
from typing import Any
from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network.http_client import AsyncAITBCHTTPClient
logger = get_logger(__name__)

class CoordinatorAPIHandler:
    """Handles actions that trigger coordinator API endpoints."""

    def __init__(self, base_url: str, api_key: str | None=None) -> None:
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        self._client: AsyncAITBCHTTPClient | None = None
        self._headers = headers

    async def _get_client(self) -> AsyncAITBCHTTPClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = AsyncAITBCHTTPClient(base_url=self.base_url, headers=self._headers, timeout=30)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        self._client = None

    async def handle_block(self, block_data: dict[str, Any], transactions: list[dict[str, Any]]) -> None:
        """Handle a new block by triggering coordinator API actions."""
        logger.info('Handling block %s with %s transactions', block_data.get('height'), len(transactions))
        for tx in transactions:
            await self.handle_transaction(tx)

    async def handle_transaction(self, tx_data: dict[str, Any]) -> None:
        """Handle a single transaction."""
        tx_type = tx_data.get('type', 'unknown')
        tx_hash = tx_data.get('hash', 'unknown')
        logger.info('Handling transaction %s of type %s', tx_hash, tx_type)
        if tx_type == 'ai_job':
            await self._trigger_ai_job_processing(tx_data)
        elif tx_type == 'agent_message':
            await self._trigger_agent_message_processing(tx_data)
        elif tx_type == 'marketplace':
            await self._trigger_marketplace_update(tx_data)

    async def _trigger_ai_job_processing(self, tx_data: dict[str, Any]) -> None:
        """Trigger AI job processing via coordinator API."""
        try:
            client = await self._get_client()
            payload = tx_data.get('payload', {})
            job_id = payload.get('job_id')
            if job_id:
                await client.async_post(f'/v1/ai-jobs/{job_id}/notify', json=tx_data)
                logger.info('Successfully notified coordinator about AI job %s', job_id)
        except NetworkError as e:
            logger.error('Network error triggering AI job processing: %s', e)
        except Exception as e:
            logger.error('Error triggering AI job processing: %s', e, exc_info=True)

    async def _trigger_agent_message_processing(self, tx_data: dict[str, Any]) -> None:
        """Trigger agent message processing via coordinator API."""
        try:
            client = await self._get_client()
            payload = tx_data.get('payload', {})
            recipient = tx_data.get('to')
            if recipient:
                await client.async_post(f'/v1/agents/{recipient}/message', json={'transaction': tx_data, 'payload': payload})
                logger.info('Successfully notified coordinator about message to %s', recipient)
        except NetworkError as e:
            logger.error('Network error triggering agent message processing: %s', e)
        except Exception as e:
            logger.error('Error triggering agent message processing: %s', e, exc_info=True)

    async def _trigger_marketplace_update(self, tx_data: dict[str, Any]) -> None:
        """Trigger marketplace state update via coordinator API."""
        try:
            client = await self._get_client()
            payload = tx_data.get('payload', {})
            listing_id = payload.get('listing_id')
            if listing_id:
                await client.async_post(f'/v1/marketplace/{listing_id}/sync', json={'transaction': tx_data})
                logger.info('Successfully updated marketplace listing %s', listing_id)
        except NetworkError as e:
            logger.error('Network error triggering marketplace update: %s', e)
        except Exception as e:
            logger.error('Error triggering marketplace update: %s', e, exc_info=True)