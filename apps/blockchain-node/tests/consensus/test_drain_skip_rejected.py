"""DRAIN-SKIP-SILENT-1 (#669) — rejected drained txs must leave a terminal record.

A drained mempool entry is deleted whether or not it seals, so a tx the apply
path refused used to vanish: the submitter's hash query found nothing and any
pre-existing row sat ``pending`` forever. ``_process_txs_sequential`` now
collects ``(tx, reason)`` for each refusal and ``_persist_rejected_txs``
upserts ``status='rejected'`` into the transaction table so the RPC surfaces
the terminal outcome.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aitbc_chain.base_models import Account, Transaction, _to_ait_address  # noqa: E402
from aitbc_chain.consensus.poa import PoAProposer  # noqa: E402
from aitbc_chain.metadata import chain_metadata  # noqa: E402
from sqlmodel import Session, create_engine, select  # noqa: E402

CHAIN = "drain-skip-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
SENDER = "0x" + "aa" * 20
RECIPIENT = "0x" + "bb" * 20
TX_HASH = "0x" + "5e" * 32


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    chain_metadata.create_all(engine)
    return engine


def _proposer() -> PoAProposer:
    proposer = PoAProposer.__new__(PoAProposer)
    proposer._config = SimpleNamespace(chain_id=CHAIN)
    proposer._logger = MagicMock()
    return proposer


def _pending_tx(**content_overrides: Any) -> SimpleNamespace:
    content: dict[str, Any] = {
        "from": SENDER,
        "to": RECIPIENT,
        "amount": 5,
        "fee": 1,
        "nonce": 0,
        "type": "TRANSFER",
        "payload": {},
        "signature": "0xsig",
    }
    content.update(content_overrides)
    return SimpleNamespace(tx_hash=TX_HASH, content=content, received_at=0.0, fee=1, size_bytes=1)


def test_skipped_tx_leaves_rejected_row(tmp_path):
    """Insufficient-balance tx is drained, skipped — and recorded rejected."""
    engine = _engine(tmp_path)
    canonical_sender = _to_ait_address(SENDER)
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=canonical_sender, balance=0, nonce=0))
        session.commit()

    tx = _pending_tx()
    proposer = _proposer()
    rejected: list[tuple[Any, str]] = []
    with Session(engine) as session:
        account = session.get(Account, (CHAIN, canonical_sender))
        processed, _changed, ok = proposer._process_txs_sequential(
            session, [tx], {canonical_sender: account}, {}, next_height=1, timestamp=T0, rejected=rejected
        )
        assert ok is True
        assert processed == []
        assert len(rejected) == 1 and rejected[0][0] is tx
        # Abort path semantics: proposal rolls back, rejections commit alone.
        session.rollback()
        proposer._persist_rejected_txs(session, rejected, next_height=1, timestamp=T0, commit=True)

    with Session(engine) as session:
        row = session.exec(select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.tx_hash == TX_HASH)).one()
        assert row.status == "rejected"
        assert row.block_height is None
        assert row.sender == SENDER and row.recipient == RECIPIENT
        meta = json.loads(row.tx_metadata)
        assert "insufficient balance" in meta["rejected_reason"]
        assert meta["rejected_at_height"] == 1
    engine.dispose()


def test_confirmed_row_is_not_clobbered(tmp_path):
    """A sealed/confirmed transaction row keeps its status — the rejection
    write-back only covers rows that never reached a terminal state."""
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=TX_HASH,
                block_height=3,
                sender=SENDER,
                recipient=RECIPIENT,
                payload={},
                status="confirmed",
                type="TRANSFER",
            )
        )
        session.commit()

    proposer = _proposer()
    with Session(engine) as session:
        proposer._persist_rejected_txs(
            session, [(_pending_tx(), "some later refusal")], next_height=5, timestamp=T0, commit=True
        )

    with Session(engine) as session:
        row = session.exec(select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.tx_hash == TX_HASH)).one()
        assert row.status == "confirmed"
        assert row.block_height == 3
    engine.dispose()


def test_pending_row_is_flipped_to_rejected(tmp_path):
    """A pre-existing non-terminal row (e.g. submitted-but-unsealed) is
    updated in place rather than duplicated (chain_id/tx_hash is unique)."""
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=TX_HASH,
                block_height=None,
                sender=SENDER,
                recipient=RECIPIENT,
                payload={},
                status="pending",
                type="TRANSFER",
            )
        )
        session.commit()

    proposer = _proposer()
    with Session(engine) as session:
        proposer._persist_rejected_txs(
            session, [(_pending_tx(), "failed v9 bridge-lock authorization")], next_height=7, timestamp=T0, commit=True
        )

    with Session(engine) as session:
        rows = session.exec(select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.tx_hash == TX_HASH)).all()
        assert len(rows) == 1
        assert rows[0].status == "rejected"
        assert "bridge-lock authorization" in json.loads(rows[0].tx_metadata)["rejected_reason"]
    engine.dispose()


def test_rejected_tombstone_does_not_block_sealed_reapply(tmp_path):
    """#704: an intake-rejected row must not count as processed — when the same
    tx later seals in a block, the apply path lands over the tombstone."""
    engine = _engine(tmp_path)
    canonical_sender = _to_ait_address(SENDER)
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=canonical_sender, balance=10_000, nonce=0))
        session.add(Account(chain_id=CHAIN, address=RECIPIENT, balance=0, nonce=0))
        # the tombstone the intake rejection wrote (insufficient balance then)
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=TX_HASH,
                sender=SENDER,
                recipient=RECIPIENT,
                payload={"type": "TRANSFER"},
                envelope={},
                created_at=datetime.now(UTC),
                nonce=0,
                value=1,
                fee=1,
                type="TRANSFER",
                status="rejected",
                timestamp=0.0,
                tx_metadata='{"rejected_reason": "insufficient balance", "rejected_at_height": 1}',
            )
        )
        session.commit()

    proposer = _proposer()
    tx = _pending_tx()
    rejected: list[tuple[Any, str]] = []
    with Session(engine) as session:
        account = session.get(Account, (CHAIN, canonical_sender))
        processed, _changed, ok = proposer._process_txs_sequential(
            session, [tx], {canonical_sender: account}, {}, next_height=2, timestamp=T0, rejected=rejected
        )
        assert ok is True
        # The tombstone no longer counts as processed: whatever verdict the tx
        # earns downstream, it is NOT the replay-attack reason. (The fake sig
        # below fails real signature validation — that reject is expected and
        # irrelevant to the gate under test.)
        for _t, reason in rejected:
            assert "replay" not in str(reason).lower()
