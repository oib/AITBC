"""Single-active-distributor lock for reward payouts (#3058).

AUDIT-POOLHUB-REWARD-POOL-PIPELINE-1 item 3: the ``reward_payouts`` UNIQUE
constraint only dedupes payouts that land in the SAME database. hub and
hub1 both run ``aitbc-pool-hub`` (:8210); if they point at different
Postgres instances, two distributors can each claim and pay the same
miner+epoch.

This lock makes exactly one distributor active per payout database:

- **PostgreSQL**: a session-level ``pg_try_advisory_lock`` held on a
  dedicated connection for the duration of a distribution cycle. Non-
  blocking — a replica that fails to acquire simply skips the cycle.
- **Other dialects** (sqlite dev/test): an in-process ``asyncio.Lock``.
  Correct for the single-process case; multi-process sqlite deployments
  are not a supported topology.

IMPORTANT deployment note: the advisory lock only excludes replicas that
share the same payout database. Replicas on separate databases must
additionally pin ``POOLHUB_REWARD_DISTRIBUTION_NODE`` to exactly one
hostname (enforced by ``reward_gate``) — see settings.py.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger(__name__)

# Stable advisory-lock key for the reward distributor, derived from a name
# so it cannot collide with hand-picked integer keys used elsewhere.
_LOCK_KEY = int.from_bytes(hashlib.sha256(b"poolhub.reward_distribution").digest()[:8], "big", signed=True)

# Fallback for non-PostgreSQL dialects (sqlite dev/test).
_process_lock = asyncio.Lock()


class RewardDistributorLock:
    """Holds the single-active-distributor guarantee for one engine."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._conn: AsyncConnection | None = None  # held connection carrying the advisory lock
        self._locked = False

    @property
    def is_postgres(self) -> bool:
        return self._engine.dialect.name == "postgresql"

    async def acquire(self) -> bool:
        """Try to become the active distributor. False = another replica holds it."""
        if not self.is_postgres:
            # asyncio.Lock has no try-acquire; use locked() state instead.
            if _process_lock.locked():
                return False
            await _process_lock.acquire()
            self._locked = True
            return True
        conn = await self._engine.connect()
        try:
            result = await conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK_KEY})
            acquired = bool(result.scalar())
        except Exception:  # noqa: BLE001 - any probe failure must close the conn and propagate; caller decides
            await conn.close()
            raise
        if not acquired:
            await conn.close()
            return False
        # Keep the connection open: the session-level advisory lock dies
        # with it, so holding it IS holding the lock.
        self._conn = conn
        self._locked = True
        return True

    async def release(self) -> None:
        if not self._locked:
            return
        self._locked = False
        if self.is_postgres:
            conn, self._conn = self._conn, None
            if conn is not None:
                try:
                    await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})
                except Exception:  # noqa: BLE001 - unlock failure still closes the conn, which releases the lock anyway
                    logger.warning("reward distributor advisory unlock failed; closing connection", exc_info=True)
                await conn.close()
        else:
            _process_lock.release()  # noqa: unawaited-async - asyncio.Lock.release() is synchronous


@asynccontextmanager
async def distributor_lock(engine: AsyncEngine) -> AsyncIterator[bool]:
    """Context manager yielding True when this process is the active distributor.

    Usage::

        async with distributor_lock(engine) as active:
            if not active:
                return  # another replica owns distribution this cycle
            ...
    """
    lock = RewardDistributorLock(engine)
    active = await lock.acquire()
    try:
        yield active
    finally:
        await lock.release()
