"""#1268 Phase 1, item 4: additive finality fields on the RPC read surface.

Flag off => the responses are byte-identical to the pre-#1268 surface.
Flag on  => ``confirmations`` / ``finalized`` / ``finality_depth`` on block and
tx reads and ``finalized_height`` on /head, N=3 (BRIDGE_WITHDRAW_SEAL_DEPTH).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.base_models import Transaction
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block
from aitbc_chain.rpc import blocks as rpc_blocks
from aitbc_chain.rpc import transactions as rpc_txs
from aitbc_chain.rpc.finality import finality_view, head_finality
from sqlmodel import Session, create_engine

CHAIN = "chain-a"
FIELDS = {"confirmations", "finalized", "finality_depth", "finalized_height"}


@pytest.fixture
def engine(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 'fin.db'}", echo=False)
    chain_metadata.create_all(eng)

    @contextmanager
    def _scope(*_a, **_k):
        with Session(eng) as session:
            yield session

    monkeypatch.setattr(rpc_blocks, "session_scope", _scope)
    monkeypatch.setattr(rpc_txs, "session_scope", _scope)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "rpc_finality_depth", 3)
    monkeypatch.setattr(settings, "rpc_finality_fields_enabled", False)
    yield eng
    eng.dispose()


def _seed(eng, head: int, tx_height: int = 1) -> None:
    with Session(eng) as s:
        for h in range(head + 1):
            s.add(
                Block(
                    chain_id=CHAIN,
                    height=h,
                    hash=f"0x{h:064x}",
                    parent_hash=f"0x{h - 1:064x}" if h else "0x00",
                    proposer="p",
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                    tx_count=0,
                )
            )
        s.add(Transaction(chain_id=CHAIN, tx_hash="0xtx", block_height=tx_height, sender="0xa", recipient="0xb"))
        s.add(Transaction(chain_id=CHAIN, tx_hash="0xpending", block_height=None, sender="0xa", recipient="0xb"))
        s.commit()


class TestFlagOff:
    def test_responses_carry_no_finality_fields(self, engine):
        _seed(engine, head=10)
        req = Mock()
        assert not FIELDS & set(rpc_blocks.get_head(req, CHAIN))
        assert not FIELDS & set(rpc_blocks.get_block(req, 10, CHAIN))
        assert not FIELDS & set(rpc_txs.get_transaction(req, "0xtx", CHAIN))
        assert all(not FIELDS & set(r) for r in rpc_txs.query_transactions(req, chain_id=CHAIN))

    def test_flag_on_only_adds_keys(self, engine, monkeypatch):
        _seed(engine, head=10)
        req = Mock()
        before_head = rpc_blocks.get_head(req, CHAIN)
        before_block = rpc_blocks.get_block(req, 10, CHAIN)
        before_tx = rpc_txs.get_transaction(req, "0xtx", CHAIN)
        monkeypatch.setattr(settings, "rpc_finality_fields_enabled", True)
        after_head = rpc_blocks.get_head(req, CHAIN)
        after_block = rpc_blocks.get_block(req, 10, CHAIN)
        after_tx = rpc_txs.get_transaction(req, "0xtx", CHAIN)
        for before, after in ((before_head, after_head), (before_block, after_block), (before_tx, after_tx)):
            assert {k: after[k] for k in before} == before  # no existing field changed
            assert set(after) - set(before) <= FIELDS


class TestFlagOn:
    @pytest.fixture(autouse=True)
    def _on(self, engine, monkeypatch):
        monkeypatch.setattr(settings, "rpc_finality_fields_enabled", True)

    def test_head_reports_finalized_height_n3(self, engine):
        _seed(engine, head=10)
        head = rpc_blocks.get_head(Mock(), CHAIN)
        assert head["finalized_height"] == 7
        assert head["finality_depth"] == 3

    def test_head_finalized_height_floors_at_zero(self, engine):
        _seed(engine, head=1)
        assert rpc_blocks.get_head(Mock(), CHAIN)["finalized_height"] == 0

    @pytest.mark.parametrize(
        ("height", "confs", "final"), [(10, 0, False), (9, 1, False), (8, 2, False), (7, 3, True), (3, 7, True)]
    )
    def test_block_depth_boundaries(self, engine, height, confs, final):
        _seed(engine, head=10)
        block = rpc_blocks.get_block(Mock(), height, CHAIN)
        assert (block["confirmations"], block["finalized"], block["finality_depth"]) == (confs, final, 3)

    def test_transaction_read_follows_its_sealing_block(self, engine):
        _seed(engine, head=3, tx_height=3)
        tx = rpc_txs.get_transaction(Mock(), "0xtx", CHAIN)
        assert (tx["confirmations"], tx["finalized"]) == (0, False)  # depth 0: sealed, not final
        _seed_more = Session(engine)
        _seed_more.add(
            Block(
                chain_id=CHAIN,
                height=4,
                hash="0x4",
                parent_hash=f"0x{3:064x}",
                proposer="p",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                tx_count=0,
            )
        )
        _seed_more.add(
            Block(
                chain_id=CHAIN,
                height=5,
                hash="0x5",
                parent_hash="0x4",
                proposer="p",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                tx_count=0,
            )
        )
        _seed_more.add(
            Block(
                chain_id=CHAIN,
                height=6,
                hash="0x6",
                parent_hash="0x5",
                proposer="p",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                tx_count=0,
            )
        )
        _seed_more.commit()
        _seed_more.close()
        tx = rpc_txs.get_transaction(Mock(), "0xtx", CHAIN)
        assert (tx["confirmations"], tx["finalized"]) == (3, True)

    def test_pending_transaction_is_never_final(self, engine):
        _seed(engine, head=10)
        tx = rpc_txs.get_transaction(Mock(), "0xpending", CHAIN)
        assert (tx["confirmations"], tx["finalized"]) == (0, False)

    def test_query_rows_are_annotated(self, engine):
        _seed(engine, head=10, tx_height=2)
        rows = {r["tx_hash"]: r for r in rpc_txs.query_transactions(Mock(), chain_id=CHAIN)}
        assert rows["0xtx"]["finalized"] is True and rows["0xtx"]["confirmations"] == 8
        assert rows["0xpending"]["finalized"] is False


def test_pure_helpers():
    assert finality_view(None, 10)["finalized"] is False
    assert finality_view(5, None)["finalized"] is False
    assert finality_view(12, 10)["confirmations"] == 0  # a height above the head never goes negative
    assert head_finality(2)["finalized_height"] == 0
