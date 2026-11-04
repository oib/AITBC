"""#1057 pins: the other unbounded list routes clamp client-supplied
limit/offset too — accounts, mempool, tx query, cross-chain swaps — and
/market/listings is rate-limited. Mirrors test_ai_list_jobs_clamp.py."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from starlette.requests import Request

from aitbc_chain.base_models import CrossChainSwap
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Transaction
from aitbc_chain.rpc import accounts as rpc_accounts
from aitbc_chain.rpc import transactions as rpc_tx
from aitbc_chain.rpc.routers import cross_chain as rpc_cc
from sqlmodel import Session, create_engine


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    yield


def _request(ip: str = "10.9.8.7") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "headers": {},
            "client": (ip, 1234),
            "query_string": b"",
            "path": "/",
            "server": ("test", 80),
        }
    )


def _engine():
    engine = create_engine("sqlite:///:memory:")
    chain_metadata.create_all(engine)
    return engine


def _bind(module, engine):
    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    monkeypatch_scope = scope
    return monkeypatch_scope


def _seed_accounts(engine, n: int) -> None:
    with Session(engine) as s:
        for i in range(n):
            s.add(Account(chain_id="c", address=f"0x{i:040x}", balance="1", nonce=0))
        s.commit()


def _seed_txs(engine, n: int) -> None:
    with Session(engine) as s:
        for i in range(n):
            s.add(
                Transaction(
                    chain_id="c",
                    tx_hash=f"0x{i:064x}",
                    block_height=i,
                    sender="0x" + "aa" * 20,
                    recipient="0x" + "bb" * 20,
                    payload={},
                    type="TRANSFER",
                    status="confirmed",
                    nonce=i,
                )
            )
        s.commit()


def _seed_swaps(engine, n: int, chain_id: str = "c1") -> None:
    with Session(engine) as s:
        for i in range(n):
            s.add(
                CrossChainSwap(
                    swap_id=f"s{i}",
                    transfer_id=f"t{i}",
                    chain_id=chain_id,
                    from_chain=chain_id,
                    to_chain="c2",
                    from_token="AIT",
                    to_token="AIT",
                    amount="1",
                    amount_units=1,
                    user_address="0x" + "cc" * 20,
                    recipient="0x" + "dd" * 20,
                    status="pending",
                )
            )
        s.commit()


# --- /accounts (accounts.py:253) -------------------------------------------


@pytest.fixture
def accounts_env(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(rpc_accounts, "session_scope", _bind(rpc_accounts, engine))
    monkeypatch.setattr(rpc_accounts, "get_chain_id", lambda cid=None: cid or "c")
    return engine


def test_accounts_negative_limit_and_offset_clamped(accounts_env):
    _seed_accounts(accounts_env, 5)
    out = rpc_accounts.list_accounts(_request(), limit=-1, offset=-5)
    assert out["limit"] == 1 and out["offset"] == 0 and len(out["accounts"]) == 1


def test_accounts_huge_limit_capped_at_500(accounts_env):
    _seed_accounts(accounts_env, 510)
    out = rpc_accounts.list_accounts(_request(), limit=10**9)
    assert out["limit"] == 500 and len(out["accounts"]) <= 500


# --- /mempool (transactions.py:392) -----------------------------------------


def test_mempool_clamps_limit(monkeypatch):
    seen = {}

    class FakeMempool:
        def get_pending_transactions(self, chain_id=None, limit=100):
            seen["limit"] = limit
            return [{"tx_hash": "0x1"}] * min(limit, 3)

    monkeypatch.setattr("aitbc_chain.mempool.get_mempool", lambda: FakeMempool())
    rpc_tx.get_mempool(_request(), limit=-5)
    assert seen["limit"] == 1
    rpc_tx.get_mempool(_request(), limit=10**9)
    assert seen["limit"] == 500


# --- /transactions/query (transactions.py:641) ------------------------------


@pytest.fixture
def tx_env(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(rpc_tx, "session_scope", _bind(rpc_tx, engine))
    monkeypatch.setattr(rpc_tx, "get_chain_id", lambda cid=None: cid or "c")
    return engine


def test_tx_query_huge_limit_returns_at_most_500(tx_env):
    _seed_txs(tx_env, 510)
    out = rpc_tx.query_transactions(_request(), limit=10**9)
    assert len(out) <= 500


def test_tx_query_zero_limit_still_bounded(tx_env):
    _seed_txs(tx_env, 510)
    out = rpc_tx.query_transactions(_request(), limit=0)
    assert len(out) <= 500


# --- /cross-chain/swaps (routers/cross_chain.py:512) ------------------------


class _FakeBridge:
    def __init__(self, engines):
        self._engines = engines

    def _known_chains(self):
        return list(self._engines)

    def _chain_db_ready(self, chain_id):
        return True

    @contextmanager
    def _session_for(self, chain_id):
        with Session(self._engines[chain_id]) as session:
            yield session

    def get_transfer(self, transfer_id, chain_id=None):
        return None


def test_cross_chain_swaps_limit_clamped_and_pushed_down(monkeypatch):
    engine = _engine()
    _seed_swaps(engine, 510, "c1")
    monkeypatch.setattr(rpc_cc, "_get_bridge", lambda: _FakeBridge({"c1": engine}))
    out = rpc_cc.list_cross_chain_swaps(_request(), limit=10**9)
    assert out["count"] <= 500 and len(out["swaps"]) <= 500


def test_cross_chain_swaps_negative_limit_clamped_up(monkeypatch):
    engine = _engine()
    _seed_swaps(engine, 3, "c1")
    monkeypatch.setattr(rpc_cc, "_get_bridge", lambda: _FakeBridge({"c1": engine}))
    out = rpc_cc.list_cross_chain_swaps(_request(), limit=-5)
    assert out["count"] == 1


# --- /market/listings (market.py:110): rate limit pin ------------------------


def test_market_listings_rate_limited(monkeypatch):
    from fastapi import HTTPException

    from aitbc_chain.rpc import market as rpc_market

    monkeypatch.delenv("AITBC_ENABLE_RATE_LIMITING", raising=False)
    monkeypatch.setattr(rpc_market, "metrics_registry", type("M", (), {"increment": staticmethod(lambda *a, **k: None)})())
    monkeypatch.setattr(rpc_market, "_chain_db_path", lambda: Path("/nonexistent/chain.db"))
    req = _request("10.9.8.9")
    with pytest.raises(HTTPException) as exc:
        for _ in range(31):
            rpc_market.market_listings(req)
    assert exc.value.status_code == 429
