"""#837: REQUEST_COINS grants go through the hourly/daily auto budget and a real
amount check — the wallet binding stays the only per-identity gate.

Pre-fix, the first-grant path signed on the spot and the strategy-approved
path compared an unvalidated JSON `amount` against an undocumented knob. Now:
non-positive/non-int/above-ceiling amounts are refused before signing, and a
grant that would exceed the rolling budget is parked for manual review.
"""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_app import config as _config_mod  # noqa: F401  (import order like test_phase_c_auth)
from agent_app.websocket import agent_stream
from agent_app.config import settings
from agent_app.services import coin_request_policy


def _db(tmp_path, grants=()):
    """An agent coin-requests DB with `grants` (amount, created_at) APPROVED rows."""
    db = tmp_path / "agent.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE coin_requests (id TEXT, sender TEXT, recipient TEXT, amount INTEGER, "
        "wallet_address TEXT, status TEXT, approval_mode TEXT, approved_by TEXT, approved_at TEXT, "
        "created_at TEXT, expires_at TEXT, transaction_hash TEXT, audit_log TEXT)"
    )
    for i, (amount, created) in enumerate(grants):
        conn.execute(
            "INSERT INTO coin_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"g{i}", "s", "r", amount, "w", "APPROVED", "automatic", "t", created, created, created, "0x", "{}"),
        )
    conn.commit()
    conn.close()
    return db


def _cm():
    cm = agent_stream.ConnectionManager()
    cm.send_personal_message = AsyncMock(return_value=True)
    return cm


def _msg(sender: str, content) -> dict:
    return {"sender_id": sender, "content": content}


@pytest.fixture(autouse=True)
def _disabled(monkeypatch):
    """Wallet binding off: these tests exercise the budget/amount path, not the gate."""
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
    monkeypatch.setattr(agent_stream, "_has_received_initial_coins", lambda *a: True)


def _parks(result):
    assert result["action"] == "coin_request_received"
    assert result["status"] == "pending_approval"
    assert "budget" in result["reason"]


def _signable(monkeypatch):
    """Everything after the gates would succeed — fail loudly if we get there."""
    fake_tx = MagicMock()
    fake_tx.generate_signed_transaction = MagicMock(return_value={"signed": True})
    monkeypatch.setattr(agent_stream, "TransactionService", lambda: fake_tx)
    monkeypatch.setattr(
        agent_stream, "_submit_transaction", lambda tx: {"success": True, "transaction_hash": "0x" + "ff" * 32}
    )
    return fake_tx


def test_strategy_grant_parked_when_hourly_budget_exhausted(monkeypatch, tmp_path):
    now = datetime.now(UTC).replace(tzinfo=None)
    db = _db(tmp_path, grants=[(coin_request_policy.auto_budget_per_hour(), now.isoformat())])
    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    monkeypatch.setenv("HERMES_DB_PATH", str(db))
    fake_tx = _signable(monkeypatch)
    monkeypatch.setattr(
        agent_stream,
        "_get_approval_strategy",
        lambda: (MagicMock(approve=lambda req: {"approved": True, "reason": "auto"}), "automatic"),
    )
    monkeypatch.setattr(agent_stream, "_record_pending_coin_request", lambda *a: "req-parked")

    result = asyncio.run(
        agent_stream.request_coins_handler(
            _msg("agent-1", json.dumps({"amount": 1, "wallet_address": "0xw"})), _cm(), MagicMock()
        )
    )
    _parks(result)
    fake_tx.generate_signed_transaction.assert_not_called()


def test_first_grant_parked_when_budget_exhausted(monkeypatch, tmp_path):
    now = datetime.now(UTC).replace(tzinfo=None)
    db = _db(tmp_path, grants=[(coin_request_policy.auto_budget_per_day(), now.isoformat())])
    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    monkeypatch.setenv("HERMES_DB_PATH", str(db))
    fake_tx = _signable(monkeypatch)
    monkeypatch.setattr(agent_stream, "_has_received_initial_coins", lambda *a: False)
    monkeypatch.setattr(agent_stream, "_record_pending_coin_request", lambda *a: "req-parked")

    result = asyncio.run(agent_stream.request_coins_handler(_msg("agent-1", ""), _cm(), MagicMock()))
    _parks(result)
    fake_tx.generate_signed_transaction.assert_not_called()


def test_old_grants_outside_the_window_do_not_trip(monkeypatch, tmp_path):
    old = (datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=48)).isoformat()
    db = _db(tmp_path, grants=[(coin_request_policy.auto_budget_per_day() * 2, old)])
    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    monkeypatch.setenv("HERMES_DB_PATH", str(db))
    fake_tx = _signable(monkeypatch)
    monkeypatch.setattr(agent_stream, "_record_coin_request", lambda *a: None)
    monkeypatch.setattr(
        agent_stream,
        "_get_approval_strategy",
        lambda: (MagicMock(approve=lambda req: {"approved": True, "reason": "auto"}), "automatic"),
    )

    result = asyncio.run(
        agent_stream.request_coins_handler(
            _msg("agent-1", json.dumps({"amount": 1, "wallet_address": "0xw"})), _cm(), MagicMock()
        )
    )
    assert result["action"] == "coins_transferred"
    fake_tx.generate_signed_transaction.assert_called_once()


@pytest.mark.parametrize("bad", [0, -5, "100", 3.7, None, True])
def test_amount_must_be_a_positive_int(monkeypatch, tmp_path, bad):
    db = _db(tmp_path)
    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    fake_tx = _signable(monkeypatch)
    result = asyncio.run(
        agent_stream.request_coins_handler(
            _msg("agent-1", json.dumps({"amount": bad, "wallet_address": "0xw"})), _cm(), MagicMock()
        )
    )
    assert result["action"] == "coin_request_failed"
    fake_tx.generate_signed_transaction.assert_not_called()


def test_amount_above_the_ceiling_refused(monkeypatch, tmp_path):
    db = _db(tmp_path)
    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    fake_tx = _signable(monkeypatch)
    over = coin_request_policy.auto_approve_ceiling() + 1
    result = asyncio.run(
        agent_stream.request_coins_handler(
            _msg("agent-1", json.dumps({"amount": over, "wallet_address": "0xw"})), _cm(), MagicMock()
        )
    )
    assert result["action"] == "coin_request_failed"
    assert "ceiling" in result["error"]
    fake_tx.generate_signed_transaction.assert_not_called()
