"""Reward distribution scheduler (#3058).

Drives the previously dead pipeline: every ``interval_seconds`` it reads
the sealed chain height, takes the single-active-distributor lock, runs
the payout reconciliation sweep, then distributes the last finalized
epoch's verified shares.

Started from the app lifespan ONLY when ``enable_reward_distribution``
is set AND ``reward_enablement_blockers`` returns empty — the flag alone
never starts money movement.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ..clients.blockchain import PoolHubBlockchainClient
from ..settings import Settings
from .distributor_lock import distributor_lock

logger = logging.getLogger(__name__)


class RewardDistributionScheduler:
    """Periodic reward reconcile + distribute loop, single-writer per cycle."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        engine: AsyncEngine,
        client_factory: Callable[[], PoolHubBlockchainClient],
        interval_seconds: float,  # seconds, not money — int settings values are fine
    ) -> None:
        self._session_factory = session_factory
        self._engine = engine
        self._client_factory = client_factory
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="poolhub-reward-distribution")
        logger.info("Reward distribution scheduler started (interval=%ss)", self._interval)

    async def stop(self) -> None:
        self._stop.set()  # noqa: unawaited-async - asyncio.Event.set() is synchronous
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def run_once(self) -> None:
        """One reconcile+distribute cycle under the distributor lock."""
        client = self._client_factory()
        try:
            height = await client.rpc_client.get_chain_height(chain_id=client.chain_id)
        except Exception as e:  # noqa: BLE001 - a height-probe failure skips the cycle, never guesses
            logger.warning("Reward cycle skipped: chain height probe failed: %s", e)
            return
        async with distributor_lock(self._engine) as active:
            if not active:
                logger.debug("Reward cycle skipped: another replica holds the distributor lock")
                return
            async with self._session_factory() as session:
                try:
                    summary = await client.reconcile_payouts(session)
                    if summary.get("checked"):
                        logger.info("Reward reconciliation summary: %s", summary)
                    payouts = await client.distribute_rewards(height, session)
                    paid = [p for p in payouts if p.get("status") == "paid"]
                    if paid:
                        logger.info("Reward distribution paid %d miner(s) at height %s", len(paid), height)
                except Exception:
                    logger.exception("Reward distribution cycle failed")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Reward distribution cycle crashed; continuing")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                pass


def build_reward_client(settings: Settings) -> PoolHubBlockchainClient:
    """Construct the payout client from settings (operator-configured)."""
    return PoolHubBlockchainClient(
        rpc_url=settings.blockchain_rpc_url,
        chain_id=settings.default_chain_id,
        api_key=settings.blockchain_rpc_api_key,
        finality_confirmations=settings.reward_finality_blocks,
        reconcile_min_age_seconds=settings.reward_reconcile_min_age_seconds,
        max_reconcile_attempts=settings.reward_max_reconcile_attempts,
        max_submissions_per_cycle=settings.reward_max_submissions_per_cycle,
    )
