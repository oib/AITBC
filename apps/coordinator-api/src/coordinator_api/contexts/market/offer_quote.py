"""Turning a market offer into the job's price and payee (G1).

``aitbc market offer`` publishes a listing and ``aitbc market list`` reads it back,
but nothing carried that listing into the job. ``JobCreate`` took a free-text
``provider_address`` and a free-text ``payment_amount``, so the price a customer was
quoted and the price they paid were two unrelated numbers, and the market was a
catalogue rather than a book of quotes.

This module resolves an offer identifier against the market service and returns
the quote it implies: who is paid, what a unit costs, which unit, and the total for
the quantity asked for. The submit path then holds the job to that quote.

The offer registry lives in the market service's own database, which the
coordinator does not share, so resolution is an HTTP call and can fail two ways that
must not be confused: the buyer named an offer that does not exist or is not for
sale (:class:`OfferUnavailable`, a 400), or the registry could not be asked
(:class:`OfferLookupFailed`, a 503). Guessing a price for either would defeat the
point of asking.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote as urlquote

import httpx

from aitbc.aitbc_logging import get_logger
from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.env_compat import market_getenv

from ..payments.provider_binding import looks_like_wallet_address

logger = get_logger(__name__)

# The market service, which owns the offer registry. It listens on loopback on
# the hub; ``config.py`` already names the same port in its CORS origins.
MARKET_BASE_URL = market_getenv("MARKET_SERVICE_URL", "http://localhost:8102").rstrip("/")

# The chain is the source of truth for offers: the catalogue only holds rows a
# provider registered via POST /v1/market/offer, and offers published before
# that registration existed — or whose republish was dedup-skipped — live only
# as confirmed GPU_MARKET transactions (whisper/base tx_8, #2312).
CHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_RPC_URL).rstrip("/")

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
    """What a market offer commits to for a given quantity."""

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
    without a live market.
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
    url = f"{MARKET_BASE_URL}{path}"
    try:
        response = await _get(url)
    except httpx.HTTPError as exc:
        raise OfferLookupFailed(f"the market service at {MARKET_BASE_URL} could not be reached") from exc
    if response.status_code == httpx.codes.OK:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OfferLookupFailed(f"the market service returned an unreadable answer for {path}") from exc
        return payload if isinstance(payload, dict) else None
    if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
        logger.warning(
            "Offer lookup %s returned %s; treating the identifier as unresolvable",
            url,
            response.status_code,
        )
    return None


def _tx_payload(tx: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a transaction payload, which the endpoint may serve as JSON text."""
    payload = tx.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _as_id_list(value: Any) -> list[str]:
    """A payload field that may hold one id, a list of ids, or nothing."""
    if not value:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(v) for v in value]


def _chain_withdrawn_listing_ids(txs: list[dict[str, Any]]) -> set[str]:
    """``tx_<id>`` listings withdrawn on chain — mirrors ``withdrawn_listing_ids``.

    Only a seller's own cancel (``action`` cancel/cancelled or ``status``
    cancelled) or a later offer's ``replaces`` hides a listing, and only when
    the referencing sender is the listing's seller. Consensus applies GPU_MARKET
    payloads without validating that binding, so the check is repeated here
    exactly as the chain's own listing readers do (#2312).
    """
    seller = {
        f"tx_{tx.get('transaction_id')}": canonical_address(str(tx.get("sender") or ""))
        for tx in txs
        if tx.get("transaction_id") is not None
    }
    withdrawn: set[str] = set()
    for tx in txs:
        tx_id = tx.get("transaction_id")
        if tx_id is None:
            continue
        payload = _tx_payload(tx)
        is_cancel = payload.get("action", "") in ("cancel", "cancelled") or str(payload.get("status", "")).lower() == (
            "cancelled"
        )
        if is_cancel:
            withdrawn.add(f"tx_{tx_id}")
            named = [*_as_id_list(payload.get("order_id")), *_as_id_list(payload.get("order_ids"))]
        else:
            named = _as_id_list(payload.get("replaces"))
        who = canonical_address(str(tx.get("sender") or ""))
        if not who:
            continue
        withdrawn.update(listing_id for listing_id in named if seller.get(listing_id) == who)
    return withdrawn


async def _fetch_offer_from_chain(identifier: str) -> dict[str, Any] | None:
    """Resolve ``identifier`` against confirmed GPU_MARKET software offers.

    Returns None when nothing — or more than one distinct listing — matches;
    the caller treats both as unresolvable, same as the catalogue's 404/500.
    """
    url = f"{CHAIN_RPC_URL}/rpc/transactions"
    try:
        response = await _get(f"{url}?transaction_type=GPU_MARKET&limit=500")
    except httpx.HTTPError as exc:
        raise OfferLookupFailed(f"the chain RPC at {CHAIN_RPC_URL} could not be reached") from exc
    if response.status_code != httpx.codes.OK:
        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            logger.warning("Chain offer lookup returned %s; treating %r as unresolvable", response.status_code, identifier)
        return None
    try:
        rows = response.json()
    except ValueError as exc:
        raise OfferLookupFailed(f"the chain RPC returned an unreadable answer for {url}") from exc
    txs = rows.get("transactions", []) if isinstance(rows, dict) else rows
    if not isinstance(txs, list):
        return None

    confirmed = [tx for tx in txs if isinstance(tx, dict) and tx.get("status") == "confirmed"]
    withdrawn = _chain_withdrawn_listing_ids(confirmed)
    matches = [offer for tx in confirmed if (offer := _chain_offer_match(tx, withdrawn, identifier)) is not None]
    if len(matches) != 1:
        if len(matches) > 1:
            logger.warning("Chain offer lookup for %r matched %s listings; treating as unresolvable", identifier, len(matches))
        return None
    return matches[0]


def _chain_offer_match(tx: dict[str, Any], withdrawn: set[str], identifier: str) -> dict[str, Any] | None:
    """The catalogue-shaped offer one confirmed tx advertises, or None."""
    tx_id = tx.get("transaction_id")
    if tx_id is None or f"tx_{tx_id}" in withdrawn:
        return None
    payload = _tx_payload(tx)
    if payload.get("action") != "software_offer":
        return None
    if str(payload.get("status", "")).lower() not in SELLABLE_STATUSES:
        return None
    service_type = str(payload.get("service_type") or "")
    model = str(payload.get("model") or "")
    plugin_id = f"{service_type}-{model.replace(':', '-')}" if service_type and model else ""
    if payload.get("offer_id") != identifier and plugin_id != identifier:
        return None
    return {
        "offer_id": str(payload.get("offer_id") or ""),
        "plugin_id": plugin_id,
        "service_type": service_type,
        "model": model,
        "price": payload.get("price"),
        "price_unit": payload.get("price_unit") or "",
        "provider_address": str(payload.get("provider_address") or tx.get("sender") or ""),
        "status": payload.get("status"),
        "endpoint": payload.get("endpoint") or "",
    }


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
    offer = await _fetch_offer(f"/v1/market/offer/{encoded}")
    if offer is None:
        offer = await _fetch_offer(f"/v1/market/offer-by-id/{encoded}")
    if offer is None:
        # The catalogue only holds registered rows; offers that exist purely
        # as confirmed GPU_MARKET transactions still price a job (#2312).
        offer = await _fetch_offer_from_chain(identifier)
    if offer is None:
        raise OfferUnavailable(f"offer {identifier!r} does not name a single listing in the market")

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
    "MARKET_BASE_URL",
    "SELLABLE_STATUSES",
    "OfferLookupFailed",
    "OfferQuote",
    "OfferUnavailable",
    "resolve_offer",
]
