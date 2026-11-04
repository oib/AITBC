"""Pin for #1056: unauthenticated market listing writes are refused.

POST /market/create and DELETE /market/listing/{id} used to accept unsigned
writes: anyone could publish under any seller address, delete any listing,
and collide ids after a delete. Both routes now require a secp256k1
signature from the seller.
"""

from __future__ import annotations

import json

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException

from aitbc_chain.rpc import market as market_mod
from aitbc_chain.rpc.market import (
    MarketCreateRequest,
    MarketDeleteRequest,
    market_create,
    market_delete_listing,
)


@pytest.fixture(autouse=True)
def clean_listings(monkeypatch):
    """Each test starts from an empty listing store and a fresh id sequence."""
    monkeypatch.setattr(market_mod, "_market_listings", [])
    import itertools

    monkeypatch.setattr(market_mod, "_listing_seq", itertools.count(1))
    yield


@pytest.fixture(autouse=True)
def quiet_events(monkeypatch):
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(market_mod, "_publish_offer_event", _noop)
    yield


def _sign(private_key: keys.PrivateKey, payload: dict) -> str:
    message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return private_key.sign_msg_hash(keccak(message)).to_hex()


def _create_body(seller_key: keys.PrivateKey, **over) -> dict:
    body = {
        "seller_address": seller_key.public_key.to_checksum_address(),
        "item_type": "gpu",
        "price": 10.0,
        "description": "a card",
    }
    body.update(over)
    unsigned = {k: v for k, v in MarketCreateRequest(**body).model_dump().items() if k != "signature"}
    body["signature"] = _sign(seller_key, {"action": "market_create", **unsigned})
    return body


@pytest.mark.asyncio
async def test_unsigned_create_refused():
    body = MarketCreateRequest(**{k: v for k, v in _create_body(keys.PrivateKey(b"\x01" * 32)).items() if k != "signature"})
    with pytest.raises(HTTPException) as exc:
        await market_create(body)
    assert exc.value.status_code == 403
    assert market_mod._market_listings == []


@pytest.mark.asyncio
async def test_wrong_seller_signature_refused():
    real = keys.PrivateKey(b"\x01" * 32)
    forger = keys.PrivateKey(b"\x02" * 32)
    body = _create_body(real)
    unsigned = dict(MarketCreateRequest(**{k2: v2 for k2, v2 in body.items() if k2 != "signature"}).model_dump().items())
    body["signature"] = _sign(forger, {"action": "market_create", **unsigned})
    with pytest.raises(HTTPException) as exc:
        await market_create(MarketCreateRequest(**body))
    assert exc.value.status_code == 403
    assert market_mod._market_listings == []


@pytest.mark.asyncio
async def test_signed_create_stores_listing_under_verified_seller():
    seller = keys.PrivateKey(b"\x01" * 32)
    result = await market_create(MarketCreateRequest(**_create_body(seller)))
    assert result["status"] == "created"
    assert market_mod._market_listings[0]["seller_address"] == seller.public_key.to_checksum_address()


@pytest.mark.asyncio
async def test_bad_price_is_400_not_500():
    seller = keys.PrivateKey(b"\x01" * 32)
    body = _create_body(seller, price=-5.0)
    with pytest.raises(HTTPException) as exc:
        await market_create(MarketCreateRequest(**body))
    # the validation 400 used to be swallowed by the catch-all and answer 500
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_listing_ids_do_not_reuse_after_delete():
    seller = keys.PrivateKey(b"\x01" * 32)
    ids = []
    for _ in range(2):
        r = await market_create(MarketCreateRequest(**_create_body(seller)))
        ids.append(r["listing_id"])
    sig = _sign(seller, {"action": "market_delete", "listing_id": ids[0]})
    await market_delete_listing(ids[0], MarketDeleteRequest(signature=sig))
    r = await market_create(MarketCreateRequest(**_create_body(seller)))
    ids.append(r["listing_id"])
    assert len(set(ids)) == 3, f"id collision: {ids}"


@pytest.mark.asyncio
async def test_unsigned_delete_refused():
    seller = keys.PrivateKey(b"\x01" * 32)
    r = await market_create(MarketCreateRequest(**_create_body(seller)))
    lid = r["listing_id"]

    with pytest.raises(HTTPException) as exc:
        await market_delete_listing(lid)
    assert exc.value.status_code == 403

    stranger = keys.PrivateKey(b"\x03" * 32)
    with pytest.raises(HTTPException) as exc:
        await market_delete_listing(
            lid, MarketDeleteRequest(signature=_sign(stranger, {"action": "market_delete", "listing_id": lid}))
        )
    assert exc.value.status_code == 403
    assert len(market_mod._market_listings) == 1


@pytest.mark.asyncio
async def test_seller_signed_delete_removes_listing():
    seller = keys.PrivateKey(b"\x01" * 32)
    r = await market_create(MarketCreateRequest(**_create_body(seller)))
    lid = r["listing_id"]
    sig = _sign(seller, {"action": "market_delete", "listing_id": lid})
    result = await market_delete_listing(lid, MarketDeleteRequest(signature=sig))
    assert result["status"] == "deleted"
    assert market_mod._market_listings == []
