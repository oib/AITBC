"""#1717 pins: keyset (cursor) pagination on the RPC list endpoints.

OFFSET pages skip/dup rows when the table mutates between fetches; the
``cursor``/``next_cursor`` pair pages by the ORDER BY key instead. Covers
/rpc/accounts, /rpc/ai/jobs (with its Python-side status trim) and
/rpc/bridge/transfers (nullable lock_time key).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from aitbc_chain.base_models import CrossChainTransfer, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc import accounts as rpc_accounts
from aitbc_chain.rpc import ai_services
from aitbc_chain.rpc.bridge import list_bridge_transfers
from sqlmodel import Session, create_engine


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    yield


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "headers": {},
            "client": ("192.0.2.7", 1234),
            "query_string": b"",
            "path": "/",
            "server": ("test", 80),
        }
    )


def _engine():
    engine = create_engine("sqlite:///:memory:")
    chain_metadata.create_all(engine)
    return engine


def _bind_scope(engine):
    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    return scope


# --- /rpc/accounts ----------------------------------------------------------


@pytest.fixture
def accounts_env(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(rpc_accounts, "session_scope", _bind_scope(engine))
    monkeypatch.setattr(rpc_accounts, "get_chain_id", lambda cid=None: cid or "c")
    return engine


def _seed_accounts(engine, addrs):
    with Session(engine) as s:
        for a in addrs:
            s.add(Account(chain_id="c", address=a, balance=1, nonce=0))
        s.commit()


def _account_addrs(out):
    return [a["address"] for a in out["accounts"]]


def test_accounts_cursor_covers_all_no_dups(accounts_env):
    addrs = [f"0x{i:040x}" for i in range(7)]
    _seed_accounts(accounts_env, addrs)
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        out = rpc_accounts.list_accounts(_request(), limit=3, cursor=cursor)
        seen.extend(_account_addrs(out))
        cursor = out["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(addrs)


def test_accounts_cursor_survives_mid_pagination_insert(accounts_env):
    addrs = [f"0x{i:040x}" for i in range(6)]
    _seed_accounts(accounts_env, addrs)
    page1 = rpc_accounts.list_accounts(_request(), limit=3)
    assert _account_addrs(page1) == addrs[:3]
    cursor = page1["next_cursor"]
    assert cursor == addrs[2]

    # A new account sorts *inside* the already-seen window — OFFSET would
    # shift every later page; keyset must not.
    _seed_accounts(accounts_env, ["0x0" + "f" * 39])
    page2 = rpc_accounts.list_accounts(_request(), limit=3, cursor=cursor)
    assert _account_addrs(page2) == addrs[3:]


def test_accounts_bad_cursor_400(accounts_env):
    _seed_accounts(accounts_env, ["0x" + "0" * 40])
    with pytest.raises(HTTPException) as exc:
        rpc_accounts.list_accounts(_request(), cursor="bad cursor|")
    assert exc.value.status_code == 400


def test_accounts_offset_still_composes(accounts_env):
    addrs = [f"0x{i:040x}" for i in range(6)]
    _seed_accounts(accounts_env, addrs)
    out = rpc_accounts.list_accounts(_request(), limit=2, offset=2)
    assert _account_addrs(out) == addrs[2:4]


# --- /rpc/ai/jobs -----------------------------------------------------------


@pytest.fixture
def ai_env(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(ai_services, "session_scope", _bind_scope(engine))
    return engine


def _seed_ai_jobs(engine, n: int, statuses: list[str] | None = None):
    statuses = statuses or ["pending"] * n
    with Session(engine) as s:
        for i, st in enumerate(statuses):
            s.add(
                Transaction(
                    chain_id="c",
                    tx_hash=f"0x{i:064x}",
                    block_height=i,
                    sender="0x" + "aa" * 20,
                    recipient="ai_service",
                    payload={"job_id": f"j{i}", "job_type": "text", "prompt": "x", "payment": 1.0},
                    type="AI_JOB",
                    status=st,
                    created_at=datetime(2026, 1, 1, 0, 0, i),
                )
            )
        s.commit()


def _job_ids(out):
    return [j["job_id"] for j in out["jobs"]]


def test_ai_jobs_cursor_covers_all_no_dups(ai_env):
    _seed_ai_jobs(ai_env, 7)
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        out = ai_services.ai_list_jobs(limit=3, cursor=cursor)
        seen.extend(_job_ids(out))
        cursor = out["next_cursor"]
        if cursor is None:
            break
    # created_at DESC, id DESC: j6 (latest) first … j0 last
    assert seen == [f"j{i}" for i in range(6, -1, -1)]


def test_ai_jobs_cursor_with_status_filter(ai_env):
    """The status trim runs post-SQL: the cursor must page *matching* jobs
    without skipping or wedging on non-matching candidates."""
    statuses = ["completed" if i % 2 == 0 else "pending" for i in range(8)]
    _seed_ai_jobs(ai_env, 8, statuses)
    seen: list[str] = []
    cursor = None
    for _ in range(20):
        out = ai_services.ai_list_jobs(limit=2, status="completed", cursor=cursor)
        seen.extend(_job_ids(out))
        assert all(j["status"] == "completed" for j in out["jobs"])
        cursor = out["next_cursor"]
        if cursor is None:
            break
    # completed jobs are even i: j6, j4, j2, j0 in DESC created_at order
    assert seen == ["j6", "j4", "j2", "j0"]


def test_ai_jobs_bad_cursor_400(ai_env):
    _seed_ai_jobs(ai_env, 2)
    with pytest.raises(HTTPException) as exc:
        ai_services.ai_list_jobs(cursor="garbage")
    assert exc.value.status_code == 400


# --- /rpc/bridge/transfers --------------------------------------------------


@pytest.fixture
def bridge_env(session, monkeypatch):
    @contextmanager
    def _fake_scope(chain_id: str = ""):
        yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", _fake_scope)
    return session


def _transfer(tid: str, lock_time: datetime | None) -> CrossChainTransfer:
    return CrossChainTransfer(
        transfer_id=tid,
        source_chain="ait-testnet",
        target_chain="sepolia",
        sender="0xSENDER",
        recipient="0xRECIPIENT",
        amount=36_000_000,
        asset="native",
        status="locked",
        lock_time=lock_time,
    )


def test_bridge_transfers_cursor_covers_all_incl_null_tail(bridge_env):
    rows = [
        ("0xt1", datetime(2026, 9, 1, 1, tzinfo=UTC)),
        ("0xt2", datetime(2026, 9, 3, 1, tzinfo=UTC)),
        ("0xt3", None),  # NULL lock_time sorts last in DESC
        ("0xt4", datetime(2026, 9, 2, 1, tzinfo=UTC)),
        ("0xt5", None),
    ]
    for tid, lt in rows:
        bridge_env.add(_transfer(tid, lt))
    bridge_env.commit()

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        out = list_bridge_transfers(None, "test-chain", limit=2, cursor=cursor)
        seen.extend(t["transfer_id"] for t in out["transfers"])
        cursor = out["next_cursor"]
        if cursor is None:
            break
    # DESC lock_time: t2 > t4 > t1, then NULL group by transfer_id DESC
    assert seen == ["0xt2", "0xt4", "0xt1", "0xt5", "0xt3"]


def test_bridge_transfers_cursor_survives_mid_pagination_insert(bridge_env):
    for i in range(4):
        bridge_env.add(_transfer(f"0xt{i}", datetime(2026, 9, i + 1, tzinfo=UTC)))
    bridge_env.commit()

    page1 = list_bridge_transfers(None, "test-chain", limit=2)
    assert [t["transfer_id"] for t in page1["transfers"]] == ["0xt3", "0xt2"]
    cursor = page1["next_cursor"]
    assert cursor is not None

    # Newer transfer lands between pages — keyset resumes below the cursor.
    bridge_env.add(_transfer("0xtnew", datetime(2026, 9, 9, tzinfo=UTC)))
    bridge_env.commit()
    page2 = list_bridge_transfers(None, "test-chain", limit=2, cursor=cursor)
    assert [t["transfer_id"] for t in page2["transfers"]] == ["0xt1", "0xt0"]


def test_bridge_transfers_bad_cursor_400(bridge_env):
    bridge_env.add(_transfer("0xt1", datetime(2026, 9, 1, tzinfo=UTC)))
    bridge_env.commit()
    with pytest.raises(HTTPException) as exc:
        list_bridge_transfers(None, "test-chain", cursor="not-a-cursor")
    assert exc.value.status_code == 400
