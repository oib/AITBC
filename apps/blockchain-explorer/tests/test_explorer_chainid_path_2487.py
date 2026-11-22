"""#2487: the by-hash chain_id query value can no longer steer the DB open.

``chain_db_path_for`` used to join the raw ``chain_id`` parameter into
``<data-root>/<chain_id>/chain.db`` — a ``..`` climb or an absolute path
made the public ``GET /api/transactions/by-hash/{hash}`` open any
``chain.db`` on the host, and ``chain_scope`` then failed open on a
legacy store without the ``chain_id`` column. Now the value must pass
``validate_chain_id``, the resolved path must stay inside the data root,
explicit-chain reads fail closed on legacy stores, and the DB opens
read-only where the WAL allows it.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chain_client
import aiosqlite
from main import app

_CHAIN = chain_client.default_chain_id()
_FOREIGN = "ait-foreignchain"
_HASH = "0x" + "ab" * 32


@pytest.fixture()
def client():
    return TestClient(app)


def _legacy_db(path: Path, tx_hash: str = _HASH) -> None:
    """A pre-multi-chain store: the transaction table has no chain_id column."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE "transaction" (
            id INTEGER PRIMARY KEY, tx_hash TEXT, sender TEXT,
            recipient TEXT, payload TEXT, block_height INTEGER, created_at TEXT,
            type TEXT, status TEXT
        )"""
    )
    conn.execute(
        """INSERT INTO "transaction"
           (tx_hash, sender, recipient, payload, block_height, created_at, type, status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (tx_hash, "0xlegacy_sender", "0xrecipient", "{}", 3, "2026-01-01 00:00:00", "TRANSFER", "confirmed"),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# chain_db_path_for: traversal / absolute / symlink escapes all refuse
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "../archive/old-mainnet",
        "..",
        "a/b",
        "a\\b",
        "..hidden",
        "a..b",
        "/etc",
        "C:\\data",
        "ab",  # too short for CHAIN_ID_PATTERN
        "with space",
        "with?query",
        "line\nbreak",
    ],
)
def test_chain_db_path_for_rejects_non_bare_chain_names(tmp_path, monkeypatch, bad: str) -> None:
    monkeypatch.setattr(chain_client, "_DATA_ROOT", tmp_path)
    assert chain_client.chain_db_path_for(bad) is None


def test_chain_db_path_for_symlink_cannot_escape_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chain_client, "_DATA_ROOT", tmp_path / "data")
    outside = tmp_path / "outside"
    _legacy_db(outside / "chain.db")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "evilchain").symlink_to(outside, target_is_directory=True)
    # 'evilchain' is a valid bare name, but resolves outside the data root.
    assert (
        chain_client.chain_db_path_for("evilchain") is None
        or chain_client.chain_db_path_for("evilchain") != outside / "chain.db"
    )


def test_chain_db_path_for_still_finds_per_chain_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chain_client, "_DATA_ROOT", tmp_path)
    island_db = tmp_path / _FOREIGN / "chain.db"
    _legacy_db(island_db)
    assert chain_client.chain_db_path_for(_FOREIGN) == island_db
    assert chain_client.chain_db_path_for(None) == chain_client.chain_db_path()
    assert chain_client.chain_db_path_for("no-such-chain") == chain_client.chain_db_path()


# --------------------------------------------------------------------------
# Route level: 400 before any path is touched; strict scope on legacy stores
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../archive/old-mainnet", "/etc", "a/b", ".."])
def test_by_hash_rejects_traversal_chain_id(client, bad: str) -> None:
    resp = client.get(f"/api/transactions/by-hash/{_HASH}", params={"chain_id": bad})
    assert resp.status_code == 400
    assert "chain_id" in resp.json()["detail"].lower()


def test_by_hash_explicit_chain_on_legacy_store_fails_closed(client, tmp_path, monkeypatch) -> None:
    """Auditor repro flipped: a legacy per-chain chain.db (no chain_id
    column) must not answer an explicit ?chain_id= lookup unscoped."""
    monkeypatch.setattr(chain_client, "_DATA_ROOT", tmp_path)
    _legacy_db(tmp_path / _FOREIGN / "chain.db")

    resp = client.get(f"/api/transactions/by-hash/{_HASH}", params={"chain_id": _FOREIGN})
    assert resp.json().get("tx_hash") != _HASH


def test_by_hash_default_chain_on_legacy_store_still_reads(client, tmp_path, monkeypatch) -> None:
    """The unscoped legacy read is preserved for the *default* chain — only
    an explicit chain_id fails closed."""
    db = tmp_path / "chain.db"
    _legacy_db(db)
    for module in (
        "routers.transactions",
        "routers.blocks",
        "routers.analytics",
    ):
        mod = __import__(module, fromlist=["x"])
        monkeypatch.setattr(mod, "chain_db_path", lambda: db)
    monkeypatch.setattr(chain_client, "chain_db_path", lambda: db)

    resp = client.get(f"/api/transactions/by-hash/{_HASH}")
    assert resp.json().get("tx_hash") == _HASH


def test_chain_scope_strict_returns_match_nothing(tmp_path) -> None:
    """The strict fragment is a constant-false predicate with no params."""

    async def scope() -> tuple[str, list[str]]:
        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.execute('CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, tx_hash TEXT)')
        conn.commit()
        conn.close()
        async with aiosqlite.connect(str(db)) as aconn:
            return await chain_client.chain_scope(aconn, "transaction", _FOREIGN, strict=True)

    sql, params = asyncio.run(scope())
    assert sql == "1 = 0"
    assert params == []


# --------------------------------------------------------------------------
# Read-only open
# --------------------------------------------------------------------------


def test_chain_db_connect_prefers_read_only_uri(tmp_path, monkeypatch) -> None:
    db = tmp_path / "chain.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()

    captured: dict = {}
    real_connect = aiosqlite.connect

    def spy(database, *args, **kwargs):
        captured["database"] = str(database)
        captured["uri"] = kwargs.get("uri")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(chain_client.aiosqlite, "connect", spy)

    async def run() -> None:
        async with chain_client.chain_db_connect(db):
            pass

    asyncio.run(run())
    assert "mode=ro" in captured["database"]
    assert captured["uri"] is True
