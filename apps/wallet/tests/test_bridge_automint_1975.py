"""#1975 wallet-side pin — ambiguous auto-mint submit must never re-pend.

Once the genesis TRANSFER POST is attempted, ReadTimeout/5xx/"no tx hash"
can all fire AFTER the chain accepted the transaction. Reverting the row
to 'pending' lets get_pending_deposits re-pick it and mint a second time.
The row must park at 'failed' for operator reconcile; only failures where
nothing was sent (pre-connect) may re-pend.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import httpx
import pytest


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _NonceClient:
    @staticmethod
    async def get(url, **kwargs):
        return _Resp({"nonce": 0})


class _PostClient:
    """Fake httpx.AsyncClient: __aenter__ returns self, post() is scripted."""

    outcome: object = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        outcome = type(self).outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _arm(monkeypatch, tmp_path: Path, post_outcome):
    from wallet_app.bridge import bridge_db
    from wallet_app.bridge import bridge_monitor as bm

    db_path = tmp_path / "bridge.db"
    monkeypatch.setattr(bridge_db, "DB_PATH", str(db_path))
    bridge_db.init_db()

    recipient = "0x" + "d" * 40
    deposit_id = bridge_db.insert_deposit("0xeth1", "0xfrom", Decimal("1"), Decimal("100"), recipient=recipient)

    monkeypatch.setattr(bm, "SharedHttpClient", _NonceClient)
    monkeypatch.setattr(bm, "GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setattr(bm, "GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
    monkeypatch.setattr(bm, "BLOCKCHAIN_RPC_URL", "http://test-rpc")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    class Scripted(_PostClient):
        outcome = post_outcome

    monkeypatch.setattr(bm.httpx, "AsyncClient", Scripted)
    return bm, bridge_db, deposit_id, recipient


@pytest.mark.asyncio
async def test_read_timeout_parks_failed_not_pending(tmp_path: Path, monkeypatch):
    bm, bridge_db, deposit_id, recipient = _arm(monkeypatch, tmp_path, httpx.ReadTimeout("slow"))

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    row = bridge_db.get_deposit_by_id(deposit_id)
    assert row["status"] == "failed"
    assert deposit_id not in {d["id"] for d in bridge_db.get_pending_deposits()}


@pytest.mark.asyncio
async def test_http_5xx_parks_failed_not_pending(tmp_path: Path, monkeypatch):
    bm, bridge_db, deposit_id, recipient = _arm(
        monkeypatch,
        tmp_path,
        httpx.HTTPStatusError(
            "server error",
            request=httpx.Request("POST", "http://test-rpc/rpc/transaction"),
            response=httpx.Response(503),
        ),
    )

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    row = bridge_db.get_deposit_by_id(deposit_id)
    assert row["status"] == "failed"


@pytest.mark.asyncio
async def test_no_tx_hash_parks_failed_not_pending(tmp_path: Path, monkeypatch):
    bm, bridge_db, deposit_id, recipient = _arm(monkeypatch, tmp_path, _Resp({}))

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    row = bridge_db.get_deposit_by_id(deposit_id)
    assert row["status"] == "failed"


@pytest.mark.asyncio
async def test_connect_error_reverts_pending(tmp_path: Path, monkeypatch):
    """Pre-connect failure sent nothing — safe to re-pend for retry."""
    bm, bridge_db, deposit_id, recipient = _arm(monkeypatch, tmp_path, httpx.ConnectError("refused"))

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    row = bridge_db.get_deposit_by_id(deposit_id)
    assert row["status"] == "pending"
    assert deposit_id in {d["id"] for d in bridge_db.get_pending_deposits()}


@pytest.mark.asyncio
async def test_pre_submit_error_reverts_pending(tmp_path: Path, monkeypatch):
    """Signing failure happens before any POST — safe to re-pend."""
    bm, bridge_db, deposit_id, recipient = _arm(monkeypatch, tmp_path, _Resp({"transaction_hash": "0x1"}))
    monkeypatch.setattr(bm, "GENESIS_WALLET_PRIVATE_KEY", "0xnot-hex")

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    row = bridge_db.get_deposit_by_id(deposit_id)
    assert row["status"] == "pending"
