"""#1082 pins: the coin grant is recorded before it is paid, claims resolve
to a tx hash or FAILED, and an unreadable ledger parks the request."""

from __future__ import annotations

import sqlite3

import pytest

from agent_app.websocket import agent_stream


@pytest.fixture()
def scratch_db(monkeypatch, tmp_path) -> str:
    db = str(tmp_path / "coins.db")
    monkeypatch.setenv("AGENT_DB_PATH", db)
    return db


def _rows(db: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM coin_requests").fetchall()
    conn.close()
    return rows


def test_claim_row_exists_before_pay(scratch_db):
    """The claim lands BEFORE signing — a crash mid-send leaves a findable
    claiming: marker, not an unrecorded payout."""
    rid = agent_stream._record_claiming_coin_request("agent-1", 5, "0x" + "aa" * 20)
    assert rid and rid.startswith("auto-agent-1-")
    rows = _rows(scratch_db)
    assert len(rows) == 1
    assert rows[0]["status"] == "APPROVED"
    assert rows[0]["transaction_hash"].startswith("claiming:")


def test_finish_claim_writes_tx_hash_and_failed(scratch_db):
    rid = agent_stream._record_claiming_coin_request("agent-1", 5, "0x" + "aa" * 20)
    agent_stream._finish_claimed_coin_request(rid, "0x" + "cd" * 32)
    assert _rows(scratch_db)[0]["transaction_hash"] == "0x" + "cd" * 32

    rid2 = agent_stream._record_claiming_coin_request("agent-2", 5, "0x" + "bb" * 20)
    agent_stream._finish_claimed_coin_request(rid2, "", failed=True)
    rows = {r["id"]: r for r in _rows(scratch_db)}
    assert rows[rid2]["status"] == "FAILED"


def test_unreadable_db_parks_instead_of_paying(monkeypatch, tmp_path):
    """#1082: an unanswerable prior-grant lookup returns None → parked, not
    paid blind."""
    bad = tmp_path / "unreadable.db"
    bad.write_bytes(b"\x00" * 64)  # not sqlite
    monkeypatch.setenv("AGENT_DB_PATH", str(bad))
    assert agent_stream._has_received_initial_coins("agent-1", "0x" + "aa" * 20) is None
    # a claim insert against the same unreadable store must not claim a row
    assert agent_stream._record_claiming_coin_request("agent-1", 5, "0x" + "aa" * 20) is None


def test_claim_ids_are_uuid_not_timestamp(scratch_db):
    """#1082: two grants in the same second no longer collide on a timestamp id."""
    a = agent_stream._record_claiming_coin_request("agent-1", 5, "0x" + "aa" * 20)
    b = agent_stream._record_claiming_coin_request("agent-1", 5, "0x" + "aa" * 20)
    assert a != b
