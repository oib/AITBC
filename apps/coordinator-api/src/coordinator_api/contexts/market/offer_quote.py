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


# The chain fallback scans newest-first; one page is the RPC's hard clamp.
_CHAIN_OFFER_PAGE_LIMIT = 500
# The fallback is a last resort on a submission-blocking path, so the scan is
# bounded: 10 pages reaches 5,000 GPU_MARKET rows deep (#2477 — a flat 500-tx
# window let noise push a chain-only offer out of reach entirely).
_CHAIN_OFFER_MAX_PAGES = 10


async def _chain_offer_page(url: str, *, first: bool) -> list[Any] | None:
    """One page of GPU_MARKET rows, or None when the first page is unreadable.

    ``first`` marks the opening page: a non-200 or malformed answer there
    means the scan cannot run at all and the caller treats the offer as
    unresolvable. The same failure mid-scan is :class:`OfferLookupFailed` —
    a partial scan cannot be trusted to contain every listing.
    """
    try:
        response = await _get(url)
    except httpx.HTTPError as exc:
        raise OfferLookupFailed(f"the chain RPC at {CHAIN_RPC_URL} could not be reached") from exc
    if response.status_code != httpx.codes.OK:
        if first:
            if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                logger.warning("Chain offer lookup returned %s; treating the scan as empty", response.status_code)
            return None
        raise OfferLookupFailed(f"the chain RPC returned {response.status_code} mid-scan at {url}")
    try:
        rows = response.json()
    except ValueError as exc:
        raise OfferLookupFailed(f"the chain RPC returned an unreadable answer for {url}") from exc
    page_rows = rows.get("transactions", []) if isinstance(rows, dict) else rows
    if not isinstance(page_rows, list):
        if first:
            return None
        raise OfferLookupFailed(f"the chain RPC returned an unreadable answer for {url}")
    return page_rows


async def _fetch_chain_gpu_market_txs() -> list[dict[str, Any]] | None:
    """Page GPU_MARKET rows newest-first via the ``before_id`` cursor.

    Returns None only when the first page cannot be read at all (the caller
    treats that as unresolvable, same as a catalogue 404).
    """
    txs: list[dict[str, Any]] = []
    before_id: int | None = None
    exhausted = False
    for page in range(_CHAIN_OFFER_MAX_PAGES):
        params = f"transaction_type=GPU_MARKET&limit={_CHAIN_OFFER_PAGE_LIMIT}"
        if before_id is not None:
            params += f"&before_id={before_id}"
        page_rows = await _chain_offer_page(f"{CHAIN_RPC_URL}/rpc/transactions?{params}", first=page == 0)
        if page_rows is None:
            return None
        txs.extend(tx for tx in page_rows if isinstance(tx, dict))
        if len(page_rows) < _CHAIN_OFFER_PAGE_LIMIT:
            exhausted = True
            break
        ids = [i for tx in page_rows if isinstance(tx, dict) and isinstance(i := tx.get("transaction_id"), int)]
        if not ids:
            exhausted = True
            break
        before_id = min(ids)
    if not exhausted:
        logger.warning(
            "Chain offer scan hit the %s-page cap without exhausting GPU_MARKET history; older listings are unseen",
            _CHAIN_OFFER_MAX_PAGES,
        )
    return txs


def _chain_offer_candidates(
    confirmed: list[dict[str, Any]], withdrawn: set[str], identifier: str
) -> tuple[list[tuple[int, dict[str, Any]]], list[tuple[int, dict[str, Any]]]]:
    """Split confirmed-tx matches into ``(tx_id, offer)`` pairs by the field
    that matched — ``offer_id`` (seller-chosen, resolvable) vs ``plugin_id``
    (shared by design, ambiguous across sellers)."""
    offer_id_matches: list[tuple[int, dict[str, Any]]] = []
    plugin_matches: list[tuple[int, dict[str, Any]]] = []
    for tx in confirmed:
        matched = _chain_offer_match(tx, withdrawn, identifier)
        if matched is None:
            continue
        offer, matched_on = matched
        tx_id = tx.get("transaction_id")
        pair = (tx_id if isinstance(tx_id, int) else 0, offer)
        (offer_id_matches if matched_on == "offer_id" else plugin_matches).append(pair)
    return offer_id_matches, plugin_matches


async def _fetch_offer_from_chain(identifier: str) -> dict[str, Any] | None:
    """Resolve ``identifier`` against confirmed GPU_MARKET software offers.

    ``offer_id`` matches resolve deterministically — the earliest confirmed
    listing wins, so a squatter's later tx reusing the id can neither deny
    the sale nor re-price it (#2477). ``plugin_id`` is shared by design, so
    it resolves only when exactly one listing matches; several sellers (or
    several listings) stay unresolvable rather than guessed.
    """
    txs = await _fetch_chain_gpu_market_txs()
    if txs is None:
        return None

    confirmed = [tx for tx in txs if tx.get("status") == "confirmed"]
    withdrawn = _chain_withdrawn_listing_ids(confirmed)
    offer_id_matches, plugin_matches = _chain_offer_candidates(confirmed, withdrawn, identifier)

    if offer_id_matches:
        offer_id_matches.sort(key=lambda m: m[0])
        if len(offer_id_matches) > 1:
            logger.info(
                "Chain offer lookup for %r: %s listings share the offer_id; using the earliest",
                identifier,
                len(offer_id_matches),
            )
        return offer_id_matches[0][1]
    if len(plugin_matches) == 1:
        return plugin_matches[0][1]
    if plugin_matches:
        logger.warning(
            "Chain offer lookup for %r matched %s plugin_id listings; treating as unresolvable",
            identifier,
            len(plugin_matches),
        )
    return None


def _chain_offer_match(tx: dict[str, Any], withdrawn: set[str], identifier: str) -> tuple[dict[str, Any], str] | None:
    """The catalogue-shaped offer one confirmed tx advertises, plus which
    identifier field matched (``offer_id`` or ``plugin_id``) — or None.

    Consensus applies GPU_MARKET payloads without validating them, so the
    payload's ``provider_address`` is not bound to the signer (#2477): a tx
    that names a payee other than its sender is not an offer this seller
    made, and matching it would quote a job to an address that never
    published it.
    """
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
    if payload.get("offer_id") == identifier:
        matched_on = "offer_id"
    elif plugin_id == identifier:
        matched_on = "plugin_id"
    else:
        return None
    sender = str(tx.get("sender") or "")
    claimed = payload.get("provider_address")
    if claimed and (not sender or canonical_address(str(claimed)) != canonical_address(sender)):
        return None
    return {
        "offer_id": str(payload.get("offer_id") or ""),
        "plugin_id": plugin_id,
        "service_type": service_type,
        "model": model,
        "price": payload.get("price"),
        "price_unit": payload.get("price_unit") or "",
        "provider_address": str(claimed or sender or ""),
        "status": payload.get("status"),
        "endpoint": payload.get("endpoint") or "",
    }, matched_on


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
