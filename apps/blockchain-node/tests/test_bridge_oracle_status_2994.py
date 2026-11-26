"""#2994: ``get_oracle_status`` aggregates in SQL and reports per-chain counts.

The endpoint previously hydrated every ``BridgeBlockHeader`` row to count
them, which scaled with table size and produced the >30s stalls that made
``aitbc bridge oracle-status`` time out on live nodes.
"""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import BridgeBlockHeader


@pytest.fixture
def bridge():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    chain_metadata.create_all(engine)
    b = CrossChainBridge(lambda: Session(engine))
    yield b, engine
    chain_metadata.drop_all(engine)


def _header(chain_id: str, height: int, finalized: bool = False) -> BridgeBlockHeader:
    return BridgeBlockHeader(
        chain_id=chain_id,
        height=height,
        hash=f"0x{height:064x}",
        parent_hash="0x" + "00" * 32,
        proposer="0xproposer",
        state_root="0xstate",
        finality_confirmed=finalized,
    )


def test_oracle_status_aggregates_per_chain(bridge):
    b, engine = bridge
    with Session(engine) as session:
        session.add_all(
            [
                _header("chain-a", 1),
                _header("chain-a", 2, finalized=True),
                _header("chain-a", 3, finalized=True),
                _header("chain-b", 1),
                _header("chain-b", 2),
            ]
        )
        session.commit()

    status = b.get_oracle_status()

    assert status["block_headers_total"] == 5
    assert status["block_headers_finalized"] == 2
    assert status["block_headers_per_chain"] == {"chain-a": 3, "chain-b": 2}
    for key in (
        "verification_mode",
        "min_confirmations",
        "finality_blocks",
        "large_transfer_threshold",
        "release_enabled",
        "multisig_enabled",
    ):
        assert key in status


def test_oracle_status_empty_table(bridge):
    b, _engine = bridge
    status = b.get_oracle_status()
    assert status["block_headers_total"] == 0
    assert status["block_headers_finalized"] == 0
    assert status["block_headers_per_chain"] == {}
