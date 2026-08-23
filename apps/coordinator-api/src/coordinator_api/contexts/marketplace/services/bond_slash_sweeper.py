
"""Periodically check for provider-bond slash conditions (G5).

Scans in-flight bonded jobs. If a miner's heartbeat is older than the configured
timeout, the provider is slashed for downtime. Fraud and bad-result slashes are
triggered from the job/dispute routers rather than from this sweeper.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from collections.abc import Callable

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from ....storage.db import get_engine
from ...infrastructure.domain import Job, Miner
from .bond_slashing import BondSlashingService, SlashingCondition

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def sweeper_enabled() -> bool:
    """The sweeper is on by default and disabled only when explicitly turned off."""
    return os.getenv("BOND_SLASH_SWEEPER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


class BondSlashSweeper:
    """Slash providers whose bonded jobs have gone silent."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        batch_size: int | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("BOND_SLASH_SWEEP_INTERVAL_SECONDS", 60)
        self.batch_size = batch_size or _env_int("BOND_SLASH_SWEEP_BATCH_SIZE", 50)
        self._session_factory = session_factory or (lambda: Session(get_engine()))

    def _to_naive_utc(self, dt: datetime) -> datetime:
        """Stored heartbeats may be naive UTC or aware; normalise for comparison."""
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(UTC).replace(tzinfo=None)

    def _find_stale_jobs(self, session: Any) -> list[Job]:
        """RUNNING bonded jobs whose miner has missed the heartbeat window."""
        stmt = (
            select(Job)
            .where(Job.state == "RUNNING")
            .where(Job.assigned_miner_id != None)  # noqa: E711
            .where(Job.payment_id != None)  # noqa: E711
            .limit(self.batch_size)
        )
        return list(session.execute(stmt).scalars().all())

    async def run_once(self) -> dict[str, int]:
        """One sweep. Returns counts for logging and tests."""
        timeout = _env_int("BOND_SLASH_HEARTBEAT_TIMEOUT_SECONDS", 300)
        cutoff = datetime.now(UTC).astimezone(UTC).replace(tzinfo=None) - timedelta(seconds=timeout)
        counts = {"stale": 0, "slashed": 0, "failed": 0, "skipped": 0}
        with self._session_factory() as session:
            for job in self._find_stale_jobs(session):
                counts["stale"] += 1
                if not job.constraints or not job.constraints.get("bond_required"):
                    counts["skipped"] += 1
                    continue
                miner = session.get(Miner, job.assigned_miner_id)
                if not miner or not (miner.last_heartbeat and self._to_naive_utc(miner.last_heartbeat) < cutoff):
                    counts["skipped"] += 1
                    continue
                try:
                    result = await BondSlashingService(session).slash(
                        job,
                        SlashingCondition.DOWNTIME,
                        f"No heartbeat from {miner.id} since {miner.last_heartbeat}",
                    )
                    if result.get("slashed"):
                        counts["slashed"] += 1
                    else:
                        counts["skipped"] += 1
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("Bond slash sweep raised for job %s: %s", job.id, e)
        logger.debug(
            "Bond slash sweep complete: stale=%s slashed=%s failed=%s skipped=%s",
            counts["stale"], counts["slashed"], counts["failed"], counts["skipped"],
        )
        return counts

    async def run_forever(self) -> None:
        logger.info(
            "Bond slash sweeper started: interval=%ss batch=%s",
            self.interval_seconds,
            self.batch_size,
        )
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Bond slash sweep failed: %s", e)
