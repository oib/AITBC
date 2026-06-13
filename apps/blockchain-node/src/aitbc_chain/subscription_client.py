"""Subscription client for follower nodes to receive block pushes from hub."""
import asyncio
import time
from typing import Any
import httpx
import websockets
from .config import settings
from .database import session_scope
from .gossip import gossip_broker
from .logger import get_logger
from .metrics import metrics_registry
from .sync import ChainSync
logger = get_logger(__name__)

class SubscriptionClient:
    """Client for follower nodes to subscribe to block pushes from hub."""

    def __init__(self, hub_url: str, node_id: str, chain_id: str):
        self._hub_url = hub_url.rstrip('/')
        self._node_id = node_id
        self._chain_id = chain_id
        self._transport = settings.subscription_transport
        self._lease_expiry = 0.0
        self._running = False
        self._client = httpx.AsyncClient(timeout=30.0)
        self._sync_mode = 'pull'

    async def start(self) -> None:
        """Start the subscription client."""
        if self._running:
            return
        self._running = True
        logger.info('Starting subscription client (transport=%s, hub=%s)', self._transport, self._hub_url)
        tasks = [asyncio.create_task(self._subscription_loop()), asyncio.create_task(self._heartbeat_loop())]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error('Subscription client error: %s', e)
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the subscription client."""
        self._running = False
        await self._client.aclose()
        logger.info('Subscription client stopped')

    async def _subscribe(self) -> bool:
        """Register subscription with hub and get lease."""
        try:
            response = await self._client.post(f'{self._hub_url}/rpc/subscribe', json={'node_id': self._node_id, 'transport': self._transport, 'chain_id': self._chain_id})
            response.raise_for_status()
            data = response.json()
            self._lease_expiry = data.get('expiry', 0.0)
            logger.info('Subscribed to hub, lease expires at %s', self._lease_expiry)
            self._set_sync_mode('push')
            return True
        except Exception as e:
            logger.error('Failed to subscribe: %s', e)
            self._set_sync_mode('pull')
            return False

    async def _heartbeat(self) -> bool:
        """Send heartbeat to extend lease."""
        try:
            response = await self._client.post(f'{self._hub_url}/rpc/heartbeat', json={'node_id': self._node_id})
            response.raise_for_status()
            data = response.json()
            self._lease_expiry = data.get('expiry', 0.0)
            logger.debug('Heartbeat successful, lease extended to %s', self._lease_expiry)
            return True
        except Exception as e:
            logger.error('Failed to send heartbeat: %s', e)
            return False

    async def _subscription_loop(self) -> None:
        """Main subscription loop to receive blocks."""
        while self._running:
            try:
                if not await self._subscribe():
                    logger.warning('Subscription failed, retrying in 30s')
                    await asyncio.sleep(30)
                    continue
                if self._transport == 'websocket':
                    await self._receive_via_websocket()
                elif self._transport == 'http':
                    await self._receive_via_http_poll()
                elif self._transport == 'redis':
                    await self._receive_via_redis()
                else:
                    logger.error('Unknown transport: %s', self._transport)
                    await asyncio.sleep(30)
            except Exception as e:
                logger.error('Subscription loop error: %s', e)
                self._set_sync_mode('pull')
                await asyncio.sleep(30)

    async def _heartbeat_loop(self) -> None:
        """Heartbeat loop to extend lease."""
        while self._running:
            try:
                await asyncio.sleep(settings.heartbeat_interval)
                now = time.time()
                time_until_expiry = self._lease_expiry - now
                if self._lease_expiry > 0:
                    logger.info('Lease status: %ss remaining, sync_mode=%s', time_until_expiry, self._sync_mode)
                    metrics_registry.set_gauge('lease_remaining_seconds', time_until_expiry)
                if time_until_expiry < settings.lease_renewal_threshold:
                    logger.warning('Lease expires in %ss, renewing', time_until_expiry)
                    if not await self._heartbeat():
                        logger.warning('Heartbeat failed, will retry')
                        self._set_sync_mode('pull')
                else:
                    await self._heartbeat()
            except Exception as e:
                logger.error('Heartbeat loop error: %s', e)

    async def _receive_via_websocket(self) -> None:
        """Receive blocks via WebSocket."""
        ws_url = self._hub_url.replace('http://', 'ws://').replace('https://', 'wss://')
        ws_url = f'{ws_url}/rpc/subscribe/ws'
        logger.info('Connecting to WebSocket: %s', ws_url)
        while self._running:
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=30, close_timeout=10) as websocket:
                    logger.info('WebSocket connected successfully')
                    self._set_sync_mode('push')
                    import json
                    await websocket.send(json.dumps({'node_id': self._node_id, 'chain_id': self._chain_id, 'transport': 'websocket'}))
                    async for message in websocket:
                        try:
                            if isinstance(message, str):
                                block_data = json.loads(message)
                            else:
                                block_data = message
                            if not isinstance(block_data, dict) or 'height' not in block_data:
                                logger.debug('Skipping non-block message: %s', list(block_data.keys()) if isinstance(block_data, dict) else type(block_data))
                                continue
                            await self._import_block(block_data)
                        except Exception as e:
                            logger.error('Error processing WebSocket message: %s', e)
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning('WebSocket connection closed: %s, reconnecting...', e)
                self._set_sync_mode('pull')
                await asyncio.sleep(5)
            except Exception as e:
                logger.error('WebSocket error: %s, falling back to pull', e)
                self._set_sync_mode('pull')
                await asyncio.sleep(30)
                break

    async def _receive_via_http_poll(self) -> None:
        """Receive blocks via HTTP long-polling (placeholder for future implementation)."""
        logger.info('HTTP long-poll transport not yet implemented, falling back to pull')
        self._set_sync_mode('pull')
        await asyncio.sleep(30)

    async def _receive_via_redis(self) -> None:
        """Receive blocks via Redis pub/sub (existing gossip mechanism)."""
        try:
            topic = f'blocks.{self._chain_id}'
            logger.info('Subscribing to Redis topic: %s', topic)
            block_sub = await gossip_broker.subscribe(topic)
            logger.info('Successfully subscribed to %s', topic)
            async for block_data in block_sub:
                if not self._running:
                    break
                if isinstance(block_data, str):
                    import json
                    block_data = json.loads(block_data)
                await self._import_block(block_data)
        except Exception as e:
            logger.error('Redis subscription error: %s', e)
            self._set_sync_mode('pull')

    async def _import_block(self, block_data: dict[str, Any]) -> None:
        """Import a received block."""
        try:
            sync = ChainSync(session_factory=lambda: session_scope(self._chain_id), chain_id=self._chain_id)  # type: ignore[arg-type, return-value]
            result = sync.import_block(block_data, transactions=block_data.get('transactions'))
            if result.accepted:
                logger.info('Imported block %s via push', block_data.get('height'))
                metrics_registry.increment('subscription_blocks_received_total')
            else:
                logger.warning('Block import failed: %s', result.reason)
        except Exception as e:
            logger.error('Failed to import block: %s', e)

    def _set_sync_mode(self, mode: str) -> None:
        """Set and log sync mode."""
        if self._sync_mode != mode:
            self._sync_mode = mode
            logger.info('Sync mode changed to: %s', mode)
            metrics_registry.set_gauge('sync_mode', 1.0 if mode == 'push' else 0.0)

    def get_lease_remaining(self) -> int:
        """Get remaining lease time in seconds."""
        return int(max(0, self._lease_expiry - time.time()))

    def get_sync_mode(self) -> str:
        """Get current sync mode."""
        return self._sync_mode