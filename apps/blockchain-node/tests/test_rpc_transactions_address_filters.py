"""Tests for the sender/recipient filters on GET /rpc/transactions.

The `address` parameter matches either side of a transaction, which makes
"what did this account send" unanswerable (KEYTRACE-1 filtered senders by
hand). `sender` and `recipient` mirror `address`'s spelling handling and are
applied in SQL alongside it — all supplied filters must hold.
"""

from __future__ import annotations

import pytest
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import event

from aitbc_chain.base_models import Transaction
from aitbc_chain.rpc.transactions import query_transactions

SENDER = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"
OTHER = "0xcF171914819E9435aC5751D29c0DF313b10f8Ee3"  # EIP-55 checksummed


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


def _tx(chain_id: str, tx_hash: str, sender: str, recipient: str, tx_type: str = "TRANSFER") -> Transaction:
    return Transaction(
        chain_id=chain_id,
        tx_hash=tx_hash,
        block_height=1,
        sender=sender,
        recipient=recipient,
        payload={},
        type=tx_type,
        status="confirmed",
        timestamp=datetime(2026, 10, 7, tzinfo=UTC),
    )


@pytest.fixture(name="seeded_db")
def seeded_db_fixture(patched_db):
    patched_db.add(_tx("test-chain", "0xsend", SENDER, OTHER))
    patched_db.add(_tx("test-chain", "0xrecv", OTHER, SENDER))
    patched_db.add(_tx("test-chain", "0xother", OTHER, OTHER))
    patched_db.commit()
    return patched_db


def test_sender_returns_only_sends(seeded_db):
    result = query_transactions(None, chain_id="test-chain", sender=SENDER)
    assert {t["tx_hash"] for t in result} == {"0xsend"}


def test_recipient_returns_only_receipts(seeded_db):
    result = query_transactions(None, chain_id="test-chain", recipient=SENDER)
    assert {t["tx_hash"] for t in result} == {"0xrecv"}


def test_address_still_matches_either_side(seeded_db):
    result = query_transactions(None, chain_id="test-chain", address=SENDER)
    assert {t["tx_hash"] for t in result} == {"0xsend", "0xrecv"}


def test_combined_filters_intersect(seeded_db):
    result = query_transactions(None, chain_id="test-chain", address=SENDER, sender=SENDER)
    assert {t["tx_hash"] for t in result} == {"0xsend"}
    result = query_transactions(None, chain_id="test-chain", address=SENDER, sender=SENDER, recipient=SENDER)
    assert result == []


def test_lowercase_spelling_matches_checksum_row(seeded_db):
    result = query_transactions(None, chain_id="test-chain", sender=SENDER.lower())
    assert {t["tx_hash"] for t in result} == {"0xsend"}


def test_checksum_query_matches_lowercase_row(patched_db):
    patched_db.add(_tx("test-chain", "0xlower", SENDER.lower(), OTHER.lower()))
    patched_db.commit()
    result = query_transactions(None, chain_id="test-chain", sender=SENDER)
    assert {t["tx_hash"] for t in result} == {"0xlower"}


def test_limit_counts_after_filter(seeded_db):
    # Two matching rows exist; limit=1 keeps only the newest (highest id).
    result = query_transactions(None, chain_id="test-chain", address=OTHER, limit=1)
    assert len(result) == 1


def _select_statements(engine):
    """Statement capture for asserting the query's SQL shape."""
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listens_for(engine, "before_cursor_execute")(capture)
    return statements, capture


def test_type_filter_applies_in_sql(patched_db, engine):
    """transaction_type is a column: the filter belongs in the WHERE clause,
    not the Python loop over every row on the chain."""
    patched_db.add(_tx("test-chain", "0xt1", SENDER, OTHER, tx_type="TRANSFER"))
    patched_db.add(_tx("test-chain", "0xe1", SENDER, OTHER, tx_type="ESCROW_LOCK"))
    patched_db.commit()

    statements, capture = _select_statements(engine)
    try:
        result = query_transactions(None, chain_id="test-chain", transaction_type="ESCROW_LOCK")
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert {t["tx_hash"] for t in result} == {"0xe1"}
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert any("type" in s for s in selects), selects


def test_limit_is_applied_in_sql(patched_db, engine):
    """RPC-TX-QUERY-UNBOUNDED-1: with no payload-field filter the limit binds
    in SQL — the query must not read the whole table to slice it in Python."""
    for i in range(5):
        patched_db.add(_tx("test-chain", f"0x{i}", SENDER, OTHER))
    patched_db.commit()

    statements, capture = _select_statements(engine)
    try:
        result = query_transactions(None, chain_id="test-chain", limit=2)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert [t["tx_hash"] for t in result] == ["0x4", "0x3"]  # newest first
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert any("LIMIT" in s.upper() for s in selects), selects


def test_payload_filter_path_still_searches_past_the_limit(patched_db):
    """Payload filters still run in Python, so a SQL limit there would be
    wrong: an older matching row must still be found beyond the window."""
    old = _tx("test-chain", "0xold", SENDER, OTHER)
    old.payload = {"island_id": "isl-1"}
    patched_db.add(old)
    for i in range(3):
        patched_db.add(_tx("test-chain", f"0xnew{i}", SENDER, OTHER))
    patched_db.commit()

    result = query_transactions(None, chain_id="test-chain", island_id="isl-1", limit=1)
    assert [t["tx_hash"] for t in result] == ["0xold"]
