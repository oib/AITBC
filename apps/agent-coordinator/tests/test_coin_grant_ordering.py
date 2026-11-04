"""Pin the #1082 ordering: claims recorded before payout, failures marked."""

import os
import sqlite3
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from agent_app.websocket import agent_stream as ws


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "coin.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(path))
    return path


def _rows(path):
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT id,status,transaction_hash FROM coin_requests").fetchall()
    conn.close()
    return rows


def test_claim_row_written_before_pay(db):
    rid = ws._record_claiming_coin_request("sender1", 100, "0xabc")
    assert rid is not None
    (id_, status, txh) = _rows(db)[0]
    assert id_ == rid and status == "APPROVED" and txh.startswith("claiming:")


def test_finish_replaces_marker_with_tx_hash(db):
    rid = ws._record_claiming_coin_request("s", 100, "0xabc")
    ws._finish_claimed_coin_request(rid, "0xhash")
    assert _rows(db)[0][2] == "0xhash"


def test_failed_send_marks_claim_failed(db):
    rid = ws._record_claiming_coin_request("s", 100, "0xabc")
    ws._finish_claimed_coin_request(rid, "", failed=True)
    assert _rows(db)[0][1] == "FAILED"


def test_unreadable_ledger_returns_none(db, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", "/nonexistent-dir-xyz/coin.db")
    assert ws._record_claiming_coin_request("s", 100, "0xabc") is None


def test_unreadable_ledger_parks_prior_check(db, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", "/nonexistent-dir-xyz/coin.db")
    assert ws._has_received_initial_coins("s", "0xabc") is None
