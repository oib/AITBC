"""Turning a marketplace offer into the job's price and payee (G1).

``aitbc market offer`` publishes a listing and ``aitbc market list`` reads it back,
but nothing carried that listing into the job. ``JobCreate`` took a free-text
``provider_address`` and a free-text ``payment_amount``, so the price a customer was
quoted and the price they paid were two unrelated numbers, and the marketplace was a
catalogue rather than a book of quotes.

This module resolves an offer identifier against the marketplace service and returns
the quote it implies: who is paid, what a unit costs, which unit, and the total for
the quantity asked for. The submit path then holds the job to that quote.

The offer registry lives in the marketplace service's own database, which the
coordinator does not share, so resolution is an HTTP call and can fail two ways that
must not be confused: the buyer named an offer that does not exist or is not for
sale (:class:`OfferUnavailable`, a 400), or the registry could not be asked
(:class:`OfferLookupFailed`, a 503). Guessing a price for either would defeat the
point of asking.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote as urlquote

import httpx

from aitbc.aitbc_logging import get_logger

from ..payments.provider_binding import looks_like_wallet_address

logger = get_logger(__name__)

# The marketplace service, which owns the offer registry. It listens on loopback on
# the hub; ``config.py`` already names the same port in its CORS origins.
MARKETPLACE_BASE_URL = os.getenv("MARKETPLACE_SERVICE_URL", "http://localhost:8102").rstrip("/")

# Job submission blocks on this call, so it is deliberately short. A slow registry
# should fail the submission, not hold a client connection open.
LOOKUP_TIMEOUT_SECONDS = 5.0

# The statuses under which an offer is actually being sold. The two registries spell
# it differently -- the software catalogue writes "active", the structured offer rows
# write "available" -- and everything else ("delisted", "reserved", "inactive", or a
# status added later) fails closed.
SELLABLE_STATUSES = frozenset({"active", "available"})


class OfferUnavailable(Exception):
    """The buyer named an offer that cannot be bought. The submission is at fault."""


class OfferLookupFailed(Exception):
    """The offer registry could not be asked. The service is at fault, not the buyer."""


@dataclass(frozen=True)
class OfferQuote:
    """What a marketplace offer commits to for a given quantity."""

    offer_id: str
    plugin_id: str
    provider_address: str
    unit_price: Decimal
    price_unit: str
    quantity: Decimal
    total: Decimal

    def describe(self) -> str:
        """Render the arithmetic, so a rejected submission says why it was rejected."""
        return f"{self.quantity} x {self.unit_price} per {self.price_unit} = {self.total}"


async def _get(url: str) -> httpx.Response:
    """Perform the bare GET against the offer registry.

    Split out from :func:`_fetch_offer` so the interesting decisions above it -- what a
    404 means, what a 500 means, when to try the second endpoint -- can be tested
    without a live marketplace.
    """
    async with httpx.AsyncClient(timeout=LOOKUP_TIMEOUT_SECONDS) as client:
        return await client.get(url)


async def _fetch_offer(path: str) -> dict[str, Any] | None:
    """Return the offer at ``path``, or None if that path does not name exactly one.

    A 404 is the registry saying it holds no such offer. A 5xx is what it returns when
    the identifier matches several rows -- ``offer_id`` is not unique in the software
    catalogue, where a single ``gpu-offer-001`` fronts five differently priced
    listings. Both mean "this did not resolve to one offer", and both must lead to a
    refusal rather than to a guess, so both return None; the 5xx is logged so an
    operator can still tell an ambiguous identifier from a sick service.
    """
    url = f"{MARKETPLACE_BASE_URL}{path}"
    try:
        response = await _get(url)
    except httpx.HTTPError as exc:
        raise OfferLookupFailed(f"the marketplace service at {MARKETPLACE_BASE_URL} could not be reached") from exc
    if response.status_code == httpx.codes.OK:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OfferLookupFailed(f"the marketplace service returned an unreadable answer for {path}") from exc
        return payload if isinstance(payload, dict) else None
    if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
        logger.warning(
            "Offer lookup %s returned %s; treating the identifier as unresolvable",
            url,
            response.status_code,
        )
    return None


async def resolve_offer(offer_id: str, quantity: Decimal) -> OfferQuote:
    """Resolve ``offer_id`` to the quote it commits its provider to.

    ``plugin_id`` is tried first because it is the catalogue's unique key; ``offer_id``
    is only consulted when that misses, and only helps when it happens to be unique.

    Raises:
        OfferUnavailable: The offer is unknown, ambiguous, not for sale, unpriced, or
            names a provider that escrow cannot pay.
        OfferLookupFailed: The registry could not be reached or did not answer sanely.
    """
    identifier = (offer_id or "").strip()
    if not identifier:
        raise OfferUnavailable("no offer_id was given")
    if quantity <= 0:
        raise OfferUnavailable(f"offer_quantity must be greater than zero, not {quantity}")

    encoded = urlquote(identifier, safe="")
    offer = await _fetch_offer(f"/v1/marketplace/offer/{encoded}")
    if offer is None:
        offer = await _fetch_offer(f"/v1/marketplace/offer-by-id/{encoded}")
    if offer is None:
        raise OfferUnavailable(f"offer {identifier!r} does not name a single listing in the marketplace")

    status_value = str(offer.get("status") or "").strip().lower()
    if status_value not in SELLABLE_STATUSES:
        raise OfferUnavailable(f"offer {identifier!r} is {status_value or 'unlabelled'}, so it is not for sale")

    # G2 binds the escrow's payee to the miner that does the work, and the chain pays
    # that address literally. An offer that advertises a node id rather than a wallet
    # -- several live ones do -- therefore cannot price a job, however valid it looks
    # in the catalogue.
    provider = str(offer.get("provider_address") or "").strip()
    if not looks_like_wallet_address(provider):
        raise OfferUnavailable(
            f"offer {identifier!r} names provider {provider or '(none)'}, which is not a wallet address an escrow can pay"
        )

    raw_price = offer.get("price")
    try:
        unit_price = Decimal(str(raw_price))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OfferUnavailable(f"offer {identifier!r} carries no readable price ({raw_price!r})") from exc
    if unit_price <= 0:
        raise OfferUnavailable(f"offer {identifier!r} is priced at {unit_price}, which cannot be escrowed")

    return OfferQuote(
        offer_id=str(offer.get("offer_id") or identifier),
        plugin_id=str(offer.get("plugin_id") or ""),
        provider_address=provider,
        unit_price=unit_price,
        price_unit=str(offer.get("price_unit") or "").strip() or "unit",
        quantity=quantity,
        total=unit_price * quantity,
    )


__all__ = [
    "LOOKUP_TIMEOUT_SECONDS",
    "MARKETPLACE_BASE_URL",
    "SELLABLE_STATUSES",
    "OfferLookupFailed",
    "OfferQuote",
    "OfferUnavailable",
    "resolve_offer",
]
