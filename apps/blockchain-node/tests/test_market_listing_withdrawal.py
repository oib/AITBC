"""M-1: only a seller can withdraw their own listing.

A GPU_MARKET cancel (``order_id``/``order_ids``) or an offer's ``replaces``
list hides the listings it names. Admission verifies the signature against
``from`` and nothing else, and consensus has no GPU_MARKET branch, so any
funded account could confirm a cancel naming another seller's listing and the
readers hid it from everyone. Both readers (``/rpc/market/listings`` and
``/rpc/transactions/market/match``) now honour a withdrawal only when its
sender is the seller of the listing it names.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from eth_keys import keys
from sqlmodel import Session, create_engine

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Transaction
from aitbc_chain.rpc import market as market_mod
from aitbc_chain.rpc import transactions as tx_mod
from aitbc_chain.rpc.utils import withdrawn_listing_ids

SELLER = keys.PrivateKey(b"\x11" * 32).public_key.to_checksum_address()
OTHER = keys.PrivateKey(b"\x22" * 32).public_key.to_checksum_address()
CHAIN = "test"


def _offer(**extra: Any) -> dict[str, Any]:
    return {"action": "software_offer", "service_type": "whisper", "model": "base", "price": 1, **extra}


def _cancel(*ids: str) -> dict[str, Any]:
    return {"action": "cancel", "order_id": ids[0], "order_ids": list(ids), "status": "cancelled"}


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------


def test_own_cancel_withdraws_listing():
    rows = [(1, SELLER, _offer()), (2, SELLER, _cancel("tx_1"))]
    assert withdrawn_listing_ids(rows) == {"tx_1", "tx_2"}


def test_foreign_cancel_is_ignored():
    rows = [(1, SELLER, _offer()), (2, OTHER, _cancel("tx_1"))]
    # The cancel row withdraws itself (it is never a listing); the listing it names stays.
    assert withdrawn_listing_ids(rows) == {"tx_2"}


def test_own_replaces_withdraws_old_listing():
    rows = [(1, SELLER, _offer()), (2, SELLER, _offer(replaces=["tx_1"]))]
    assert withdrawn_listing_ids(rows) == {"tx_1"}


def test_foreign_replaces_is_ignored():
    rows = [(1, SELLER, _offer()), (2, OTHER, _offer(replaces=["tx_1"]))]
    assert withdrawn_listing_ids(rows) == set()


def test_replaces_accepts_a_bare_id():
    rows = [(1, SELLER, _offer()), (2, SELLER, _offer(replaces="tx_1"))]
    assert withdrawn_listing_ids(rows) == {"tx_1"}


def test_cancel_naming_several_ids_withdraws_only_the_senders():
    rows = [
        (1, SELLER, _offer()),
        (2, OTHER, _offer()),
        (3, SELLER, _cancel("tx_1", "tx_2")),
    ]
    assert withdrawn_listing_ids(rows) == {"tx_1", "tx_3"}


def test_same_account_in_another_spelling_still_counts_as_the_seller():
    """`sender` is stored verbatim; the same account may be written lower- or checksum-case."""
    assert SELLER != SELLER.lower()
    rows = [(1, SELLER, _offer()), (2, SELLER.lower(), _cancel("tx_1"))]
    assert "tx_1" in withdrawn_listing_ids(rows)


def test_cancel_of_an_unknown_id_is_ignored():
    rows = [(1, SELLER, _offer()), (2, SELLER, _cancel("tx_99", "listing_001", "1"))]
    assert withdrawn_listing_ids(rows) == {"tx_2"}


def test_a_senderless_row_withdraws_nothing():
    rows = [(1, "", _offer()), (2, "", _cancel("tx_1")), (3, None, _cancel("tx_1"))]
    assert "tx_1" not in withdrawn_listing_ids(rows)


def test_an_offer_marked_cancelled_withdraws_itself():
    rows = [(1, SELLER, _offer(status="cancelled"))]
    assert withdrawn_listing_ids(rows) == {"tx_1"}


# ---------------------------------------------------------------------------
# Both readers, against a real chain.db
# ---------------------------------------------------------------------------


@pytest.fixture
def chain_db(tmp_path):
    path = tmp_path / "chain.db"
    engine = create_engine(f"sqlite:///{path}")
    chain_metadata.create_all(engine)
    yield path, engine
    engine.dispose()


def _seed(engine, rows: list[tuple[int, str, dict[str, Any]]]) -> None:
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
                    type="GPU_MARKET",
                    status="confirmed",
                    timestamp="2026-10-02T12:00:00",
                )
            )
        session.commit()


async def _listing_ids(chain_db, rows) -> dict[str, set[str]]:
    """The listing ids each reader returns for ``rows``."""
    path, engine = chain_db
    _seed(engine, rows)

    @contextmanager
    def session_scope(*_a, **_kw):
        with Session(engine) as session:
            yield session

    with patch.object(market_mod, "_chain_db_path", lambda: path):
        listings = await market_mod.market_listings()
    with patch.object(tx_mod, "session_scope", session_scope), patch.object(tx_mod, "get_chain_id", lambda _c=None: CHAIN):
        matched = await tx_mod.match_market(MagicMock(), chain_id=CHAIN)
    return {
        "listings": {listing["listing_id"] for listing in listings["listings"] if listing["listing_id"].startswith("tx_")},
        "match": {m["listing_id"] for m in matched["matches"]},
    }


@pytest.mark.asyncio
async def test_foreign_cancel_does_not_hide_a_listing(chain_db):
    seen = await _listing_ids(chain_db, [(1, SELLER, _offer()), (2, OTHER, _cancel("tx_1"))])
    assert seen == {"listings": {"tx_1"}, "match": {"tx_1"}}


@pytest.mark.asyncio
async def test_own_cancel_hides_a_listing(chain_db):
    seen = await _listing_ids(chain_db, [(1, SELLER, _offer()), (2, SELLER, _offer()), (3, SELLER, _cancel("tx_1"))])
    assert seen == {"listings": {"tx_2"}, "match": {"tx_2"}}


@pytest.mark.asyncio
async def test_foreign_replaces_does_not_hide_a_listing(chain_db):
    seen = await _listing_ids(chain_db, [(1, SELLER, _offer()), (2, OTHER, _offer(replaces=["tx_1"]))])
    assert seen == {"listings": {"tx_1", "tx_2"}, "match": {"tx_1", "tx_2"}}


@pytest.mark.asyncio
async def test_own_replaces_hides_the_old_listing(chain_db):
    seen = await _listing_ids(chain_db, [(1, SELLER, _offer()), (2, SELLER, _offer(replaces=["tx_1"]))])
    assert seen == {"listings": {"tx_2"}, "match": {"tx_2"}}


@pytest.mark.asyncio
async def test_a_foreign_cancel_cannot_ride_along_with_an_own_one(chain_db):
    """One cancel naming the sender's listing and someone else's hides only the sender's."""
    seen = await _listing_ids(
        chain_db,
        [(1, SELLER, _offer()), (2, OTHER, _offer()), (3, SELLER, _cancel("tx_1", "tx_2"))],
    )
    assert seen == {"listings": {"tx_2"}, "match": {"tx_2"}}


@pytest.mark.asyncio
async def test_listing_reader_ignores_a_row_with_unparseable_payload(chain_db):
    """The reader still skips what is not JSON, and now what is not an object."""
    path, engine = chain_db
    _seed(engine, [(1, SELLER, _offer())])
    conn = sqlite3.connect(path)
    conn.execute('UPDATE "transaction" SET payload = ? WHERE id = 1', (json.dumps([1, 2]),))
    conn.execute(
        'INSERT INTO "transaction" (id, chain_id, tx_hash, sender, recipient, payload, type, status, timestamp, nonce, value, fee, created_at) '
        "VALUES (2, ?, ?, ?, ?, 'not json', 'GPU_MARKET', 'confirmed', 't', 0, 0, 0, '2026-10-02')",
        (CHAIN, f"{2:064x}", SELLER, "0x" + "0" * 40),
    )
    conn.commit()
    conn.close()
    with patch.object(market_mod, "_chain_db_path", lambda: path):
        listings = await market_mod.market_listings()
    assert [x for x in listings["listings"] if x["listing_id"].startswith("tx_")] == []
