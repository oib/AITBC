"""Mempool resource limits: size cap, fee-aware eviction, and nonce slots.

Regression coverage for the four intake gaps closed together with the gossip
admission wiring:

* ``mempool_max_tx_size_bytes`` — an oversized transaction can never fit a
  block (``max_block_size_bytes``), so admitting one only lets it squat in the
  pool until TTL expiry while ``drain`` loads its content every round.
* Fee-floor eviction — a full pool previously evicted the cheapest pending
  transaction for *any* newcomer, so a fee-floor flood evicted real work it
  could never outbid. Now the newcomer must strictly outbid the lowest fee.
* (sender, nonce) slots — submission only deduped on tx_hash, so one sender
  could queue thousands of same-nonce variants of which at most one could ever
  execute. Signed transactions now compete for their slot: a second candidate
  must pay strictly more, and then replaces the first. Unsigned
  protocol-internal transactions (escrow movements, bridge locks and credits)
  carry no top-level signature and are exempt — their nonce is a placeholder
  the proposer rewrites at seal time.
* ``pending_cost`` — admission charges the sender's other signed pending
  transactions against the same balance, so an account cannot queue more than
  it can ever pay.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session

from aitbc_chain.config import settings
from aitbc_chain.mempool import DatabaseMempool, InMemoryMempool
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc import transactions as transactions_mod
from aitbc_chain.rpc.utils import get_chain_id

CHAIN = "test-chain"
SENDER = "0x1000000000000000000000000000000000000001"
OTHER = "0x2000000000000000000000000000000000000002"


def _signed_tx(
    sender: str = SENDER,
    nonce: int = 0,
    fee: int = 5,
    amount: int = 10,
    **overrides: Any,
) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": sender,
        "to": "0x3000000000000000000000000000000000000003",
        "amount": amount,
        "fee": fee,
        "nonce": nonce,
        "type": "TRANSFER",
        "payload": {},
        "chain_id": CHAIN,
        "signature": "0xsig",
    }
    tx.update(overrides)
    return tx


@pytest.fixture(params=["memory", "database"])
def pool(request: pytest.FixtureRequest, tmp_path):
    if request.param == "memory":
        yield InMemoryMempool(max_size=100, min_fee=0)
    else:
        yield DatabaseMempool(f"sqlite:///{tmp_path / 'mempool.db'}", max_size=100, min_fee=0)


@pytest.fixture(params=["memory", "database"])
def small_pool(request: pytest.FixtureRequest, tmp_path):
    if request.param == "memory":
        yield InMemoryMempool(max_size=2, min_fee=0)
    else:
        yield DatabaseMempool(f"sqlite:///{tmp_path / 'mempool.db'}", max_size=2, min_fee=0)


class TestSizeCap:
    def test_oversized_transaction_rejected(self, pool):
        blob = "x" * settings.mempool_max_tx_size_bytes
        with pytest.raises(ValueError, match="exceeds limit"):
            pool.add(_signed_tx(payload={"blob": blob}), chain_id=CHAIN)

    def test_normal_transaction_accepted(self, pool):
        assert pool.add(_signed_tx(payload={"blob": "x" * 100}), chain_id=CHAIN)
        assert pool.size(CHAIN) == 1


class TestFullPoolFeeFloor:
    def test_cheaper_newcomer_rejected(self, small_pool):
        small_pool.add(_signed_tx(sender="0xa", nonce=0, fee=5), chain_id=CHAIN)
        small_pool.add(_signed_tx(sender="0xb", nonce=0, fee=10), chain_id=CHAIN)
        with pytest.raises(ValueError, match="mempool full"):
            small_pool.add(_signed_tx(sender="0xc", nonce=0, fee=1), chain_id=CHAIN)
        assert small_pool.size(CHAIN) == 2

    def test_equal_fee_newcomer_rejected(self, small_pool):
        small_pool.add(_signed_tx(sender="0xa", nonce=0, fee=5), chain_id=CHAIN)
        small_pool.add(_signed_tx(sender="0xb", nonce=0, fee=10), chain_id=CHAIN)
        with pytest.raises(ValueError, match="mempool full"):
            small_pool.add(_signed_tx(sender="0xc", nonce=0, fee=5), chain_id=CHAIN)

    def test_pricier_newcomer_evicts_lowest(self, small_pool):
        small_pool.add(_signed_tx(sender="0xa", nonce=0, fee=5), chain_id=CHAIN)
        keep = _signed_tx(sender="0xb", nonce=0, fee=10)
        small_pool.add(keep, chain_id=CHAIN)
        new_hash = small_pool.add(_signed_tx(sender="0xc", nonce=0, fee=11), chain_id=CHAIN)
        hashes = {t.tx_hash for t in small_pool.list_transactions(CHAIN)}
        from aitbc_chain.mempool import compute_tx_hash

        assert hashes == {compute_tx_hash(keep), new_hash}

    def test_fee_floor_applies_to_unsigned_internal_txs(self, small_pool):
        """Capacity rules are uniform: a full pool of higher-fee entries rejects
        even protocol-internal writes — silently dropping a bridge credit would
        be worse than a loud failure."""
        small_pool.add(_signed_tx(sender="0xa", nonce=0, fee=5), chain_id=CHAIN)
        small_pool.add(_signed_tx(sender="0xb", nonce=0, fee=10), chain_id=CHAIN)
        internal = {"from": "bridge_release", "to": "0xdead", "amount": 1, "fee": 0, "nonce": 0}
        with pytest.raises(ValueError, match="mempool full"):
            small_pool.add(internal, chain_id=CHAIN)


class TestNonceSlot:
    def test_higher_fee_replaces_same_slot(self, pool):
        pool.add(_signed_tx(nonce=0, fee=5), chain_id=CHAIN)
        new_hash = pool.add(_signed_tx(nonce=0, fee=10, amount=11), chain_id=CHAIN)
        assert pool.size(CHAIN) == 1
        assert pool.list_transactions(CHAIN)[0].tx_hash == new_hash

    def test_equal_fee_same_slot_rejected(self, pool):
        pool.add(_signed_tx(nonce=0, fee=5), chain_id=CHAIN)
        with pytest.raises(ValueError, match="nonce slot"):
            pool.add(_signed_tx(nonce=0, fee=5, amount=11), chain_id=CHAIN)
        assert pool.size(CHAIN) == 1

    def test_lower_fee_same_slot_rejected(self, pool):
        pool.add(_signed_tx(nonce=0, fee=10), chain_id=CHAIN)
        with pytest.raises(ValueError, match="nonce slot"):
            pool.add(_signed_tx(nonce=0, fee=1, amount=11), chain_id=CHAIN)

    def test_different_nonce_coexists(self, pool):
        pool.add(_signed_tx(nonce=0, fee=5), chain_id=CHAIN)
        pool.add(_signed_tx(nonce=1, fee=1), chain_id=CHAIN)
        assert pool.size(CHAIN) == 2

    def test_different_sender_same_nonce_coexists(self, pool):
        pool.add(_signed_tx(sender=SENDER, nonce=0, fee=5), chain_id=CHAIN)
        pool.add(_signed_tx(sender=OTHER, nonce=0, fee=1), chain_id=CHAIN)
        assert pool.size(CHAIN) == 2

    def test_unsigned_txs_exempt_from_slot_rule(self, pool):
        """Protocol-internal writes (fee 0, placeholder nonce 0, unsigned) must
        be able to coexist — escrow/bridge flows queue several per sender."""
        first = {"from": "0xescrow", "to": "0xdead", "amount": 5, "fee": 0, "nonce": 0}
        second = {"from": "0xescrow", "to": "0xbeef", "amount": 7, "fee": 0, "nonce": 0}
        pool.add(first, chain_id=CHAIN)
        pool.add(second, chain_id=CHAIN)
        assert pool.size(CHAIN) == 2

    def test_slot_freed_when_occupant_drained(self, pool):
        pool.add(_signed_tx(nonce=0, fee=100), chain_id=CHAIN)
        pool.drain(max_count=100, max_bytes=10**7, chain_id=CHAIN)
        # A cheaper tx may now occupy the freed slot.
        pool.add(_signed_tx(nonce=0, fee=1, amount=11), chain_id=CHAIN)
        assert pool.size(CHAIN) == 1

    def test_slot_freed_when_occupant_removed(self, pool):
        h = pool.add(_signed_tx(nonce=0, fee=100), chain_id=CHAIN)
        assert pool.remove(h, chain_id=CHAIN)
        pool.add(_signed_tx(nonce=0, fee=1, amount=11), chain_id=CHAIN)
        assert pool.size(CHAIN) == 1


class TestPendingCost:
    def test_sums_signed_costs(self, pool):
        pool.add(_signed_tx(nonce=0, amount=10, fee=1), chain_id=CHAIN)
        pool.add(_signed_tx(nonce=1, amount=20, fee=2), chain_id=CHAIN)
        assert pool.pending_cost(CHAIN, SENDER) == 33

    def test_excludes_unsigned_and_other_senders(self, pool):
        pool.add(_signed_tx(nonce=0, amount=10, fee=1), chain_id=CHAIN)
        pool.add({"from": SENDER, "to": "0xdead", "amount": 99, "fee": 0, "nonce": 0}, chain_id=CHAIN)
        pool.add(_signed_tx(sender=OTHER, nonce=0, amount=50, fee=5), chain_id=CHAIN)
        assert pool.pending_cost(CHAIN, SENDER) == 11

    def test_exclude_nonce_skips_replaced_slot(self, pool):
        pool.add(_signed_tx(nonce=0, amount=10, fee=1), chain_id=CHAIN)
        pool.add(_signed_tx(nonce=1, amount=20, fee=2), chain_id=CHAIN)
        assert pool.pending_cost(CHAIN, SENDER, exclude_nonce=0) == 22

    def test_chain_id_isolated(self, pool):
        pool.add(_signed_tx(nonce=0, amount=10, fee=1), chain_id=CHAIN)
        assert pool.pending_cost("other-chain", SENDER) == 0


class TestBatchAdd:
    def test_batch_respects_fee_floor(self, tmp_path):
        pool = DatabaseMempool(f"sqlite:///{tmp_path / 'mp.db'}", max_size=2, min_fee=0)
        pool.batch_add([_signed_tx(sender="0xa", nonce=0, fee=5), _signed_tx(sender="0xb", nonce=0, fee=10)], chain_id=CHAIN)
        # The cheap newcomer is skipped, not allowed to evict.
        pool.batch_add([_signed_tx(sender="0xc", nonce=0, fee=1), _signed_tx(sender="0xd", nonce=0, fee=20)], chain_id=CHAIN)
        fees = sorted(t.fee for t in pool.list_transactions(CHAIN))
        assert fees == [10, 20]

    def test_batch_same_slot_replace(self, tmp_path):
        pool = DatabaseMempool(f"sqlite:///{tmp_path / 'mp.db'}", max_size=10, min_fee=0)
        pool.batch_add([_signed_tx(nonce=0, fee=5), _signed_tx(nonce=0, fee=9, amount=11)], chain_id=CHAIN)
        entries = pool.list_transactions(CHAIN)
        assert len(entries) == 1
        assert entries[0].fee == 9


class TestDatabaseSlotColumns:
    def test_sender_nonce_columns_populated(self, tmp_path):
        pool = DatabaseMempool(f"sqlite:///{tmp_path / 'mp.db'}", min_fee=0)
        pool.add(_signed_tx(sender="0xABCD", nonce=3), chain_id=CHAIN)

        with pool._engine.connect() as conn:
            row = conn.execute(text("SELECT sender, nonce FROM mempool")).one()
        assert row == ("0xabcd", 3)

    def test_existing_table_without_columns_migrated(self, tmp_path):
        """A mempool.db created before the slot columns existed gains them on
        init; pre-existing rows stay NULL and never occupy a slot."""
        db = tmp_path / "old.db"
        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE TABLE mempool (chain_id TEXT NOT NULL, tx_hash TEXT NOT NULL, content TEXT NOT NULL,"
                    " fee INTEGER DEFAULT 0, size_bytes INTEGER DEFAULT 0, received_at REAL NOT NULL,"
                    " PRIMARY KEY (chain_id, tx_hash))"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO mempool (chain_id, tx_hash, content, fee, size_bytes, received_at)"
                    " VALUES ('c', '0xold', '{}', 1, 2, 0.0)"
                )
            )
            conn.commit()
        engine.dispose()

        pool = DatabaseMempool(f"sqlite:///{db}", min_fee=0)
        # The pre-existing NULL row coexists with a same-slot newcomer —
        # upgrading cannot retroactively index what it never recorded.
        pool.add(_signed_tx(nonce=0, fee=5), chain_id="c")
        assert pool.size("c") == 2


class TestDrainTwoPhase:
    def test_drain_still_returns_content(self, tmp_path):
        pool = DatabaseMempool(f"sqlite:///{tmp_path / 'mp.db'}", min_fee=0)
        txs = [_signed_tx(sender=f"0xs{i}", nonce=0, fee=fee) for i, fee in enumerate((1, 50, 100))]
        for tx in txs:
            pool.add(tx, chain_id=CHAIN)
        drained = pool.drain(max_count=2, max_bytes=10**7, chain_id=CHAIN)
        assert [t.fee for t in drained] == [100, 50]
        assert drained[0].content["from"] == "0xs2"
        assert pool.size(CHAIN) == 1


def _account_db(tmp_path, *, balance: int, nonce: int):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Account(chain_id=get_chain_id(), address=SENDER, balance=balance, nonce=nonce))
        session.commit()
    return engine


def _admission_tx(**overrides: Any) -> dict[str, Any]:
    tx = {
        "chain_id": get_chain_id(),
        "type": "TRANSFER",
        "from": SENDER,
        "to": "0x3000000000000000000000000000000000000003",
        "amount": 10,
        "value": 10,
        "fee": 1,
        "nonce": 0,
        "payload": {},
        "signature": "0xsig",
    }
    tx.update(overrides)
    return tx


@pytest.fixture
def patch_session(monkeypatch, tmp_path):
    """Bind ``_validate_transaction_admission`` to a scratch chain database."""

    def _apply(*, balance: int, nonce: int):
        engine = _account_db(tmp_path, balance=balance, nonce=nonce)

        @contextlib.contextmanager
        def _scope(*args: Any, **kwargs: Any):
            with Session(engine) as session:
                yield session

        monkeypatch.setattr(transactions_mod, "session_scope", _scope)
        return engine

    return _apply


class TestAdmission:
    def test_exact_nonce_accepted(self, patch_session):
        patch_session(balance=1000, nonce=0)
        transactions_mod._validate_transaction_admission(_admission_tx(nonce=0), None)

    def test_lookahead_nonce_accepted(self, patch_session):
        patch_session(balance=1000, nonce=0)
        transactions_mod._validate_transaction_admission(_admission_tx(nonce=5), None)

    def test_stale_nonce_rejected(self, patch_session):
        patch_session(balance=1000, nonce=5)
        with pytest.raises(ValueError, match="stale nonce"):
            transactions_mod._validate_transaction_admission(_admission_tx(nonce=3), None)

    def test_beyond_lookahead_rejected(self, patch_session):
        patch_session(balance=1000, nonce=0)
        beyond = settings.mempool_nonce_lookahead + 1
        with pytest.raises(ValueError, match="too far ahead"):
            transactions_mod._validate_transaction_admission(_admission_tx(nonce=beyond), None)

    def test_pending_cost_charged_against_balance(self, patch_session):
        """Two individually affordable transactions may not queue together
        when their combined cost exceeds the balance."""
        patch_session(balance=100, nonce=0)
        pool = InMemoryMempool()
        pool.add(_signed_tx(nonce=0, amount=60, fee=0), chain_id=get_chain_id())
        # amount 50 + pending 60 = 110 > 100
        with pytest.raises(ValueError, match="insufficient balance"):
            transactions_mod._validate_transaction_admission(_admission_tx(nonce=1, amount=50, fee=0), pool)

    def test_replacement_excludes_own_slot(self, patch_session):
        """A same-nonce replacement must not be charged against the tx it
        displaces — it can only ever pay instead of it."""
        patch_session(balance=100, nonce=0)
        pool = InMemoryMempool()
        pool.add(_signed_tx(nonce=0, amount=60, fee=5), chain_id=get_chain_id())
        # amount 90 + fee 6 = 96 <= 100 once the pending 65 at nonce 0 is excluded
        transactions_mod._validate_transaction_admission(_admission_tx(nonce=0, amount=90, fee=6), pool)

    def test_mempool_none_tolerated(self, patch_session):
        """Gossip admission callers may pass mempool=None — pending cost is 0."""
        patch_session(balance=1000, nonce=0)
        transactions_mod._validate_transaction_admission(_admission_tx(nonce=0), None)
