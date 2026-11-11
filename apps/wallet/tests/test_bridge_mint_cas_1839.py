"""#1839 wallet-side pin — _mint_deposit must abort on a lost verify CAS.

The pending→verified CAS already existed (#1796) but its return value was
ignored: a row another writer had already moved still proceeded to the
nonce fetch and TRANSFER submit — a double mint when the loser's nonce
differed. This pin FAILS on the unfixed code (the nonce fetch runs).
"""

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_mint_aborts_when_verify_cas_loses(tmp_path: Path, monkeypatch):
    from wallet_app.bridge import bridge_db
    from wallet_app.bridge import bridge_monitor as bm

    db_path = tmp_path / "bridge.db"
    monkeypatch.setattr(bridge_db, "DB_PATH", str(db_path))
    bridge_db.init_db()

    recipient = "0x" + "d" * 40
    deposit_id = bridge_db.insert_deposit("0xeth1", "0xfrom", Decimal("1"), Decimal("100"), recipient=recipient)
    # Another writer wins the row before the mint's verify CAS lands.
    assert bridge_db.update_deposit_status(deposit_id, "completed")

    calls: list[str] = []

    class SpyClient:
        @staticmethod
        async def get(url, **kwargs):
            calls.append("get")
            return _Resp({"nonce": 0})

        @staticmethod
        async def post(url, **kwargs):
            calls.append("post")
            return _Resp({"transaction_hash": "0xdead"})

    monkeypatch.setattr(bm, "SharedHttpClient", SpyClient)
    monkeypatch.setattr(bm, "GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setattr(bm, "GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
    monkeypatch.setattr(bm, "BLOCKCHAIN_RPC_URL", "http://test-rpc")

    await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

    # Aborted before the nonce fetch — no chain calls at all.
    assert calls == []
    row = bridge_db.get_deposit_by_id(deposit_id)
    assert row["status"] == "completed"
