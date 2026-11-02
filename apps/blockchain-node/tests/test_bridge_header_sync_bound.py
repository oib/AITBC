"""Header mirroring is bounded per pass and still converges.

``_sync_local_chain_headers`` used to select every block from the gap start to
the chain head with no ``LIMIT``, loading them all into memory at once -- and a
node that has been down long enough for that to matter is exactly the node that
cannot afford it. It now takes ``bridge_header_sync_batch`` per pass.

A bound that does not converge is worse than no bound, so both halves are
pinned here: one pass stores no more than the batch, and successive passes
still reach the head.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, func, select

from aitbc_chain.config import settings
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block, BridgeBlockHeader

CHAIN_ID = "chain-a"
HEAD_HEIGHT = 119
BATCH = 25


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    chain_metadata.create_all(engine)
    yield engine
    chain_metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def bridge(engine):
    """A chain of blocks 0..HEAD_HEIGHT with only height 0 already mirrored.

    Seeding one header is what puts the sync on its resumed path
    (``start_height = last_stored + 1``); with an empty header table it would
    take the first-run branch, which is already clamped to the finality window
    and so would never reach the batch.
    """
    with Session(engine) as session:
        for height in range(HEAD_HEIGHT + 1):
            session.add(
                Block(
                    chain_id=CHAIN_ID,
                    height=height,
                    hash=f"0x{height:064x}",
                    parent_hash=f"0x{max(0, height - 1):064x}",
                    proposer="0x" + "11" * 20,
                    state_root=f"0xstate{height}",
                    bridge_state_root=f"0xbridge{height}",
                )
            )
        session.add(
            BridgeBlockHeader(
                chain_id=CHAIN_ID,
                height=0,
                hash=f"0x{0:064x}",
                parent_hash="0x" + "00" * 32,
                proposer="0x" + "11" * 20,
                state_root="0xstate0",
                bridge_state_root="0xbridge0",
            )
        )
        session.commit()
    return CrossChainBridge(lambda: Session(engine))


def _mirrored(engine) -> tuple[int, int]:
    with Session(engine) as session:
        count = session.exec(
            select(func.count()).select_from(BridgeBlockHeader).where(BridgeBlockHeader.chain_id == CHAIN_ID)
        ).one()
        top = session.exec(select(func.max(BridgeBlockHeader.height)).where(BridgeBlockHeader.chain_id == CHAIN_ID)).one()
    return int(count), int(top)


def test_one_pass_stores_at_most_the_batch(bridge, engine) -> None:
    with patch.object(settings, "bridge_header_sync_batch", BATCH):
        stored = bridge._sync_local_chain_headers(CHAIN_ID)

    assert stored == BATCH
    count, top = _mirrored(engine)
    # The unbounded version mirrored the whole 119-block gap in this one call.
    assert count == BATCH + 1
    assert top == BATCH


def test_successive_passes_reach_the_head(bridge, engine) -> None:
    gap = HEAD_HEIGHT  # heights 1..HEAD_HEIGHT are missing
    expected_passes = -(-gap // BATCH)  # ceil

    with patch.object(settings, "bridge_header_sync_batch", BATCH):
        passes = 0
        while True:
            stored = bridge._sync_local_chain_headers(CHAIN_ID)
            if not stored:
                break
            passes += 1
            assert stored <= BATCH, f"pass {passes} stored {stored}"
            assert passes <= expected_passes, "sync is not converging"

    assert passes == expected_passes
    count, top = _mirrored(engine)
    assert top == HEAD_HEIGHT
    assert count == HEAD_HEIGHT + 1


def test_the_batch_is_read_from_settings_not_hardcoded(bridge) -> None:
    with patch.object(settings, "bridge_header_sync_batch", 7):
        assert bridge._sync_local_chain_headers(CHAIN_ID) == 7


@pytest.mark.parametrize("bad", [0, -1])
def test_a_nonpositive_batch_still_makes_progress(bridge, bad: int) -> None:
    """A misconfigured batch must not wedge the mirror at zero headers a pass."""
    with patch.object(settings, "bridge_header_sync_batch", bad):
        assert bridge._sync_local_chain_headers(CHAIN_ID) == 1


class TestBackfillCommitBatching:
    """BRIDGE-FINALIZER-LOCK-1: the backfill commits once per
    ``bridge_header_commit_batch`` headers, not once per header — per-header
    commits held the sqlite write lock ~1 s apiece and starved appends (#768)."""

    def test_headers_commit_per_batch_not_per_header(self, bridge, monkeypatch):
        monkeypatch.setattr(settings, "bridge_header_sync_batch", 500)
        monkeypatch.setattr(settings, "bridge_header_commit_batch", 10)
        commits = []

        with bridge._session_for(CHAIN_ID):  # type: ignore[attr-defined]
            pass

        original_commit = Session.commit
        try:

            def counted(self):
                commits.append(1)
                return original_commit(self)

            monkeypatch.setattr(Session, "commit", counted)
            stored = bridge._sync_local_chain_headers(CHAIN_ID)  # type: ignore[attr-defined]
        finally:
            monkeypatch.setattr(Session, "commit", original_commit)

        assert stored == HEAD_HEIGHT
        # 119 new headers / batch 10 = 12 batch commits (+1 margin for the
        # seeded session) — vs ~119+ commits under the per-header path.
        assert len(commits) <= 15

    def test_deadline_stops_mid_backfill_and_next_pass_converges(self, bridge, monkeypatch):
        import time

        monkeypatch.setattr(settings, "bridge_header_sync_batch", 500)
        monkeypatch.setattr(settings, "bridge_header_commit_batch", 50)
        calls = 0

        def expiring_then_normal():
            nonlocal calls
            calls += 1
            # First call (deadline check) is already past; later calls fine.
            return time.monotonic() - 1 if calls == 1 else time.monotonic()

        with Session(
            bridge._session_for(CHAIN_ID).__wrapped__()
            if hasattr(bridge._session_for(CHAIN_ID), "__wrapped__")
            else bridge._session_for(CHAIN_ID)
        ):
            pass

        stored = bridge._sync_local_chain_headers(CHAIN_ID, deadline=time.monotonic() - 1)  # type: ignore[attr-defined]
        assert stored == 0
        stored = bridge._sync_local_chain_headers(CHAIN_ID)  # type: ignore[attr-defined]
        assert stored == HEAD_HEIGHT


class TestFinalizerDeadlineMargin:
    """BRIDGE-FINALIZER-DEADLINE-MARGIN-1: the cooperative deadline sits at
    ``_FINALIZER_DEADLINE_FRACTION`` of the wait_for watchdog, so a pass that
    stops on its own deadline returns before the watchdog fires and is not
    counted as abandoned. A pass that ignores the deadline (wedged) still
    trips the watchdog and is counted."""

    async def _run_finalizer_briefly(self, bridge, seconds: float) -> None:
        task = asyncio.create_task(bridge.start_finalizer())
        try:
            await asyncio.sleep(seconds)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    def _patch_chains(self, bridge, monkeypatch, pass_timeout: float) -> None:
        monkeypatch.setattr(bridge, "_known_chains", lambda: [CHAIN_ID])
        monkeypatch.setattr(settings, "bridge_finalizer_pass_timeout", pass_timeout)
        monkeypatch.setattr(settings, "bridge_monitor_interval", 60)

    @pytest.mark.asyncio
    async def test_deadline_bound_pass_returns_before_the_watchdog(self, bridge, monkeypatch):
        """A pass that honors its deadline finishes inside the margin and is
        not reported abandoned — before the fix, deadline == watchdog meant it
        always tripped wait_for and logged 'worker thread abandoned'."""
        self._patch_chains(bridge, monkeypatch, pass_timeout=1.0)
        reports: list[str] = []
        monkeypatch.setattr(bridge, "_report_abandoned_pass", lambda abandoned, cid, t: reports.append(cid))
        seen: list[float] = []

        def deadline_bound_pass(cid, relayer, deadline):
            seen.append(deadline)
            while time.monotonic() < deadline:
                time.sleep(0.01)

        monkeypatch.setattr(bridge, "_finalizer_pass", deadline_bound_pass)

        start = time.monotonic()
        # Run past the 1.0 s watchdog budget: reports == [] is only possible
        # if the pass stopped on its own deadline and wait_for never timed
        # out. Under the old code the pass returns at about 1.0 s, races the
        # 1.0 s watchdog, and is reported abandoned.
        await self._run_finalizer_briefly(bridge, 1.3)

        assert reports == []
        assert len(seen) == 1
        offset = seen[0] - start
        assert 0 < offset < 0.95 * 1.0

    @pytest.mark.asyncio
    async def test_a_wedged_pass_is_still_abandoned(self, bridge, monkeypatch, caplog):
        """The watchdog stays the backstop: a worker that ignores the deadline
        and runs past the full pass budget is abandoned and counted."""
        self._patch_chains(bridge, monkeypatch, pass_timeout=0.5)

        def wedged_pass(cid, relayer, deadline):
            time.sleep(5)

        monkeypatch.setattr(bridge, "_finalizer_pass", wedged_pass)

        with caplog.at_level("ERROR"):
            await self._run_finalizer_briefly(bridge, 0.8)

        assert bridge._finalizer_abandoned[CHAIN_ID] == 1
        assert any("abandoned" in r.message for r in caplog.records)
