"""Tests for #2464: the bridge finalizer must not overwrite a refunded source row.

``_finalize_confirmed_transfers`` mirrored completion onto the source-chain
row with ``status != "completed"`` — which also matched ``refunded``,
erasing the only local marker that a transfer was both refunded and
released (double pay, #2459). The source row is now promoted only from a
non-terminal status; a ``refunded`` row is left untouched, logged as an
error naming the transfer and tx hashes, and counted on
``bridge_finalizer_refunded_source_row_total``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.models import CrossChainTransfer, Transaction

SOURCE = "chain-a"
TARGET = "chain-b"
TRANSFER_ID = "0x" + "ab" * 32
LOCK_HASH = "0x" + "11" * 32
RELEASE_HASH = "0x" + "22" * 32


def _engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    return engine


@pytest.fixture()
def two_chain_bridge():
    """Bridge whose session factory routes each chain to its own engine."""
    engines = {SOURCE: _engine(), TARGET: _engine()}

    def factory(chain_id: str = ""):
        return Session(engines[chain_id])

    bridge = CrossChainBridge(factory)
    yield bridge, engines
    for engine in engines.values():
        chain_metadata.drop_all(engine)
        engine.dispose()


def _source_record(status: str) -> CrossChainTransfer:
    return CrossChainTransfer(
        transfer_id=TRANSFER_ID,
        source_chain=SOURCE,
        target_chain=TARGET,
        sender="0xsender",
        recipient="0xrecipient",
        amount=1000,
        asset="native",
        status=status,
        source_tx_hash=LOCK_HASH,
        lock_time=datetime.now(UTC),
    )


def _target_record() -> CrossChainTransfer:
    return CrossChainTransfer(
        transfer_id=TRANSFER_ID,
        source_chain=SOURCE,
        target_chain=TARGET,
        sender="0xsender",
        recipient="0xrecipient",
        amount=1000,
        asset="native",
        status="confirmed",
        source_tx_hash=LOCK_HASH,
        target_tx_hash=RELEASE_HASH,
        lock_time=datetime.now(UTC),
        confirm_time=datetime.now(UTC),
    )


def _seed_target_release(engine) -> None:
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=TARGET,
                tx_hash=RELEASE_HASH,
                type="BRIDGE_RELEASE",
                status="sealed",
                sender="0xrelayer",
                recipient="0xrecipient",
                value=1000,
                fee=0,
                nonce=0,
                payload={},
                envelope={},
                block_height=11,
            )
        )
        session.commit()


def test_refunded_source_row_survives_finalize(two_chain_bridge, caplog):
    bridge, engines = two_chain_bridge
    metrics_registry.reset()
    with Session(engines[SOURCE]) as session:
        session.add(_source_record("refunded"))
        session.commit()
    with Session(engines[TARGET]) as session:
        session.add(_target_record())
        session.commit()
    _seed_target_release(engines[TARGET])

    assert bridge._finalize_confirmed_transfers(TARGET) == 1

    # Target row completes — the release really did seal.
    with Session(engines[TARGET]) as session:
        target = session.get(CrossChainTransfer, TRANSFER_ID)
        assert target is not None and target.status == "completed"

    # Source row keeps 'refunded' and none of the release fields leak in.
    with Session(engines[SOURCE]) as session:
        source = session.get(CrossChainTransfer, TRANSFER_ID)
        assert source is not None
        assert source.status == "refunded"
        assert source.target_tx_hash is None
        assert source.proof_hash is None
        assert source.confirm_time is None

    assert metrics_registry._counters.get("bridge_finalizer_refunded_source_row_total") == 1.0
    assert any("double pay" in r.message for r in caplog.records)


def test_nonterminal_source_row_still_promoted(two_chain_bridge):
    bridge, engines = two_chain_bridge
    with Session(engines[SOURCE]) as session:
        session.add(_source_record("confirmed"))
        session.commit()
    with Session(engines[TARGET]) as session:
        session.add(_target_record())
        session.commit()
    _seed_target_release(engines[TARGET])

    assert bridge._finalize_confirmed_transfers(TARGET) == 1

    with Session(engines[SOURCE]) as session:
        source = session.get(CrossChainTransfer, TRANSFER_ID)
        assert source is not None
        assert source.status == "completed"
        assert source.target_tx_hash == RELEASE_HASH
        assert source.confirm_time is not None
