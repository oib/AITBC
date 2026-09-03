"""Periodically expire abandoned QUEUED/RUNNING jobs (G3/G5 follow-up).

``JobService._ensure_not_expired`` already flips a job to ``EXPIRED`` once its
``expires_at`` has passed, but it is read-triggered only -- it runs inline when
something happens to fetch that specific job (a client polling status, a miner
touching it). A job nobody is polling any more (miner went dark, client stopped
checking) never gets that check re-run, so ``expires_at`` passing is invisible
to the rest of the system and the job sits ``RUNNING`` forever.

That silence has two downstream costs:
- ``StuckEscrowSweeper`` never sees the job (it only acts on already-terminal
  states), so its held escrow is never refunded.
- ``BondSlashSweeper`` keeps matching it every cycle forever, re-slashing the
  same continuous downtime incident instead of a single proportionate penalty.

This reaper proactively re-runs the existing, already-correct expiry
transition on a schedule, plus a second clause for jobs whose TTL has not
technically elapsed yet but whose assigned miner has been OFFLINE for a long
time (heartbeat-dead, but not yet TTL-expired).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, col, select

from aitbc.aitbc_logging import get_logger

from ....storage.db import get_engine
from ..domain import Job, Miner

logger = get_logger(__name__)

_ACTIVE_STATES = {"QUEUED", "RUNNING"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def reaper_enabled() -> bool:
    """The reaper is on by default and disabled only when explicitly turned off."""
    return os.getenv("COORDINATOR_STALE_JOB_REAPER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _to_utc(dt: datetime | None) -> datetime | None:
    """Make a datetime comparable with ``datetime.now(UTC)``."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class StaleJobReaper:
    """Expire abandoned QUEUED/RUNNING jobs so downstream sweepers can see them."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        miner_dead_seconds: int | None = None,
        batch_size: int | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("COORDINATOR_STALE_JOB_REAPER_INTERVAL_SECONDS", 60)
        # A RUNNING job whose miner has been OFFLINE this long is treated as
        # abandoned even if its own TTL has not technically elapsed yet.
        self.miner_dead_seconds = miner_dead_seconds or _env_int("COORDINATOR_STALE_JOB_MINER_DEAD_SECONDS", 600)
        self.batch_size = batch_size or _env_int("COORDINATOR_STALE_JOB_REAPER_BATCH_SIZE", 100)
        self._session_factory = session_factory or (lambda: Session(get_engine()))

    def _find_ttl_expired(self, session: Any) -> list[Job]:
        """QUEUED/RUNNING jobs whose expires_at has already passed."""
        now = datetime.now(UTC).replace(tzinfo=None)
        stmt = (
            select(Job)
            .where(col(Job.state).in_(_ACTIVE_STATES))
            .where(col(Job.expires_at).is_not(None))
            .where(col(Job.expires_at) < now)
            .limit(self.batch_size)
        )
        return list(session.execute(stmt).scalars().all())

    def _find_miner_dead(self, session: Any) -> list[Job]:
        """RUNNING jobs whose assigned miner has been OFFLINE past the grace period.

        Covers jobs whose TTL is long (or far in the future) but whose miner is
        already known-dead -- pure TTL expiry alone would leave these stuck.
        """
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=self.miner_dead_seconds)
        stmt = (
            select(Job)
            .join(Miner, col(Job.assigned_miner_id) == Miner.id)
            .where(Job.state == "RUNNING")
            .where(Miner.status == "OFFLINE")
            .where(col(Miner.last_heartbeat) < cutoff)
            .limit(self.batch_size)
        )
        return list(session.execute(stmt).scalars().all())

    def _expire(self, session: Any, job: Job, reason: str) -> None:
        """Apply the same transition JobService._ensure_not_expired already uses."""
        job.state = "EXPIRED"
        job.error = reason
        session.add(job)

    def run_once(self) -> dict[str, int]:
        """One sweep. Returns counts for logging and tests."""
        counts = {"ttl_expired": 0, "miner_dead": 0, "failed": 0}
        with self._session_factory() as session:
            seen: set[str] = set()
            for job in self._find_ttl_expired(session):
                seen.add(job.id)
                try:
                    self._expire(session, job, "job expired")
                    counts["ttl_expired"] += 1
                    logger.info("Expired abandoned job %s (TTL elapsed at %s)", job.id, job.expires_at)
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("Failed to expire job %s: %s", job.id, e)

            for job in self._find_miner_dead(session):
                if job.id in seen:
                    continue
                try:
                    self._expire(session, job, "job abandoned: assigned miner offline")
                    counts["miner_dead"] += 1
                    logger.info(
                        "Expired job %s: miner %s offline past %ss grace period",
                        job.id,
                        job.assigned_miner_id,
                        self.miner_dead_seconds,
                    )
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("Failed to expire job %s: %s", job.id, e)

            try:
                session.commit()
            except Exception as e:
                counts["failed"] += 1
                logger.error("Stale job reaper commit failed: %s", e)
                session.rollback()
        logger.debug(
            "Stale job reaper complete: ttl_expired=%s miner_dead=%s failed=%s",
            counts["ttl_expired"],
            counts["miner_dead"],
            counts["failed"],
        )
        return counts

    async def run_forever(self) -> None:
        logger.info(
            "Stale job reaper started: interval=%ss miner_dead_grace=%ss batch=%s",
            self.interval_seconds,
            self.miner_dead_seconds,
            self.batch_size,
        )
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Stale job reaper sweep failed: %s", e)
