"""Transaction event subscriber for gossip broker."""

import asyncio
from typing import TYPE_CHECKING, Any, Protocol, cast
from collections.abc import Awaitable

from aitbc.aitbc_logging import get_logger

from ..config import Settings
from ..metrics import event_queue_size, gossip_subscribers_total
from ._resubscribe import read_gossip_with_recovery

if TYPE_CHECKING:
    from ..bridge import BlockchainEventBridge

logger = get_logger(__name__)

# Subscriber failure surface: gossip broker subscribe/queue errors and the
# event-payload data-shape errors the bridge handler can raise.
_OPS_ERRORS = (
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ArithmeticError,
    TimeoutError,
)


class SubscriptionProtocol(Protocol):
    async def get(self) -> dict[str, Any]: ...
    @property
    def queue(self) -> "asyncio.Queue[object]": ...
    def close(self) -> None: ...


class TransactionEventSubscriber:
    """Subscribes to transaction events from the gossip broker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._bridge: BlockchainEventBridge | None = None
        self._subscription: SubscriptionProtocol | None = None
        self._broker: Any = None
        self._topic: str = "transactions"

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
        if not await self._connect_gossip():
            return
        while self._running:
            outcome = await read_gossip_with_recovery(
                self._broker,
                self._topic,
                self._subscription,
                label="Transaction",
                max_queue_size=100,
            )
            self._subscription = outcome.subscription
            if outcome.kind == "cancelled":
                break
            if outcome.kind == "retry":
                continue
            await self._handle_transaction_message(outcome.message or {})

    async def _connect_gossip(self) -> bool:
        try:
            from aitbc_chain.gossip import GossipBroker, create_backend

            backend = create_backend(self.settings.gossip_backend, broadcast_url=self.settings.gossip_broadcast_url)
            self._broker = GossipBroker(backend)
            try:
                self._subscription = await cast(
                    Awaitable[Any],
                    self._broker.subscribe("transactions", max_queue_size=100),
                )
                gossip_subscribers_total.inc()
                logger.info("Successfully subscribed to transactions topic")
                return True
            except _OPS_ERRORS:
                logger.info("Transactions topic not available - will extract from block events")
                await self._run_mock()
                return False
        except ImportError as e:
            logger.error("Failed to import gossip broker: %s", e)
            logger.info("Using mock implementation for development")
            await self._run_mock()
            return False

    async def _handle_transaction_message(self, tx_data: dict[str, Any]) -> None:
        try:
            if self._subscription is None:
                return
            event_queue_size.labels(topic="transactions").set(self._subscription.queue.qsize())  # noqa: unawaited-async
            logger.info("Received transaction event: hash=%s", tx_data.get("hash"))
            if self._bridge:
                await self._bridge.handle_transaction_event(tx_data)
        except _OPS_ERRORS as e:
            logger.error("Error processing transaction event: %s", e, exc_info=True)
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
            self._subscription.close()  # noqa: unawaited-async — SubscriptionProtocol.close() is synchronous
        if self._broker is not None:
            await self._broker.shutdown()
        gossip_subscribers_total.dec()
        logger.info("Transaction event subscriber stopped")
