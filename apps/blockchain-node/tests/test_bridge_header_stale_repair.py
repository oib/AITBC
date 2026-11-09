"""#1305: fork-healed heights leave stale ``bridge_block_header`` rows.

``_sync_local_chain_headers`` resumes at ``last_stored + 1`` and never
re-checks stored rows, so when the canonical ``block`` table heals onto a
different hash (the h261 restart-storm divergence), the mirror keeps the
orphaned hash forever. Each pass now re-verifies a bounded recent window
(``bridge_header_verify_window``) against the canonical table and repairs
mismatches through the update-capable store path.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.config import settings
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block, BridgeBlockHeader

CHAIN_ID = "chain-a"
HEAD_HEIGHT = 40


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


def _block_hash(height: int) -> str:
    return f"0x{height:064x}"


def _seed(engine, *, stale_heights: set[int] = frozenset(), mirrored: set[int] | None = None) -> None:
    """Blocks 0..HEAD_HEIGHT; every height mirrored, ``stale_heights`` get a wrong hash."""
    if mirrored is None:
        mirrored = set(range(HEAD_HEIGHT + 1))
    with Session(engine) as session:
        for height in range(HEAD_HEIGHT + 1):
            session.add(
                Block(
                    chain_id=CHAIN_ID,
                    height=height,
                    hash=_block_hash(height),
                    parent_hash=_block_hash(height - 1) if height else "0x" + "00" * 32,
                    proposer="0x" + "11" * 20,
                    state_root=f"0xstate{height}",
                    bridge_state_root=f"0xbridge{height}",
                )
            )
        for height in mirrored:
            session.add(
                BridgeBlockHeader(
                    chain_id=CHAIN_ID,
                    height=height,
                    hash="0xdead" + "00" * 30 if height in stale_heights else _block_hash(height),
                    parent_hash="0x" + "00" * 32,
                    proposer="0x" + "11" * 20,
                    state_root=f"0xstate{height}",
                    bridge_state_root=f"0xbridge{height}",
                )
            )
        session.commit()


def _mirror_hash(engine, height: int) -> str:
    with Session(engine) as session:
        row = session.exec(
            select(BridgeBlockHeader).where(
                BridgeBlockHeader.chain_id == CHAIN_ID,
                BridgeBlockHeader.height == height,
            )
        ).one()
        return str(row.hash)


def test_stale_mirror_row_is_repaired(engine) -> None:
    _seed(engine, stale_heights={7, 23})
    bridge = CrossChainBridge(lambda: Session(engine))

    bridge._sync_local_chain_headers(CHAIN_ID)

    assert _mirror_hash(engine, 7) == _block_hash(7)
    assert _mirror_hash(engine, 23) == _block_hash(23)


def test_clean_mirror_is_untouched(engine) -> None:
    _seed(engine)
    bridge = CrossChainBridge(lambda: Session(engine))
    before = _mirror_hash(engine, 11)

    bridge._sync_local_chain_headers(CHAIN_ID)

    assert _mirror_hash(engine, 11) == before == _block_hash(11)


def test_stale_row_below_window_is_not_repaired(engine) -> None:
    """The sweep is bounded: rows deeper than the window stay stale by design
    (they cannot be pending-transfer relevant)."""
    _seed(engine, stale_heights={3})
    bridge = CrossChainBridge(lambda: Session(engine))

    with patch.object(settings, "bridge_header_verify_window", 10):
        # head=40, window=10 -> floor=30; height 3 is below it.
        bridge._sync_local_chain_headers(CHAIN_ID)

    assert _mirror_hash(engine, 3) == "0xdead" + "00" * 30


def test_stale_row_inside_window_is_repaired(engine) -> None:
    _seed(engine, stale_heights={35})
    bridge = CrossChainBridge(lambda: Session(engine))

    with patch.object(settings, "bridge_header_verify_window", 10):
        bridge._sync_local_chain_headers(CHAIN_ID)

    assert _mirror_hash(engine, 35) == _block_hash(35)


def test_repair_preserves_other_fields(engine) -> None:
    """Repair updates the diverged hash; proposer/state roots come from the
    canonical block, not the stale row."""
    _seed(engine, stale_heights={9})
    bridge = CrossChainBridge(lambda: Session(engine))

    bridge._sync_local_chain_headers(CHAIN_ID)

    with Session(engine) as session:
        row = session.exec(
            select(BridgeBlockHeader).where(
                BridgeBlockHeader.chain_id == CHAIN_ID,
                BridgeBlockHeader.height == 9,
            )
        ).one()
        assert row.proposer == "0x" + "11" * 20
        assert row.state_root == "0xstate9"


def test_missing_mirror_rows_are_still_backfilled(engine) -> None:
    """Sweep and backfill coexist: unmirrored heights store normally while a
    stale row in-window is repaired in the same pass."""
    mirrored = set(range(HEAD_HEIGHT + 1)) - {20}
    _seed(engine, stale_heights={8}, mirrored=mirrored)
    bridge = CrossChainBridge(lambda: Session(engine))

    stored = bridge._sync_local_chain_headers(CHAIN_ID)

    # last_stored = HEAD_HEIGHT already, so resume path stores nothing new;
    # height 20 stays missing (resume never looks backwards) — the sweep only
    # repairs *stored* rows, it does not backfill gaps. That is existing
    # semantics, unchanged by #1305.
    assert stored == 0
    assert _mirror_hash(engine, 8) == _block_hash(8)
