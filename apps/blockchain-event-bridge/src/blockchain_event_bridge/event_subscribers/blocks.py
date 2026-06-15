"""Block event subscriber for gossip broker."""

import asyncio
from typing import TYPE_CHECKING

from aitbc.aitbc_logging import get_logger

from ..config import Settings
from ..metrics import event_queue_size, gossip_subscribers_total

if TYPE_CHECKING:
    from ..bridge import BlockchainEventBridge
logger = get_logger(__name__)


class BlockEventSubscriber:
    """Subscribes to block events from the gossip broker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._bridge: BlockchainEventBridge | None = None
        self._subscription = None

    def set_bridge(self, bridge: "BlockchainEventBridge") -> None:
        """Set the bridge instance for event handling."""
        self._bridge = bridge

    async def run(self) -> None:
        """Run the block event subscriber."""
        if self._running:
            logger.warning("Block event subscriber already running")
            return
        self._running = True
        logger.info("Starting block event subscriber...")
        try:
            from aitbc_chain.gossip.broker import GossipBroker, create_backend

            backend = create_backend(self.settings.gossip_backend, broadcast_url=self.settings.gossip_broadcast_url)
            self._broker = GossipBroker(backend)
            self._subscription = await self._broker.subscribe("blocks", max_queue_size=100)
            gossip_subscribers_total.set(1)
            logger.info("Successfully subscribed to blocks topic")
        except ImportError as e:
            logger.error("Failed to import gossip broker: %s", e)
            logger.info("Using mock implementation for development")
            await self._run_mock()
            return
        while self._running:
            try:
                block_data = await self._subscription.get()  # type: ignore[attr-defined]
                event_queue_size.labels(topic="blocks").set(self._subscription.queue.qsize())  # type: ignore[attr-defined]
                logger.info("Received block event: height=%s", block_data.get("height"))
                if self._bridge:
                    await self._bridge.handle_block_event(block_data)
            except asyncio.CancelledError:
                logger.info("Block event subscriber cancelled")
                break
            except Exception as e:
                logger.error("Error processing block event: %s", e, exc_info=True)
                await asyncio.sleep(1)

    async def _run_mock(self) -> None:
        """Run a mock subscriber for development/testing when gossip broker is unavailable."""
        logger.warning("Using mock block event subscriber - no real events will be processed")
        await asyncio.sleep(60)

    async def stop(self) -> None:
        """Stop the block event subscriber."""
        if not self._running:
            return
        logger.info("Stopping block event subscriber...")
        self._running = False
        if self._subscription:
            self._subscription.close()
        if hasattr(self, "_broker"):
            await self._broker.shutdown()
        gossip_subscribers_total.set(0)
        logger.info("Block event subscriber stopped")
