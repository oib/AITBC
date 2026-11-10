"""#1623 pins: /transactions/market/match stops hydrating every confirmed
GPU_MARKET row — the SQL candidate predicate keeps only offers, withdrawals
and `replaces` carriers, and the output is capped with an honest
``truncated`` flag."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from eth_keys import keys
from sqlmodel import Session, create_engine

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Transaction
from aitbc_chain.rpc import transactions as tx_mod

SELLER = keys.PrivateKey(b"\x11" * 32).public_key.to_checksum_address()
OTHER = keys.PrivateKey(b"\x22" * 32).public_key.to_checksum_address()
CHAIN = "test"


def _offer(**extra: Any) -> dict[str, Any]:
    return {"action": "software_offer", "service_type": "whisper", "model": "base", "price": 1, **extra}


def _cancel(*ids: str) -> dict[str, Any]:
    return {"action": "cancel", "order_id": ids[0], "order_ids": list(ids), "status": "cancelled"}


@pytest.fixture
def chain_db(tmp_path):
    path = tmp_path / "chain.db"
    engine = create_engine(f"sqlite:///{path}")
    chain_metadata.create_all(engine)
    yield path, engine
    engine.dispose()


def _seed(engine, rows: list[tuple[int, str, dict[str, Any]]], tx_type: str = "GPU_MARKET") -> None:
    with Session(engine) as session:
        for tx_id, sender, payload in rows:
            session.add(
                Transaction(
                    id=tx_id,
                    chain_id=CHAIN,
                    tx_hash=f"{tx_id:064x}",
                    sender=sender,
                    recipient="0x" + "0" * 40,
                    payload=payload,
                    type=tx_type,
                    status="confirmed",
                    timestamp="2026-10-02T12:00:00",
                )
            )
        session.commit()


def _match(engine, chain_db, **kwargs):
    path, _ = chain_db

    @contextmanager
    def session_scope(*_a, **_kw):
        with Session(engine) as session:
            yield session

    with patch.object(tx_mod, "session_scope", session_scope), patch.object(tx_mod, "get_chain_id", lambda _c=None: CHAIN):
        return tx_mod.match_market(MagicMock(), chain_id=CHAIN, **kwargs)


@pytest.mark.asyncio
async def test_settlement_rows_are_not_match_candidates(chain_db):
    """software_job settlements dominated the old scan; they are not offers
    and carry no withdrawal, so the predicate must exclude them."""
    path, engine = chain_db
    _seed(
        engine,
        [
            (1, SELLER, _offer()),
            (2, SELLER, {"action": "software_job", "job_id": "j1", "status": "completed"}),
            (3, OTHER, {"action": "rate", "rating": 5}),
            (4, OTHER, {"status": "delivered"}),
        ],
    )
    out = _match(engine, chain_db)
    assert [m["listing_id"] for m in out["matches"]] == ["tx_1"]
    assert out["total"] == 1 and out["truncated"] is False


@pytest.mark.asyncio
async def test_withdrawal_rows_still_reach_the_matcher(chain_db):
    """Cancels and `replaces` carriers must survive the predicate — they are
    what withdraws_listing_ids needs."""
    path, engine = chain_db
    _seed(
        engine,
        [
            (1, SELLER, _offer()),
            (2, SELLER, _offer()),
            (3, SELLER, _cancel("tx_1")),
            (4, OTHER, _offer(replaces=["tx_2"])),  # foreign replaces: ignored
        ],
    )
    out = _match(engine, chain_db)
    assert {m["listing_id"] for m in out["matches"]} == {"tx_2", "tx_4"}


@pytest.mark.asyncio
async def test_corrupt_and_non_object_payloads_do_not_break_the_scan(chain_db):
    """json_valid gates the JSON calls — a malformed payload row is skipped
    in SQL instead of erroring the whole query (or hydrating into a crash)."""
    path, engine = chain_db
    _seed(engine, [(1, SELLER, _offer())])
    conn = sqlite3.connect(path)
    conn.execute(
        'INSERT INTO "transaction" (id, chain_id, tx_hash, sender, recipient, payload, type, status, timestamp, nonce, value, fee, created_at) '
        "VALUES (2, ?, ?, ?, ?, 'not json', 'GPU_MARKET', 'confirmed', 't', 0, 0, 0, '2026-10-02')",
        (CHAIN, f"{2:064x}", SELLER, "0x" + "0" * 40),
    )
    conn.execute(
        'INSERT INTO "transaction" (id, chain_id, tx_hash, sender, recipient, payload, type, status, timestamp, nonce, value, fee, created_at) '
        "VALUES (3, ?, ?, ?, ?, '[1,2]', 'GPU_MARKET', 'confirmed', 't', 0, 0, 0, '2026-10-02')",
        (CHAIN, f"{3:064x}", SELLER, "0x" + "0" * 40),
    )
    conn.commit()
    conn.close()
    out = _match(engine, chain_db)
    assert [m["listing_id"] for m in out["matches"]] == ["tx_1"]


@pytest.mark.asyncio
async def test_limit_truncates_newest_first_with_flag(chain_db):
    path, engine = chain_db
    _seed(engine, [(i, SELLER, _offer()) for i in range(1, 6)])
    out = _match(engine, chain_db, limit=2)
    assert out["total"] == 5 and out["truncated"] is True
    # Newest first: the cap drops the oldest listings.
    assert [m["listing_id"] for m in out["matches"]] == ["tx_5", "tx_4"]
    out = _match(engine, chain_db, limit=0)
    assert out["truncated"] is True and len(out["matches"]) == 1  # 0 clamps to 1, never unbounded
