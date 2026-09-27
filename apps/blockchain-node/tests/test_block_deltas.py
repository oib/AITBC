"""Per-block delta journal — capture, revert, and resolver integration.

The journal (``state.block_deltas.BlockDeltaJournal``) records the
before-image of every row a block apply touches — ORM inserts/updates/
deletes plus the raw ``UPDATE account`` writes that bypass dirty tracking.
``revert_losing_segment`` replays them in reverse and proves the restore
cryptographically by recomputing the state root against the common
ancestor's recorded root. A missing journal on a non-empty block, or a root
that refuses to match, escalates (returns None / refuses the commit) —
never a wrong revert.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc_chain.base_models import Account, Block, BlockStateDelta
from aitbc_chain.base_models import Transaction as ChainTransaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state.block_deltas import (
    BlockDeltaJournal,
    has_journal,
    revert_losing_segment,
)
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.sync import ChainSync
from aitbc_chain.sync import settings as sync_settings
from aitbc.crypto.signature_recovery import canonical_address
from sqlalchemy import text
from sqlmodel import Session, create_engine, select

CHAIN = "test-chain"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
# Already EIP-55 canonical — stored and raw-SQL-bound forms must agree.
ADDR_A = canonical_address("0x" + "aa" * 20)
ADDR_B = canonical_address("0x" + "bb" * 20)


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture(autouse=True)
def round_seconds(monkeypatch):
    monkeypatch.setattr(sync_settings, "consensus_proposer_round_seconds", 60)


@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'delta.db'}", echo=False)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    @contextmanager
    def _factory():
        with Session(db_engine) as session:
            yield session

    return _factory


def _hash(*parts: object) -> str:
    return "0x" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _mk_block(
    height: int,
    parent_hash: str,
    ts: datetime,
    *,
    proposer: str = "proposer-a",
    tx_count: int = 0,
    state_root: str | None = None,
    hash_salt: object = "",
) -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": _hash(height, parent_hash, ts.isoformat(), hash_salt),
        "parent_hash": parent_hash,
        "proposer": proposer,
        "timestamp": ts.isoformat(),
        "tx_count": tx_count,
        "state_root": state_root,
    }


def _store(session_factory, block: dict[str, Any]) -> None:
    with session_factory() as session:
        session.add(
            Block(
                chain_id=CHAIN,
                height=block["height"],
                hash=block["hash"],
                parent_hash=block["parent_hash"],
                proposer=block["proposer"],
                timestamp=datetime.fromisoformat(block["timestamp"]),
                tx_count=block["tx_count"],
                state_root=block["state_root"],
            )
        )
        session.commit()


def _seed(session_factory, heights: int, *, start_ts: datetime = T0, step: int = 30) -> list[dict[str, Any]]:
    """Seed `heights` empty blocks with *real* ancestor state roots."""
    blocks: list[dict[str, Any]] = []
    parent = "0x00"
    for h in range(heights):
        b = _mk_block(h, parent, start_ts + timedelta(seconds=step * h), state_root="0xstate")
        _store(session_factory, b)
        blocks.append(b)
        parent = b["hash"]
    return blocks


def _add_account(session: Session, address: str, balance: int, nonce: int = 0) -> None:
    session.add(Account(chain_id=CHAIN, address=address, balance=balance, nonce=nonce))


def _provably_empty_for(session_factory):
    """The bound ``_blocks_provably_empty`` of a real ChainSync — the same
    callable the resolvers hand to revert_losing_segment."""
    return ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)._blocks_provably_empty


def _stamp_real_root(session_factory, height: int = 0) -> None:
    """Set block `height`'s state_root to the root of the CURRENT account
    rows — the revert verifier recomputes the same way."""
    with session_factory() as session:
        root = compute_state_root_full(session, CHAIN)
        blk = session.exec(select(Block).where(Block.height == height)).one()
        blk.state_root = root
        session.commit()


def _accounts(session: Session) -> dict[str, tuple[int, int]]:
    rows = session.execute(text("SELECT address, balance, nonce FROM account WHERE chain_id = :c"), {"c": CHAIN}).all()
    return {r[0]: (r[1], r[2]) for r in rows}


class TestJournalCapture:
    def test_orm_insert_update_delete_captured(self, session_factory):
        _seed(session_factory, 1)
        with session_factory() as session:
            _add_account(session, ADDR_A, 1000)
            session.commit()  # committed state the journal diffs against

            j = BlockDeltaJournal.attach(session, CHAIN, 1)
            _add_account(session, ADDR_B, 500)  # ins
            acc = session.get(Account, (CHAIN, ADDR_A))
            acc.balance = 700  # upd: 1000 -> 700
            j.persist(session)
            session.commit()

        with session_factory() as session:
            rows = session.exec(
                select(BlockStateDelta).where(BlockStateDelta.chain_id == CHAIN).where(BlockStateDelta.height == 1)
            ).all()
        by_pk = {(r.table_name, r.op): r for r in rows}
        ins = by_pk[("account", "ins")]
        upd = by_pk[("account", "upd")]
        assert ADDR_B in ins.pk_json
        before = json.loads(upd.before_json)
        assert before["balance"] == 1000

    def test_raw_account_update_captured_with_before_image(self, session_factory):
        with session_factory() as session:
            _add_account(session, ADDR_A, 1000, nonce=3)
            session.commit()

            j = BlockDeltaJournal.attach(session, CHAIN, 5)
            # Same shape state_transition.py uses.
            session.execute(
                text(
                    "UPDATE account SET balance = balance + :amt, nonce = nonce + 1 "
                    "WHERE chain_id = :chain_id AND address = :address"
                ),
                {"amt": -250, "chain_id": CHAIN, "address": ADDR_A},
            )
            j.persist(session)
            session.commit()

        with session_factory() as session:
            rows = session.exec(select(BlockStateDelta).where(BlockStateDelta.table_name == "account")).all()
        assert len(rows) == 1 and rows[0].op == "upd"
        before = json.loads(rows[0].before_json)
        assert before["balance"] == 1000 and before["nonce"] == 3

    def test_raw_update_of_pending_insert_records_delete_undo(self, session_factory):
        """Account created by this block's pending ORM insert then raw-updated:
        undo must delete the row, not 'restore' a phantom."""
        with session_factory() as session:
            j = BlockDeltaJournal.attach(session, CHAIN, 2)
            _add_account(session, ADDR_A, 100)  # pending insert, not flushed
            session.execute(
                text("UPDATE account SET balance = :b WHERE chain_id = :chain_id AND address = :address"),
                {"b": 150, "chain_id": CHAIN, "address": ADDR_A},
            )
            session.flush()
            j.persist(session)
            session.commit()

        with session_factory() as session:
            rows = session.exec(select(BlockStateDelta).where(BlockStateDelta.table_name == "account")).all()
        ops = sorted(r.op for r in rows)
        assert ops == ["ins", "upd"]
        upd = next(r for r in rows if r.op == "upd")
        assert upd.before_json is None  # undo = delete

    def test_unjournaled_account_write_is_not_mistaken_for_capture(self, session_factory):
        """A raw write outside the account-PK pattern is skipped (and any miss
        would surface as a state-root mismatch at revert — fail closed)."""
        with session_factory() as session:
            j = BlockDeltaJournal.attach(session, CHAIN, 3)
            session.execute(text("UPDATE block SET tx_count = 0 WHERE height = -1"))
            j.persist(session)
            session.commit()
        with session_factory() as session:
            assert session.exec(select(BlockStateDelta)).all() == []


class TestRevert:
    def _journaled_block(
        self, session_factory, height: int, parent: dict[str, Any], apply_fn, *, tx_count: int = 0
    ) -> dict[str, Any]:
        """Apply a block the way _append_block does: journal + mutations + persist + commit."""
        blk = _mk_block(height, parent["hash"], T0 + timedelta(seconds=30 * (height + 1)), tx_count=tx_count)
        with session_factory() as session:
            j = BlockDeltaJournal.attach(session, CHAIN, height)
            session.add(
                Block(
                    chain_id=CHAIN,
                    height=blk["height"],
                    hash=blk["hash"],
                    parent_hash=blk["parent_hash"],
                    proposer=blk["proposer"],
                    timestamp=datetime.fromisoformat(blk["timestamp"]),
                    tx_count=blk["tx_count"],
                    state_root=blk["state_root"],
                )
            )
            apply_fn(session)
            j.persist(session)
            session.commit()
        return blk

    def test_revert_restores_accounts_and_drops_rows(self, session_factory):
        ancestor = _seed(session_factory, 1)[0]
        with session_factory() as session:
            _add_account(session, ADDR_A, 1000, nonce=1)
            session.commit()
            # The ancestor's recorded root must be the real root of the
            # pre-fork account state — that's what undo verification checks.
            root = compute_state_root_full(session, CHAIN)
            blk = session.exec(select(Block).where(Block.height == ancestor["height"])).one()
            blk.state_root = root
            session.commit()
            ancestor["state_root"] = root

        def apply(session: Session) -> None:
            session.execute(
                text(
                    "UPDATE account SET balance = balance + :amt, nonce = nonce + 1 "
                    "WHERE chain_id = :chain_id AND address = :address"
                ),
                {"amt": -400, "chain_id": CHAIN, "address": ADDR_A},
            )
            _add_account(session, ADDR_B, 400)
            session.add(
                ChainTransaction(
                    chain_id=CHAIN,
                    tx_hash="0x" + "11" * 32,
                    sender=ADDR_A,
                    recipient=ADDR_B,
                    block_height=1,
                    value=400,
                    fee=1,
                    nonce=1,
                    status="confirmed",
                    payload={"note": "hi"},
                )
            )

        self._journaled_block(session_factory, 1, ancestor, apply, tx_count=1)

        with session_factory() as session:
            assert _accounts(session)[ADDR_B][0] == 400
            ours = session.exec(select(Block).where(Block.height == 1)).one()
            anc = session.exec(select(Block).where(Block.height == 0)).one()
            payloads = revert_losing_segment(session, CHAIN, [ours], anc, _provably_empty_for(session_factory))
            assert payloads is not None and len(payloads) == 1
            assert payloads[0]["tx_hash"] == "0x" + "11" * 32
            assert payloads[0]["from"] == ADDR_A
            session.commit()

        with session_factory() as session:
            assert _accounts(session) == {ADDR_A: (1000, 1)}  # B gone, A restored
            assert session.exec(select(Block).where(Block.height == 1)).first() is None
            assert session.exec(select(ChainTransaction).where(ChainTransaction.block_height == 1)).all() == []
            assert not has_journal(session, CHAIN, 1)

    def test_revert_missing_journal_nonempty_returns_none(self, session_factory):
        ancestor = _seed(session_factory, 1)[0]
        losing = _mk_block(1, ancestor["hash"], T0 + timedelta(seconds=60), tx_count=2)
        _store(session_factory, losing)
        with session_factory() as session:
            ours = session.exec(select(Block).where(Block.height == 1)).one()
            anc = session.exec(select(Block).where(Block.height == 0)).one()
            assert revert_losing_segment(session, CHAIN, [ours], anc, _provably_empty_for(session_factory)) is None
            session.rollback()
        # Nothing was deleted.
        with session_factory() as session:
            assert session.exec(select(Block).where(Block.height == 1)).first() is not None

    def test_revert_unjournaled_provably_empty_block_ok(self, session_factory):
        ancestor = _seed(session_factory, 1)[0]
        losing = _mk_block(1, ancestor["hash"], T0 + timedelta(seconds=60))
        _store(session_factory, losing)
        _stamp_real_root(session_factory, height=0)
        with session_factory() as session:
            ours = session.exec(select(Block).where(Block.height == 1)).one()
            anc = session.exec(select(Block).where(Block.height == 0)).one()
            assert revert_losing_segment(session, CHAIN, [ours], anc, _provably_empty_for(session_factory)) == []
            session.commit()
        with session_factory() as session:
            assert session.exec(select(Block).where(Block.height == 1)).first() is None

    def test_state_root_mismatch_escalates(self, session_factory):
        ancestor = _seed(session_factory, 1)[0]
        with session_factory() as session:
            _add_account(session, ADDR_A, 1000)
            session.commit()

        def apply(session: Session) -> None:
            session.execute(
                text("UPDATE account SET balance = :b WHERE chain_id = :chain_id AND address = :address"),
                {"b": 42, "chain_id": CHAIN, "address": ADDR_A},
            )

        self._journaled_block(session_factory, 1, ancestor, apply)
        # Corrupt the journal: the recorded before-image no longer matches the
        # true pre-block state, so the revert must fail the root check.
        with session_factory() as session:
            d = session.exec(select(BlockStateDelta).where(BlockStateDelta.op == "upd")).one()
            before = json.loads(d.before_json)
            before["balance"] = 999  # wrong before-image
            d.before_json = json.dumps(before)
            session.commit()

        with session_factory() as session:
            ours = session.exec(select(Block).where(Block.height == 1)).one()
            anc = session.exec(select(Block).where(Block.height == 0)).one()
            assert revert_losing_segment(session, CHAIN, [ours], anc, _provably_empty_for(session_factory)) is None
            session.rollback()


class TestResolverUndoIntegration:
    """_resolve_fork_with_peer with a journaled non-empty losing segment."""

    async def test_nonempty_journaled_segment_reverts_and_wins(self, session_factory, monkeypatch):
        blocks = _seed(session_factory, 4)
        # The ancestor chain must carry the REAL root of the pre-fork account
        # state (empty) — revert verification recomputes it.
        with session_factory() as session:
            empty_root = compute_state_root_full(session, CHAIN)
            for b in session.exec(select(Block)).all():
                b.state_root = empty_root
            session.commit()

        # our 4: round 1, carries a transaction and an account change under a
        # journal — as if produced by _append_block.
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), tx_count=1)
        with session_factory() as session:
            j = BlockDeltaJournal.attach(session, CHAIN, 4)
            session.add(
                Block(
                    chain_id=CHAIN,
                    height=4,
                    hash=ours4["hash"],
                    parent_hash=ours4["parent_hash"],
                    proposer=ours4["proposer"],
                    timestamp=datetime.fromisoformat(ours4["timestamp"]),
                    tx_count=1,
                    state_root=ours4["state_root"],
                )
            )
            session.add(
                ChainTransaction(
                    chain_id=CHAIN,
                    tx_hash="0x" + "22" * 32,
                    sender=ADDR_A,
                    recipient=ADDR_B,
                    block_height=4,
                    value=5,
                    fee=1,
                    status="confirmed",
                )
            )
            _add_account(session, ADDR_A, 900)
            j.persist(session)
            session.commit()

        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="p4")
        peer[5] = _mk_block(5, peer[4]["hash"], T0 + timedelta(seconds=125), hash_salt="p5")

        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        async def fake_fetch(start, end, source_url):
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        # 1v1 proposers, peer longer (2 vs 1): length decides, our non-empty
        # block is undone rather than escalating.
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=5) is True
        assert metrics_registry._counters.get("sync_fork_reorg_undone_total") == 1.0
        assert metrics_registry._counters.get("sync_fork_reorg_unsafe_total") is None

        with session_factory() as session:
            assert session.exec(select(Block).where(Block.height == 4)).first() is None
            assert session.exec(select(ChainTransaction).where(ChainTransaction.block_height == 4)).all() == []
            assert _accounts(session) == {}  # the journaled account insert undone
