"""Block event subscriber for gossip broker."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict

from ..config import Settings
from ..metrics import event_queue_size, gossip_subscribers_total

if TYPE_CHECKING:
    from ..bridge import BlockchainEventBridge


logger = logging.getLogger(__name__)


class BlockEventSubscriber:
    """Subscribes to block events from the gossip broker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._bridge: "BlockchainEventBridge | None" = None
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

        # Import gossip broker from blockchain-node
        try:
            # Add blockchain-node to path for import
            import sys
            from pathlib import Path
            blockchain_node_src = Path("/opt/aitbc/apps/blockchain-node/src")
            if str(blockchain_node_src) not in sys.path:
                sys.path.insert(0, str(blockchain_node_src))

            from aitbc_chain.gossip.broker import create_backend, GossipBroker

            # Create gossip backend
            backend = create_backend(
                self.settings.gossip_backend,
                broadcast_url=self.settings.gossip_broadcast_url
            )
            self._broker = GossipBroker(backend)

            # Subscribe to blocks topic
            self._subscription = await self._broker.subscribe("blocks", max_queue_size=100)
            gossip_subscribers_total.set(1)

            logger.info("Successfully subscribed to blocks topic")

        except ImportError as e:
            logger.error(f"Failed to import gossip broker: {e}")
            logger.info("Using mock implementation for development")
            await self._run_mock()
            return

        # Process block events
        while self._running:
            try:
                block_data = await self._subscription.get()
                event_queue_size.labels(topic="blocks").set(self._subscription.queue.qsize())

                logger.info(f"Received block event: height={block_data.get('height')}")

                if self._bridge:
                    await self._bridge.handle_block_event(block_data)

            except asyncio.CancelledError:
                logger.info("Block event subscriber cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing block event: {e}", exc_info=True)
                await asyncio.sleep(1)  # Avoid tight error loop

    async def _run_mock(self) -> None:
        """Run a mock subscriber for development/testing when gossip broker is unavailable."""
        logger.warning("Using mock block event subscriber - no real events will be processed")
        await asyncio.sleep(60)  # Keep alive but do nothing

    async def stop(self) -> None:
        """Stop the block event subscriber."""
        if not self._running:
            return

        logger.info("Stopping block event subscriber...")
        self._running = False

        if self._subscription:
            self._subscription.close()

        if hasattr(self, '_broker'):
            await self._broker.shutdown()

        gossip_subscribers_total.set(0)
        logger.info("Block event subscriber stopped")
