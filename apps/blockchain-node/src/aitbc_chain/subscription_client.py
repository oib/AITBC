"""Subscription client for follower nodes to receive block pushes from hub."""

import asyncio
import time
from typing import Any

import httpx
import websockets

from .config import settings
from .gossip import gossip_broker
from .logger import get_logger
from .metrics import metrics_registry
from .sync import ChainSync
from .database import session_scope

logger = get_logger(__name__)


class SubscriptionClient:
    """Client for follower nodes to subscribe to block pushes from hub."""

    def __init__(self, hub_url: str, node_id: str, chain_id: str):
        self._hub_url = hub_url.rstrip("/")
        self._node_id = node_id
        self._chain_id = chain_id
        self._transport = settings.subscription_transport
        self._lease_expiry = 0.0
        self._running = False
        self._client = httpx.AsyncClient(timeout=30.0)
        self._sync_mode = "pull"  # Track current sync mode

    async def start(self) -> None:
        """Start the subscription client."""
        if self._running:
            return

        self._running = True
        logger.info(f"Starting subscription client (transport={self._transport}, hub={self._hub_url})")

        # Start background tasks
        tasks = [
            asyncio.create_task(self._subscription_loop()),
            asyncio.create_task(self._heartbeat_loop()),
        ]

        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Subscription client error: {e}")
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the subscription client."""
        self._running = False
        await self._client.aclose()
        logger.info("Subscription client stopped")

    async def _subscribe(self) -> bool:
        """Register subscription with hub and get lease."""
        try:
            response = await self._client.post(
                f"{self._hub_url}/rpc/subscribe",
                json={
                    "node_id": self._node_id,
                    "transport": self._transport,
                    "chain_id": self._chain_id,
                }
            )
            response.raise_for_status()
            data = response.json()

            self._lease_expiry = data.get("expiry", 0.0)
            logger.info(f"Subscribed to hub, lease expires at {self._lease_expiry}")
            self._set_sync_mode("push")
            return True
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            self._set_sync_mode("pull")
            return False

    async def _heartbeat(self) -> bool:
        """Send heartbeat to extend lease."""
        try:
            response = await self._client.post(
                f"{self._hub_url}/rpc/heartbeat",
                json={"node_id": self._node_id}
            )
            response.raise_for_status()
            data = response.json()

            self._lease_expiry = data.get("expiry", 0.0)
            logger.debug(f"Heartbeat successful, lease extended to {self._lease_expiry}")
            return True
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
            return False

    async def _subscription_loop(self) -> None:
        """Main subscription loop to receive blocks."""
        while self._running:
            try:
                # Subscribe to hub
                if not await self._subscribe():
                    logger.warning("Subscription failed, retrying in 30s")
                    await asyncio.sleep(30)
                    continue

                # Receive blocks based on transport
                if self._transport == "websocket":
                    await self._receive_via_websocket()
                elif self._transport == "http":
                    await self._receive_via_http_poll()
                elif self._transport == "redis":
                    await self._receive_via_redis()
                else:
                    logger.error(f"Unknown transport: {self._transport}")
                    await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Subscription loop error: {e}")
                self._set_sync_mode("pull")
                await asyncio.sleep(30)

    async def _heartbeat_loop(self) -> None:
        """Heartbeat loop to extend lease."""
        while self._running:
            try:
                await asyncio.sleep(settings.heartbeat_interval)

                # Check if lease needs renewal
                now = time.time()
                time_until_expiry = self._lease_expiry - now

                # Log lease status
                if self._lease_expiry > 0:
                    logger.info(f"Lease status: {time_until_expiry:.0f}s remaining, sync_mode={self._sync_mode}")
                    metrics_registry.set_gauge("lease_remaining_seconds", time_until_expiry)

                if time_until_expiry < settings.lease_renewal_threshold:
                    logger.warning(f"Lease expires in {time_until_expiry:.0f}s, renewing")
                    if not await self._heartbeat():
                        logger.warning("Heartbeat failed, will retry")
                        self._set_sync_mode("pull")
                else:
                    # Send regular heartbeat to extend lease
                    await self._heartbeat()

            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")

    async def _receive_via_websocket(self) -> None:
        """Receive blocks via WebSocket."""
        ws_url = self._hub_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/rpc/subscribe/ws"

        logger.info(f"Connecting to WebSocket: {ws_url}")

        while self._running:
            try:
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=10
                ) as websocket:
                    logger.info("WebSocket connected successfully")
                    self._set_sync_mode("push")

                    # Send subscription message
                    import json
                    await websocket.send(json.dumps({
                        "node_id": self._node_id,
                        "chain_id": self._chain_id,
                        "transport": "websocket"
                    }))

                    # Receive blocks
                    async for message in websocket:
                        if not self._running:
                            break

                        try:
                            if isinstance(message, str):
                                block_data = json.loads(message)
                            else:
                                block_data = message

                            # Import the block
                            await self._import_block(block_data)

                        except Exception as e:
                            logger.error(f"Error processing WebSocket message: {e}")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}, reconnecting...")
                self._set_sync_mode("pull")
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"WebSocket error: {e}, falling back to pull")
                self._set_sync_mode("pull")
                await asyncio.sleep(30)
                break

    async def _receive_via_http_poll(self) -> None:
        """Receive blocks via HTTP long-polling (placeholder for future implementation)."""
        logger.info("HTTP long-poll transport not yet implemented, falling back to pull")
        self._set_sync_mode("pull")
        await asyncio.sleep(30)

    async def _receive_via_redis(self) -> None:
        """Receive blocks via Redis pub/sub (existing gossip mechanism)."""
        try:
            topic = f"blocks.{self._chain_id}"
            logger.info(f"Subscribing to Redis topic: {topic}")

            block_sub = await gossip_broker.subscribe(topic)
            logger.info(f"Successfully subscribed to {topic}")

            async for block_data in block_sub:
                if not self._running:
                    break

                if isinstance(block_data, str):
                    import json
                    block_data = json.loads(block_data)

                # Import the block
                await self._import_block(block_data)

        except Exception as e:
            logger.error(f"Redis subscription error: {e}")
            self._set_sync_mode("pull")

    async def _import_block(self, block_data: dict[str, Any]) -> None:
        """Import a received block."""
        try:
            sync = ChainSync(
                session_factory=lambda cid=self._chain_id: session_scope(cid),
                chain_id=self._chain_id
            )
            result = sync.import_block(block_data, transactions=block_data.get("transactions"))

            if result.accepted:
                logger.info(f"Imported block {block_data.get('height')} via push")
                metrics_registry.increment("subscription_blocks_received_total")
            else:
                logger.warning(f"Block import failed: {result.reason}")

        except Exception as e:
            logger.error(f"Failed to import block: {e}")

    def _set_sync_mode(self, mode: str) -> None:
        """Set and log sync mode."""
        if self._sync_mode != mode:
            self._sync_mode = mode
            logger.info(f"Sync mode changed to: {mode}")
            metrics_registry.set_gauge("sync_mode", 1.0 if mode == "push" else 0.0)

    def get_lease_remaining(self) -> int:
        """Get remaining lease time in seconds."""
        return int(max(0, self._lease_expiry - time.time()))

    def get_sync_mode(self) -> str:
        """Get current sync mode."""
        return self._sync_mode
