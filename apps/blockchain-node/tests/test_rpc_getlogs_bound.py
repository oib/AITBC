"""eth_getLogs answers within a fixed row and block budget (#835).

``POST /rpc/eth_getLogs`` is public. ``get_logs`` used to read every receipt
on the chain when ``from_block``/``to_block`` were omitted and filter events
in Python; a bounded-parameter call could still pull the full table. The
budgets are a block span, a receipt row cap bound in SQL, and a log-entry
cap — a caller needing an older or deeper window paginates by block range.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event

from aitbc_chain.base_models import Receipt
from aitbc_chain.rpc import gossip
from aitbc_chain.config import settings as _settings
from aitbc_chain.rpc.gossip import GetLogsRequest, get_logs

CHAIN = "test-chain"
ADDR = "0xContract"


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture(name="patched_db")
def patched_db_fixture(session, monkeypatch):
    @contextmanager
    def _fake_scope(chain_id: str = ""):
        yield session

    monkeypatch.setattr(gossip, "session_scope", _fake_scope)
    return session


def _receipt(height: int, events: int = 1, address: str = ADDR) -> Receipt:
    return Receipt(
        chain_id=CHAIN,
        job_id=f"job-{height}",
        receipt_id=f"0xr{height}",
        block_height=height,
        payload={"events": [{"address": address, "topics": ["0xt"], "data": "0x1", "logIndex": i} for i in range(events)]},
    )


def _call() -> object:
    return get_logs(MagicMock(), GetLogsRequest(), chain_id=CHAIN)


def _select_statements(engine):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listens_for(engine, "before_cursor_execute")(capture)
    return statements, capture


def test_an_unbounded_request_reads_a_bounded_window(patched_db, monkeypatch):
    """No from/to: the scan covers only the newest getlogs_max_block_span blocks."""
    monkeypatch.setattr(_settings, "getlogs_max_block_span", 3, raising=False)
    for h in range(1, 11):
        patched_db.add(_receipt(h))
    patched_db.commit()

    resp = _call()

    # Blocks 8, 9, 10 only — the open-ended request is clamped, not full-table.
    assert {log.block_number for log in resp.logs} == {8, 9, 10}


def test_the_receipt_cap_is_bound_in_sql(patched_db, engine):
    """The row budget goes into LIMIT, not a Python slice after fetch."""
    for h in range(1, 6):
        patched_db.add(_receipt(h))
    patched_db.commit()

    statements, capture = _select_statements(engine)
    try:
        resp = _call()
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert resp.count <= 5
    assert any("LIMIT" in s.upper() for s in statements), statements


def test_an_explicit_range_inside_the_budget_is_honoured(patched_db, monkeypatch):
    monkeypatch.setattr(_settings, "getlogs_max_block_span", 100, raising=False)
    for h in range(1, 11):
        patched_db.add(_receipt(h))
    patched_db.commit()

    resp = get_logs(MagicMock(), GetLogsRequest(from_block=3, to_block=5), chain_id=CHAIN)

    assert {log.block_number for log in resp.logs} == {3, 4, 5}


def test_a_span_wider_than_the_budget_is_clamped_from_the_top(patched_db, monkeypatch):
    monkeypatch.setattr(_settings, "getlogs_max_block_span", 3, raising=False)
    for h in range(1, 11):
        patched_db.add(_receipt(h))
    patched_db.commit()

    resp = get_logs(MagicMock(), GetLogsRequest(from_block=1, to_block=10), chain_id=CHAIN)

    assert {log.block_number for log in resp.logs} == {8, 9, 10}


def test_the_log_entry_count_is_capped(patched_db, monkeypatch):
    monkeypatch.setattr(_settings, "getlogs_max_logs", 3, raising=False)
    for h in range(1, 4):
        patched_db.add(_receipt(h, events=3))
    patched_db.commit()

    resp = _call()

    assert resp.count == 3
    assert len(resp.logs) == 3


def test_address_and_topic_filters_still_apply(patched_db, monkeypatch):
    monkeypatch.setattr(_settings, "getlogs_max_block_span", 100, raising=False)
    patched_db.add(_receipt(1, address=ADDR))
    patched_db.add(_receipt(2, address="0xOther"))
    patched_db.commit()

    resp = get_logs(MagicMock(), GetLogsRequest(address=ADDR), chain_id=CHAIN)

    assert [log.address for log in resp.logs] == [ADDR]
    assert resp.logs[0].block_number == 1
