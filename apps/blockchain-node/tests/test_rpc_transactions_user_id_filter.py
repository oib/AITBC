"""Tests for the ``user_id`` payload filter on GET /rpc/transactions (#2349).

``aitbc exchange-island orders --user`` sent ``user_id`` but the endpoint
had no such parameter — FastAPI dropped it and every caller got the full
unfiltered list. ``user_id`` now binds in SQL (same payload-filter pipeline
as island_id/pair/status/order_id) and is re-checked Python-side.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from aitbc_chain.base_models import Transaction
from aitbc_chain.rpc.transactions import query_transactions

ALICE = "0x1111111111111111111111111111111111111111"
BOB = "0x2222222222222222222222222222222222222222"


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture(name="patched_db")
def patched_db_fixture(session, monkeypatch):
    @contextmanager
    def _fake_scope(chain_id: str = ""):
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _fake_scope)
    return session


def _exchange_tx(chain_id: str, tx_hash: str, user_id: str, status: str = "open", pair: str = "AIT-ETH") -> Transaction:
    return Transaction(
        chain_id=chain_id,
        tx_hash=tx_hash,
        block_height=1,
        sender=user_id,
        recipient="0x0000000000000000000000000000000000000000",
        payload={"user_id": user_id, "status": status, "pair": pair, "order_id": tx_hash},
        type="EXCHANGE",
        status="confirmed",
        timestamp=datetime(2026, 11, 21, tzinfo=UTC),
    )


@pytest.fixture(name="seeded_db")
def seeded_db_fixture(patched_db):
    patched_db.add(_exchange_tx("test-chain", "0xa1", ALICE))
    patched_db.add(_exchange_tx("test-chain", "0xb1", BOB))
    patched_db.add(_exchange_tx("test-chain", "0xb2", BOB, status="filled"))
    patched_db.add(
        Transaction(
            chain_id="test-chain",
            tx_hash="0xplain",
            block_height=1,
            sender=ALICE,
            recipient="0x0000000000000000000000000000000000000000",
            payload={},
            type="TRANSFER",
            status="confirmed",
            timestamp=datetime(2026, 11, 21, tzinfo=UTC),
        )
    )
    patched_db.commit()
    return patched_db


def test_user_id_returns_only_that_users_rows(seeded_db):
    result = query_transactions(None, chain_id="test-chain", transaction_type="EXCHANGE", user_id=ALICE)
    assert {t["tx_hash"] for t in result} == {"0xa1"}


def test_user_id_composes_with_status_and_pair(seeded_db):
    result = query_transactions(
        None,
        chain_id="test-chain",
        transaction_type="EXCHANGE",
        user_id=BOB,
        status="filled",
        pair="AIT-ETH",
    )
    assert {t["tx_hash"] for t in result} == {"0xb2"}
    # A status the user has no rows for yields nothing, not the full list.
    result = query_transactions(
        None,
        chain_id="test-chain",
        transaction_type="EXCHANGE",
        user_id=ALICE,
        status="filled",
    )
    assert result == []


def test_user_id_omitted_returns_all_exchange_rows(seeded_db):
    result = query_transactions(None, chain_id="test-chain", transaction_type="EXCHANGE")
    assert {t["tx_hash"] for t in result} == {"0xa1", "0xb1", "0xb2"}
