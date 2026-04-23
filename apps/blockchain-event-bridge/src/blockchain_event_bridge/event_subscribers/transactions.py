"""Transaction event subscriber for gossip broker."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict

from ..config import Settings
from ..metrics import event_queue_size, gossip_subscribers_total

if TYPE_CHECKING:
    from ..bridge import BlockchainEventBridge


logger = logging.getLogger(__name__)


class TransactionEventSubscriber:
    """Subscribes to transaction events from the gossip broker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._bridge: "BlockchainEventBridge | None" = None
        self._subscription = None

    def set_bridge(self, bridge: "BlockchainEventBridge") -> None:
        """Set the bridge instance for event handling."""
        self._bridge = bridge

    async def run(self) -> None:
        """Run the transaction event subscriber."""
        if self._running:
            logger.warning("Transaction event subscriber already running")
            return

        self._running = True
        logger.info("Starting transaction event subscriber...")

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

            # Subscribe to transactions topic (if available)
            # Note: Currently transactions are embedded in block events
            # This subscriber will be enhanced when transaction events are published separately
            try:
                self._subscription = await self._broker.subscribe("transactions", max_queue_size=100)
                gossip_subscribers_total.inc()
                logger.info("Successfully subscribed to transactions topic")
            except Exception:
                logger.info("Transactions topic not available - will extract from block events")
                await self._run_mock()
                return

        except ImportError as e:
            logger.error(f"Failed to import gossip broker: {e}")
            logger.info("Using mock implementation for development")
            await self._run_mock()
            return

        # Process transaction events
        while self._running:
            try:
                tx_data = await self._subscription.get()
                event_queue_size.labels(topic="transactions").set(self._subscription.queue.qsize())

                logger.info(f"Received transaction event: hash={tx_data.get('hash')}")

                if self._bridge:
                    await self._bridge.handle_transaction_event(tx_data)

            except asyncio.CancelledError:
                logger.info("Transaction event subscriber cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing transaction event: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _run_mock(self) -> None:
        """Run a mock subscriber for development/testing."""
        logger.warning("Using mock transaction event subscriber - no real events will be processed")
        await asyncio.sleep(60)

    async def stop(self) -> None:
        """Stop the transaction event subscriber."""
        if not self._running:
            return

        logger.info("Stopping transaction event subscriber...")
        self._running = False

        if self._subscription:
            self._subscription.close()

        if hasattr(self, '_broker'):
            await self._broker.shutdown()

        gossip_subscribers_total.dec()
        logger.info("Transaction event subscriber stopped")
