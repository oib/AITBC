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
