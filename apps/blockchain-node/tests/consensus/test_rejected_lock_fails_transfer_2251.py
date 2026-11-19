"""#2251 — a BRIDGE_LOCK refused at apply must fail its pending bridge transfer.

Intake writes the ``CrossChainTransfer`` row ``pending`` before the lock tx is
applied; the apply-time rejection path (#669) recorded the tx ``rejected`` but
left the transfer pending forever (0xaa3c1fd4… on hub: bad ``bridge_signature``).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest  # noqa: E402
from aitbc_chain.base_models import Transaction  # noqa: E402
from aitbc_chain.base_models_aux import CrossChainTransfer  # noqa: E402
from aitbc_chain.consensus.poa import PoAProposer  # noqa: E402
from aitbc_chain.metadata import chain_metadata  # noqa: E402
from sqlmodel import Session, create_engine, select  # noqa: E402

CHAIN = "bc-2-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
SENDER = "0x" + "aa" * 20
LOCK_HASH = "0x" + "5e" * 32
REASON = "BRIDGE_LOCK must carry a valid bridge_signature from the bridge authority"


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    chain_metadata.create_all(eng)
    yield eng
    eng.dispose()


def _proposer() -> PoAProposer:
    proposer = PoAProposer.__new__(PoAProposer)
    proposer._config = SimpleNamespace(chain_id=CHAIN)
    proposer._logger = MagicMock()
    return proposer


def _tx(tx_hash: str = LOCK_HASH, tx_type: str = "BRIDGE_LOCK") -> SimpleNamespace:
    content: dict[str, Any] = {
        "from": SENDER,
        "to": "bridge_lock",
        "amount": 30_000_000,
        "fee": 30_000,
        "nonce": 74,
        "type": tx_type,
        "payload": {},
    }
    return SimpleNamespace(tx_hash=tx_hash, content=content, received_at=0.0, fee=1, size_bytes=1)


def _transfer(tx_hash: str = LOCK_HASH, status: str = "pending", source_chain: str = CHAIN) -> CrossChainTransfer:
    return CrossChainTransfer(
        transfer_id=tx_hash,
        source_chain=source_chain,
        target_chain="bc-2-island-1",
        sender=SENDER,
        recipient="0x" + "c1" * 20,
        amount=30_000_000,
        status=status,
        source_tx_hash=tx_hash,
    )


def _status(engine, tx_hash: str = LOCK_HASH) -> str:
    with Session(engine) as session:
        return session.exec(select(CrossChainTransfer).where(CrossChainTransfer.transfer_id == tx_hash)).one().status


def _persist(engine, txs: list[Any]) -> None:
    with Session(engine) as session:
        _proposer()._persist_rejected_txs(session, [(t, REASON) for t in txs], next_height=9, timestamp=T0, commit=True)


def test_rejected_lock_without_tx_row_fails_pending_transfer(engine):
    with Session(engine) as session:
        session.add(_transfer())
        session.commit()
    _persist(engine, [_tx()])
    assert _status(engine) == "failed"
    with Session(engine) as session:
        assert session.exec(select(Transaction).where(Transaction.tx_hash == LOCK_HASH)).one().status == "rejected"


def test_rejected_lock_with_existing_tx_row_fails_pending_transfer(engine):
    with Session(engine) as session:
        session.add(_transfer())
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=LOCK_HASH,
                sender=SENDER,
                recipient="bridge_lock",
                payload={},
                status="pending",
                type="BRIDGE_LOCK",
            )
        )
        session.commit()
    _persist(engine, [_tx()])
    assert _status(engine) == "failed"


def test_non_lock_rejection_leaves_transfer_alone(engine):
    with Session(engine) as session:
        session.add(_transfer())
        session.commit()
    _persist(engine, [_tx(tx_type="TRANSFER")])
    assert _status(engine) == "pending"


@pytest.mark.parametrize("status", ["locked", "confirmed", "completed", "refunded"])
def test_only_pending_transfer_is_failed(engine, status):
    with Session(engine) as session:
        session.add(_transfer(status=status))
        session.commit()
    _persist(engine, [_tx()])
    assert _status(engine) == status


def test_other_source_chain_and_other_hash_untouched(engine):
    other = "0x" + "77" * 32
    with Session(engine) as session:
        session.add(_transfer(source_chain="bc-3"))
        session.add(_transfer(tx_hash=other))
        session.commit()
    _persist(engine, [_tx()])
    assert _status(engine) == "pending"
    assert _status(engine, other) == "pending"


def test_rejected_lock_without_transfer_row_is_harmless(engine):
    _persist(engine, [_tx()])
    with Session(engine) as session:
        assert session.exec(select(Transaction).where(Transaction.tx_hash == LOCK_HASH)).one().status == "rejected"
