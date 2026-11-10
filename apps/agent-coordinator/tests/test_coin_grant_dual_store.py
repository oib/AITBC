"""#1604 / #1542 regression pins — the WS grant path and `/register` share ONE
``coin_requests`` table in ``agent_coin_requests.db``.

What is pinned here:

- Schema convergence (#1604): a database where the raw websocket schema was
  created first (the historical 13-column table, missing the ORM's
  ``rejection_reason``/``signed_transaction``) is upgraded in place, so the
  SQLAlchemy ``CoinRequest`` writer keeps working.
- Cross-path prior-grant visibility (#1542): a WS auto-grant is an APPROVED
  row in the same table, so ``/register``'s ``has_prior_grant`` sees it and
  parks the second grant; and a ``/register`` approval is visible to the WS
  handler's prior-grant probe.
- The atomic first-grant gate: ``_record_claiming_coin_request(first_grant=True)``
  runs its prior-grant probe and INSERT inside one ``BEGIN IMMEDIATE``
  transaction, so concurrent claims for the same wallet across workers produce
  exactly one winner.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock


from agent_app.config import settings
from agent_app.websocket import agent_stream
from agent_app.services import coin_request_policy
from aitbc.db import agent_db
from aitbc.models import CoinRequest, CoinRequestStatus

from .conftest import API_KEY, PAYOUT, bare_client  # noqa: F401

WALLET = "0x" + "ab" * 20
OTHER_WALLET = "0x" + "cd" * 20


def _ws_env(monkeypatch):
    """Wallet binding off + a signer that cannot emit a transaction."""
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
    fake_tx = MagicMock()
    fake_tx.generate_signed_transaction = MagicMock(return_value={"signed": True})
    monkeypatch.setattr(agent_stream, "TransactionService", lambda: fake_tx)
    monkeypatch.setattr(
        agent_stream, "_submit_transaction", lambda tx: {"success": True, "transaction_hash": "0x" + "ee" * 32}
    )
    return fake_tx


def _cm():
    cm = agent_stream.ConnectionManager()
    cm.send_personal_message = AsyncMock(return_value=True)
    return cm


def _ws_request(sender: str, wallet: str) -> dict:
    return {
        "sender_id": sender,
        "content": json.dumps({"amount": 1, "wallet_address": wallet}),
    }


def _register(client, sender: str, wallet: str, request_id: str = "req-dual-1"):
    return client.post(
        "/api/v1/agent/coin-requests/register",
        json={"request_id": request_id, "sender": sender, "amount": PAYOUT, "wallet_address": wallet},
        headers={"x-api-key": API_KEY},
    )


# --- Cross-path prior-grant visibility ----------------------------------------------------


def test_ws_grant_then_register_is_denied(bare_client, monkeypatch) -> None:  # noqa: F811
    """The #1542 bypass: a WS-granted wallet must not collect a second grant
    through /register. Both rows live in the same table, so the policy's
    prior-grant probe sees the WS claim."""
    fake_tx = _ws_env(monkeypatch)

    result = asyncio.run(agent_stream.request_coins_handler(_ws_request("ws-agent", WALLET), _cm(), MagicMock()))

    assert result["action"] == "coins_transferred"
    fake_tx.generate_signed_transaction.assert_called_once()

    response = _register(bare_client, "register-agent", WALLET)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert "already been granted" in response.json()["reason"]


def test_register_grant_then_ws_request_parks(bare_client, monkeypatch) -> None:  # noqa: F811
    """The mirror direction: an APPROVED-but-unexecuted /register row counts as
    a prior grant for the WS handler, which signs on the spot — it must park
    for the (manual) approval strategy instead of paying again."""
    monkeypatch.delenv("COIN_APPROVAL_MODE", raising=False)  # default: manual
    fake_tx = _ws_env(monkeypatch)

    response = _register(bare_client, "register-agent", WALLET)
    assert response.json()["status"] == "approved"

    result = asyncio.run(agent_stream.request_coins_handler(_ws_request("ws-agent", WALLET), _cm(), MagicMock()))

    assert result["action"] == "coin_request_received"
    assert result["status"] == "pending_approval"
    fake_tx.generate_signed_transaction.assert_not_called()


# --- The atomic first-grant gate ------------------------------------------------------------


def _count_approved(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM coin_requests WHERE status = 'APPROVED'").fetchone()[0]
    conn.close()
    return n


def test_sequential_first_grant_claims_one_wins(monkeypatch, tmp_path) -> None:
    db = tmp_path / "coins.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db))

    first, dup1 = agent_stream._record_claiming_coin_request("agent-1", 5, WALLET, first_grant=True)
    assert first is not None and not dup1

    second, dup2 = agent_stream._record_claiming_coin_request("agent-2", 5, WALLET, first_grant=True)
    assert second is None and dup2
    # Same sender is caught by the sender clause even with a fresh wallet.
    third, dup3 = agent_stream._record_claiming_coin_request("agent-1", 5, OTHER_WALLET, first_grant=True)
    assert third is None and dup3
    assert _count_approved(str(db)) == 1


def test_failed_first_grant_claim_does_not_block_retry(monkeypatch, tmp_path) -> None:
    """A claim marked FAILED by _finish_claimed_coin_request releases the gate —
    the agent may retry, matching the pre-gate semantics."""
    db = tmp_path / "coins.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db))

    rid, _ = agent_stream._record_claiming_coin_request("agent-1", 5, WALLET, first_grant=True)
    assert rid is not None
    agent_stream._finish_claimed_coin_request(rid, "", failed=True)

    retry, dup = agent_stream._record_claiming_coin_request("agent-1", 5, WALLET, first_grant=True)
    assert retry is not None and not dup


def test_concurrent_first_grant_claims_exactly_one_wins(monkeypatch, tmp_path) -> None:
    """The cross-worker race from #1542: N simultaneous first-grant claims for
    the same wallet must produce exactly one committed claim row."""
    db = tmp_path / "coins.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db))

    n = 8
    # Pre-open the ledger once so the workers don't race the fresh-file
    # schema creation inside _agent_db_conn — that first-open
    # "database is locked" window is a separate defect tracked in #1658.
    # The invariant pinned here is the claim path's BEGIN IMMEDIATE
    # check-and-insert, which still runs fully concurrently below.
    warm = agent_stream._agent_db_conn()
    assert warm is not None
    warm.close()
    barrier = threading.Barrier(n)
    results: list[tuple[str | None, bool]] = []
    results_lock = threading.Lock()

    def claim(i: int) -> None:
        barrier.wait(timeout=10)
        out = agent_stream._record_claiming_coin_request(f"agent-{i}", 5, WALLET, first_grant=True)
        with results_lock:
            results.append(out)

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == n
    winners = [r for r in results if r[0] is not None and not r[1]]
    losers = [r for r in results if r[0] is None and r[1]]
    errors = [r for r in results if r == (None, False)]
    assert errors == []
    assert len(winners) == 1
    assert len(losers) == n - 1
    assert _count_approved(str(db)) == 1


# --- Schema convergence (#1604) --------------------------------------------------------------


def test_narrow_preexisting_table_is_upgraded_for_the_orm(monkeypatch, tmp_path) -> None:
    """A database created by the historical raw schema (no rejection_reason /
    signed_transaction) must not break ORM CoinRequest writes — the #1604
    'narrow schema breaks the ORM' defect."""
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE coin_requests (id TEXT, sender TEXT, recipient TEXT, amount INTEGER, "
        "wallet_address TEXT, status TEXT, approval_mode TEXT, approved_by TEXT, approved_at TEXT, "
        "created_at TEXT, expires_at TEXT, transaction_hash TEXT, audit_log TEXT)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    conn = agent_stream._agent_db_conn()
    assert conn is not None
    conn.close()

    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    try:
        agent_db.init_db()
        now = datetime.now(UTC).replace(tzinfo=None)
        with agent_db.get_db_session() as session:
            session.add(
                CoinRequest(
                    id="req-orm-after-raw",
                    sender="agent-orm",
                    recipient="hub-coordinator",
                    amount=PAYOUT,
                    wallet_address=WALLET,
                    status=CoinRequestStatus.PENDING,
                    approval_mode="manual",
                    created_at=now,
                    expires_at=now + timedelta(days=1),
                )
            )
        with agent_db.get_db_session() as session:
            row = session.query(CoinRequest).filter(CoinRequest.id == "req-orm-after-raw").first()
            assert row is not None
            assert row.status is CoinRequestStatus.PENDING
    finally:
        agent_db._engine = None
        agent_db._SessionLocal = None


def test_fresh_node_raw_schema_first_still_serves_the_orm(monkeypatch, tmp_path) -> None:
    """The deployment order that used to corrupt the store: the websocket path
    opens the DB before lifespan init_db(). The raw schema now carries every
    ORM column, so create_all afterwards is a no-op and ORM writes work."""
    db = tmp_path / "fresh.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db))

    conn = agent_stream._agent_db_conn()
    assert conn is not None
    conn.close()

    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    try:
        agent_db.init_db()
        now = datetime.now(UTC).replace(tzinfo=None)
        with agent_db.get_db_session() as session:
            session.add(
                CoinRequest(
                    id="req-after-raw-create",
                    sender="agent-orm",
                    recipient="hub-coordinator",
                    amount=PAYOUT,
                    wallet_address=OTHER_WALLET,
                    status=CoinRequestStatus.APPROVED,
                    approval_mode="automatic",
                    created_at=now,
                    expires_at=now + timedelta(days=1),
                )
            )
        with agent_db.get_db_session() as session:
            assert coin_request_policy.has_prior_grant(session, "agent-orm", OTHER_WALLET)
    finally:
        agent_db._engine = None
        agent_db._SessionLocal = None
