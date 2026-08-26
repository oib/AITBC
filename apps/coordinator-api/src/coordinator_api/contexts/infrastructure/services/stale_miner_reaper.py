"""Periodically mark miners with stale heartbeats as OFFLINE (G5).

The dispatch-time filter in JobService and the online_count() in MinerService
already ignore stale miners.  This reaper keeps the database honest so the
dashboard and any other status consumers do not over-count stale records.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from ....storage.db import get_engine
from ..domain import Miner

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def reaper_enabled() -> bool:
    """The reaper is on by default and disabled only when explicitly turned off."""
    return os.getenv("COORDINATOR_STALE_MINER_REAPER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


class StaleMinerReaper:
    """Mark miners that have not heartbeated within the cutoff window as OFFLINE."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        heartbeat_timeout_seconds: int | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("COORDINATOR_STALE_MINER_REAPER_INTERVAL_SECONDS", 60)
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds or _env_int(
            "COORDINATOR_MINER_HEARTBEAT_CUTOFF_SECONDS", 300
        )
        self._session_factory = session_factory or (lambda: Session(get_engine()))

    def _to_naive_utc(self, dt: datetime) -> datetime:
        """Stored heartbeats may be naive UTC or aware; normalise for comparison."""
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(UTC).replace(tzinfo=None)

    def _find_stale_miners(self, session: Any) -> list[Miner]:
        """Return ONLINE miners whose last heartbeat is older than the cutoff."""
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=self.heartbeat_timeout_seconds)
        stmt = select(Miner).where(Miner.status == "ONLINE", Miner.last_heartbeat < cutoff)
        return list(session.execute(stmt).scalars().all())

    def run_once(self) -> dict[str, int]:
        """One sweep. Returns counts for logging and tests."""
        counts = {"stale": 0, "offline": 0, "failed": 0}
        with self._session_factory() as session:
            for miner in self._find_stale_miners(session):
                counts["stale"] += 1
                try:
                    miner.status = "OFFLINE"
                    miner.inflight = 0
                    session.add(miner)
                    counts["offline"] += 1
                    logger.info("Marked miner %s as OFFLINE (last heartbeat %s)", miner.id, miner.last_heartbeat)
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("Failed to mark miner %s offline: %s", miner.id, e)
            try:
                session.commit()
            except Exception as e:
                counts["failed"] += 1
                logger.error("Stale miner reaper commit failed: %s", e)
                session.rollback()
        logger.debug(
            "Stale miner reaper complete: stale=%s offline=%s failed=%s",
            counts["stale"],
            counts["offline"],
            counts["failed"],
        )
        return counts

    async def run_forever(self) -> None:
        logger.info(
            "Stale miner reaper started: interval=%ss heartbeat_timeout=%ss",
            self.interval_seconds,
            self.heartbeat_timeout_seconds,
        )
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Stale miner reaper sweep failed: %s", e)
