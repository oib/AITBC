"""Batch processing for aggregated operations."""

import asyncio
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Processes events in batches for efficiency."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._running = False
        self._batch_queue: List[Dict[str, Any]] = []
        self._batch_size = 50

    async def run(self) -> None:
        """Run the batch processor."""
        if not self.settings.enable_polling:
            logger.info("Batch processing disabled")
            return

        self._running = True
        logger.info("Starting batch processor...")

        while self._running:
            try:
                await self._process_batch()
                await asyncio.sleep(self.settings.polling_interval_seconds)
            except asyncio.CancelledError:
                logger.info("Batch processor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in batch processor: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def add_to_batch(self, event: Dict[str, Any]) -> None:
        """Add an event to the batch queue."""
        self._batch_queue.append(event)

        if len(self._batch_queue) >= self._batch_size:
            await self._process_batch()

    async def _process_batch(self) -> None:
        """Process the current batch of events."""
        if not self._batch_queue:
            return

        batch = self._batch_queue.copy()
        self._batch_queue.clear()

        logger.info(f"Processing batch of {len(batch)} events")

        # Placeholder for Phase 3 implementation
        # Examples:
        # - Batch agent reputation updates
        # - Batch marketplace state synchronization
        # - Batch performance metric aggregation

    async def stop(self) -> None:
        """Stop the batch processor."""
        self._running = False

        # Process remaining events
        if self._batch_queue:
            await self._process_batch()

        logger.info("Batch processor stopped")
