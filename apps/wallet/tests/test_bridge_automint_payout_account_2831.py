"""#2831 wallet-side pin — auto-mint must refuse a shared nonce space.

When GENESIS_WALLET_ADDRESS IS the bridge-monitor payout account, this
path and the monitor's payout lane draw nonces from the same account
with no cross-service serialization — two signers can collide in the
mempool and burn each other's envelopes. The monitor publishes its
payout account in bridge_monitor_state; the wallet refuses the auto-mint
and leaves the row 'pending' until the operator splits the accounts.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

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
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        type(self).calls.append(url)
        outcome = type(self).outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


GENESIS = "0x" + "b" * 40


def _arm(monkeypatch, tmp_path: Path, payout_account: str | None):
    from wallet_app.bridge import bridge_db
    from wallet_app.bridge import bridge_monitor as bm

    db_path = tmp_path / "bridge.db"
    monkeypatch.setattr(bridge_db, "DB_PATH", str(db_path))
    bridge_db.init_db()

    if payout_account is not None:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT OR REPLACE INTO bridge_monitor_state (key, value) VALUES ('payout_account', ?)",
                (payout_account,),
            )
            conn.commit()
        finally:
            conn.close()

    recipient = "0x" + "d" * 40
    deposit_id = bridge_db.insert_deposit("0xeth1", "0xfrom", Decimal("1"), Decimal("100"), recipient=recipient)

    monkeypatch.setattr(bm, "SharedHttpClient", _NonceClient)
    monkeypatch.setattr(bm, "GENESIS_WALLET_ADDRESS", GENESIS)
    monkeypatch.setattr(bm, "GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
    monkeypatch.setattr(bm, "BLOCKCHAIN_RPC_URL", "http://test-rpc")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    class Scripted(_PostClient):
        outcome = _Resp({"transaction_hash": "0xminted"})
        calls = []

    monkeypatch.setattr(bm.httpx, "AsyncClient", Scripted)
    return bm, bridge_db, deposit_id, recipient, Scripted


@pytest.mark.asyncio
async def test_shared_payout_account_refuses_mint(tmp_path: Path, monkeypatch):
    """payout_account == GENESIS_WALLET_ADDRESS → no TRANSFER is ever
    submitted; the row stays 'pending' for the operator to resolve."""
    bm, bridge_db, deposit_id, recipient, scripted = _arm(monkeypatch, tmp_path, GENESIS)

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    assert scripted.calls == []
    row = bridge_db.get_deposit_by_id(deposit_id)
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_shared_payout_account_case_insensitive(tmp_path: Path, monkeypatch):
    """A case-variant stored payout account still matches — addresses are
    compared lowercase on both sides."""
    bm, bridge_db, deposit_id, recipient, scripted = _arm(monkeypatch, tmp_path, GENESIS.upper().replace("0X", "0x"))

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    assert scripted.calls == []
    assert bridge_db.get_deposit_by_id(deposit_id)["status"] == "pending"


@pytest.mark.asyncio
async def test_distinct_payout_account_mints(tmp_path: Path, monkeypatch):
    """A different payout account means separate nonce spaces — the
    auto-mint proceeds normally."""
    bm, bridge_db, deposit_id, recipient, scripted = _arm(monkeypatch, tmp_path, "0x" + "e" * 40)

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    assert scripted.calls != []
    assert bridge_db.get_deposit_by_id(deposit_id)["status"] == "completed"


@pytest.mark.asyncio
async def test_absent_payout_account_mints(tmp_path: Path, monkeypatch):
    """Monitor never published (or predates the publish) — fail-open: the
    mint proceeds exactly as before."""
    bm, bridge_db, deposit_id, recipient, scripted = _arm(monkeypatch, tmp_path, None)

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    assert scripted.calls != []
    assert bridge_db.get_deposit_by_id(deposit_id)["status"] == "completed"
