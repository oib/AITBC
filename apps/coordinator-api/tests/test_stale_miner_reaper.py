"""Tests for the stale-miner reaper."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.infrastructure.services.stale_miner_reaper import (
    StaleMinerReaper,
    reaper_enabled,
)


@pytest.fixture
def reaper_session(db_engine) -> Generator[Session]:
    with Session(db_engine) as session:
        yield session


def _miner(
    session: Session,
    miner_id: str,
    *,
    status: str = "ONLINE",
    heartbeat_age_seconds: int = 0,
    inflight: int = 0,
) -> Miner:
    """Create and persist a miner fixture."""
    miner = Miner(
        id=miner_id,
        status=status,
        last_heartbeat=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=heartbeat_age_seconds),
        inflight=inflight,
    )
    session.add(miner)
    session.commit()
    return miner


@pytest.mark.unit
class TestStaleMinerReaper:
    """StaleMinerReaper marks miners with stale heartbeats as OFFLINE."""

    def test_reaper_marks_stale_miner_offline(self, reaper_session):
        """An ONLINE miner with an old heartbeat is marked OFFLINE and inflight reset."""
        _miner(reaper_session, "stale-miner", heartbeat_age_seconds=600, inflight=2)

        reaper = StaleMinerReaper(
            interval_seconds=60,
            heartbeat_timeout_seconds=300,
            session_factory=lambda: reaper_session,
        )
        counts = reaper.run_once()

        assert counts["stale"] == 1
        assert counts["offline"] == 1
        assert counts["failed"] == 0

        reaper_session.refresh(reaper_session.get(Miner, "stale-miner"))
        stale = reaper_session.get(Miner, "stale-miner")
        assert stale.status == "OFFLINE"
        assert stale.inflight == 0

    def test_reaper_leaves_fresh_miner_online(self, reaper_session):
        """An ONLINE miner with a recent heartbeat stays ONLINE."""
        _miner(reaper_session, "fresh-miner", heartbeat_age_seconds=10)

        reaper = StaleMinerReaper(
            interval_seconds=60,
            heartbeat_timeout_seconds=300,
            session_factory=lambda: reaper_session,
        )
        counts = reaper.run_once()

        assert counts["stale"] == 0
        assert counts["offline"] == 0
        assert counts["failed"] == 0

        fresh = reaper_session.get(Miner, "fresh-miner")
        assert fresh.status == "ONLINE"

    def test_reaper_ignores_already_offline_miners(self, reaper_session):
        """A miner already OFFLINE is not counted as stale."""
        _miner(reaper_session, "offline-miner", status="OFFLINE", heartbeat_age_seconds=600)

        reaper = StaleMinerReaper(
            interval_seconds=60,
            heartbeat_timeout_seconds=300,
            session_factory=lambda: reaper_session,
        )
        counts = reaper.run_once()

        assert counts["stale"] == 0
        assert counts["offline"] == 0

    def test_reaper_respects_env_vars(self, reaper_session, monkeypatch):
        """The reaper reads its settings from environment variables."""
        monkeypatch.setenv("COORDINATOR_STALE_MINER_REAPER_INTERVAL_SECONDS", "120")
        monkeypatch.setenv("COORDINATOR_MINER_HEARTBEAT_CUTOFF_SECONDS", "10")

        _miner(reaper_session, "env-miner", heartbeat_age_seconds=30)

        reaper = StaleMinerReaper(session_factory=lambda: reaper_session)
        assert reaper.interval_seconds == 120
        assert reaper.heartbeat_timeout_seconds == 10

        counts = reaper.run_once()
        assert counts["stale"] == 1
        assert counts["offline"] == 1

    def test_reaper_can_be_disabled(self, monkeypatch):
        """reaper_enabled() returns False when the env var is set to false."""
        monkeypatch.setenv("COORDINATOR_STALE_MINER_REAPER_ENABLED", "false")
        assert reaper_enabled() is False

    def test_reaper_enabled_by_default(self, monkeypatch):
        """reaper_enabled() returns True by default."""
        monkeypatch.delenv("COORDINATOR_STALE_MINER_REAPER_ENABLED", raising=False)
        assert reaper_enabled() is True
