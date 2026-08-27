"""Tests for binding a job to the marketplace offer that priced it (G1).

The catalogue used to be advisory: a customer read a price out of ``aitbc market
list`` and then typed whatever they liked into ``payment_amount``. These pin the rule
that naming an ``offer_id`` makes the listing binding -- it decides the payee and the
total, and a submission that disagrees is refused before a job exists.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from fastapi import HTTPException

from coordinator_api.contexts.infrastructure.routers import client as client_router
from coordinator_api.contexts.marketplace import offer_quote
from coordinator_api.contexts.marketplace.offer_quote import (
    OfferLookupFailed,
    OfferUnavailable,
    resolve_offer,
)
from coordinator_api.contexts.payments.provider_binding import looks_like_wallet_address
from coordinator_api.schemas import JobCreate

# The wallet a live hub offer is actually sold by, in the canonical 0x spelling
# the marketplace stores and in a lowercase 0x spelling a caller might use.
SELLER = "0xA54B82312beb65D0E90c21717ea372396991Fa36"
SELLER_LOWER = "0xa54b82312beb65d0e90c21717ea372396991fa36"
OUTSIDER = "0x2222222222222222222222222222222222222222"


def _offer(**overrides):
    """An offer as the marketplace service returns it, with the live field spellings."""
    offer = {
        "plugin_id": "ollama-llama3.2-3b",
        "offer_id": "sw_offer_20260823191152_84ec042f",
        "service_type": "ollama",
        "model": "llama3.2:3b",
        "price": "0.00100000",
        "price_unit": "per_1k_tokens",
        "provider_address": SELLER,
        "status": "active",
    }
    offer.update(overrides)
    return offer


def _serve(monkeypatch, responses):
    """Answer offer lookups from ``responses``, keyed by the path that was requested.

    A path that is absent answers 404, which is how the registry says it holds no such
    offer. Values may be a dict (served as 200), an int status code, or an exception
    to raise, so a test can describe a registry that is confused or absent.
    """
    seen: list[str] = []

    async def fake_get(url: str) -> httpx.Response:
        path = url[len(offer_quote.MARKETPLACE_BASE_URL) :]
        seen.append(path)
        answer = responses.get(path, 404)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):
            return httpx.Response(answer, json={"error": "Offer not found"})
        return httpx.Response(200, json=answer)

    monkeypatch.setattr(offer_quote, "_get", fake_get)
    return seen


def _submission(**overrides) -> JobCreate:
    fields = {"payload": {"type": "inference", "prompt": "hello"}, "ttl_seconds": 900}
    fields.update(overrides)
    return JobCreate(**fields)


# --------------------------------------------------------------------------
# resolving the offer
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_offer_is_looked_up_by_plugin_id_first(monkeypatch):
    """plugin_id is the catalogue's unique key, so it is asked before offer_id."""
    seen = _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer()})

    quote = await resolve_offer("ollama-llama3.2-3b", Decimal("1"))

    assert seen == ["/v1/marketplace/offer/ollama-llama3.2-3b"]
    assert quote.provider_address == SELLER
    assert quote.unit_price == Decimal("0.001")
    assert quote.price_unit == "per_1k_tokens"


@pytest.mark.asyncio
async def test_an_offer_id_is_tried_when_the_plugin_lookup_misses(monkeypatch):
    """Customers hold offer ids too, so a missed plugin lookup falls through."""
    offer_id = "sw_offer_20260823191152_84ec042f"
    seen = _serve(monkeypatch, {f"/v1/marketplace/offer-by-id/{offer_id}": _offer()})

    quote = await resolve_offer(offer_id, Decimal("1"))

    assert seen == [f"/v1/marketplace/offer/{offer_id}", f"/v1/marketplace/offer-by-id/{offer_id}"]
    assert quote.offer_id == offer_id


@pytest.mark.asyncio
async def test_quantity_multiplies_the_advertised_unit_price(monkeypatch):
    """A per-unit offer only becomes a total once a quantity is named."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer()})

    quote = await resolve_offer("ollama-llama3.2-3b", Decimal("3"))

    assert quote.total == Decimal("0.003")
    assert "3 x 0.00100000 per per_1k_tokens = 0.00300000" == quote.describe()


@pytest.mark.asyncio
async def test_an_unknown_offer_is_refused(monkeypatch):
    """Both lookups miss, so there is no price to charge."""
    _serve(monkeypatch, {})

    with pytest.raises(OfferUnavailable, match="does not name a single listing"):
        await resolve_offer("no-such-offer", Decimal("1"))


@pytest.mark.asyncio
async def test_an_ambiguous_offer_id_is_refused(monkeypatch):
    """gpu-offer-001 fronts five differently priced listings; picking one would guess."""
    _serve(monkeypatch, {"/v1/marketplace/offer-by-id/gpu-offer-001": 500})

    with pytest.raises(OfferUnavailable, match="does not name a single listing"):
        await resolve_offer("gpu-offer-001", Decimal("1"))


@pytest.mark.asyncio
async def test_a_delisted_offer_is_refused(monkeypatch):
    """A listing that was withdrawn is not a quote, whatever price it still carries."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer(status="delisted")})

    with pytest.raises(OfferUnavailable, match="not for sale"):
        await resolve_offer("ollama-llama3.2-3b", Decimal("1"))


@pytest.mark.asyncio
async def test_an_offer_sold_by_a_node_id_is_refused(monkeypatch):
    """Live offers name providers like aitbc-miner-1, which escrow cannot pay."""
    _serve(monkeypatch, {"/v1/marketplace/offer/aitbc3-gpu-1": _offer(provider_address="aitbc-miner-1")})

    with pytest.raises(OfferUnavailable, match="not a wallet address"):
        await resolve_offer("aitbc3-gpu-1", Decimal("1"))


@pytest.mark.asyncio
async def test_a_free_offer_is_refused(monkeypatch):
    """A zero price cannot be escrowed, so it must not reach the payment path."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer(price="0")})

    with pytest.raises(OfferUnavailable, match="cannot be escrowed"):
        await resolve_offer("ollama-llama3.2-3b", Decimal("1"))


@pytest.mark.asyncio
async def test_a_marketplace_outage_is_not_the_buyers_fault(monkeypatch):
    """An unreachable registry is a different failure from an invalid offer."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": httpx.ConnectError("refused")})

    with pytest.raises(OfferLookupFailed, match="could not be reached"):
        await resolve_offer("ollama-llama3.2-3b", Decimal("1"))


# --------------------------------------------------------------------------
# holding the submission to the quote
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_quote_supplies_the_price_and_the_payee(monkeypatch):
    """A submission that names an offer need not repeat its terms."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer()})

    priced, quote = await client_router._apply_offer_quote(_submission(offer_id="ollama-llama3.2-3b"))

    assert quote is not None
    assert priced.payment_amount == Decimal("0.001")
    assert priced.provider_address == SELLER


@pytest.mark.asyncio
async def test_a_payment_amount_that_disagrees_is_refused(monkeypatch):
    """The number the customer was shown and the number they pay are now one number."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer()})
    req = _submission(offer_id="ollama-llama3.2-3b", payment_amount=Decimal("0.0001"))

    with pytest.raises(HTTPException) as raised:
        await client_router._apply_offer_quote(req)

    assert raised.value.status_code == 400
    assert "does not match the quote" in raised.value.detail


@pytest.mark.asyncio
async def test_over_funding_is_refused_too(monkeypatch):
    """Release pays out the whole escrow, so paying too much is not generosity."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer()})
    req = _submission(offer_id="ollama-llama3.2-3b", payment_amount=Decimal("500"))

    with pytest.raises(HTTPException) as raised:
        await client_router._apply_offer_quote(req)

    assert raised.value.status_code == 400


@pytest.mark.asyncio
async def test_a_payment_amount_that_agrees_is_accepted(monkeypatch):
    """A client that did the arithmetic itself is not punished for it."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer()})
    req = _submission(offer_id="ollama-llama3.2-3b", offer_quantity=Decimal("4"), payment_amount=Decimal("0.004"))

    priced, quote = await client_router._apply_offer_quote(req)

    assert quote is not None
    assert priced.payment_amount == Decimal("0.004")


@pytest.mark.asyncio
async def test_a_provider_address_that_disagrees_is_refused(monkeypatch):
    """Naming someone else as the payee is the redirection G2 stops at dispatch."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer()})
    req = _submission(offer_id="ollama-llama3.2-3b", provider_address=OUTSIDER)

    with pytest.raises(HTTPException) as raised:
        await client_router._apply_offer_quote(req)

    assert raised.value.status_code == 400
    assert "disagrees with offer" in raised.value.detail


@pytest.mark.asyncio
async def test_a_lowercase_spelling_of_the_seller_still_agrees(monkeypatch):
    """The same twenty bytes in a different 0x case is the same seller, not a mismatch."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": _offer()})
    req = _submission(offer_id="ollama-llama3.2-3b", provider_address=SELLER_LOWER)

    priced, quote = await client_router._apply_offer_quote(req)

    assert quote is not None
    assert priced.provider_address == SELLER


@pytest.mark.asyncio
async def test_an_unreachable_registry_answers_503(monkeypatch):
    """A submission is not rejected as invalid because the marketplace is down."""
    _serve(monkeypatch, {"/v1/marketplace/offer/ollama-llama3.2-3b": httpx.ConnectError("refused")})

    with pytest.raises(HTTPException) as raised:
        await client_router._apply_offer_quote(_submission(offer_id="ollama-llama3.2-3b"))

    assert raised.value.status_code == 503


@pytest.mark.asyncio
async def test_a_submission_without_an_offer_is_untouched(monkeypatch):
    """Existing clients that price jobs directly keep working."""
    _serve(monkeypatch, {})
    req = _submission(payment_amount=Decimal("5"), provider_address=OUTSIDER)

    priced, quote = await client_router._apply_offer_quote(req)

    assert quote is None
    assert priced is req


@pytest.mark.asyncio
async def test_operators_can_require_every_priced_job_to_name_an_offer(monkeypatch):
    """COORDINATOR_REQUIRE_OFFER closes the free-text price path entirely."""
    monkeypatch.setattr(client_router, "_OFFER_REQUIRE", True)

    with pytest.raises(HTTPException) as raised:
        await client_router._apply_offer_quote(_submission(payment_amount=Decimal("5")))

    assert raised.value.status_code == 400
    assert "must name the offer_id" in raised.value.detail


@pytest.mark.asyncio
async def test_requiring_an_offer_still_allows_unpriced_work(monkeypatch):
    """The requirement is about money, so free jobs are unaffected by it."""
    monkeypatch.setattr(client_router, "_OFFER_REQUIRE", True)

    priced, quote = await client_router._apply_offer_quote(_submission())

    assert quote is None
    assert priced.payment_amount is None


# --------------------------------------------------------------------------
# the shared wallet-shape test
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,payable",
    [
        (SELLER, True),
        (SELLER_LOWER, True),
        ("0xEB29516824E95AdFFeEdfc914941F0fbEd0bB1a4", True),
        ("aitbc-miner-1", False),
        ("aitbc3-provider", False),
        ("0x" + "z" * 40, False),
        ("0x1234", False),
        ("", False),
        (None, False),
    ],
)
def test_only_real_addresses_are_payable(value, payable):
    """Offers advertise node ids in the same field as wallets; only wallets can be paid."""
    assert looks_like_wallet_address(value) is payable
