"""Offer, bid, match, and analytics routes for the market service.

Extracted verbatim from ``main.py`` — route paths, methods, dependencies,
and handler bodies are unchanged; only the registration target moved from
``app`` to an ``APIRouter`` included by ``main``.
"""

from decimal import Decimal
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from aitbc.aitbc_logging import get_logger
from aitbc.market import OfferStatus
from aitbc.utils.json_utils import to_jsonable

from ..config import settings
from ..deps import get_market_service, get_matching_service, require_market_api_key
from ..domain.offer_status import try_to_offer_status
from ..gates import _canonical_or_none, _party_or_operator_gate, _party_signature_precheck
from ..operations import (
    _OPS_ERRORS,
    _begin_operation,
    _fail_operation,
    _get_operations_ledger,
    _reject_operation,
)
from ..services.market_service import MAX_PAYMENT_AMOUNT, MarketService
from ..services.matching_service import MatchingService

# Keep the historic logger name: caplog filters and log-schema checks key on
# "market_service.main".
logger = get_logger("market_service.main")

router = APIRouter()


@router.get("/v1/market/offers")
async def get_offers(
    svc: Annotated[MarketService, Depends(get_market_service)],
    status: str | None = None,
    region: str | None = None,
    gpu_model: str | None = None,
    chain_id: str | None = None,
) -> Any:
    """Get market offers (v0.6.6: optional chain_id filter)"""
    try:
        logger.info(
            "GET /v1/market/offers called with filters: status=%s, region=%s, gpu_model=%s, chain_id=%s",
            status,
            region,
            gpu_model,
            chain_id,
        )
        result = await svc.list_offers(status=status, region=region, gpu_model=gpu_model, chain_id=chain_id)
        logger.info("GET /v1/market/offers returned %s offers", len(result))
        return result
    except ValueError as e:
        # A status filter naming a state that does not exist. It used to return 200 and an
        # empty list, which reads as "no offers are in that state" rather than "there is no
        # such state" -- the same answer a typo gets and a real filter gets (V23-83).
        logger.info("Rejecting offer listing: %s", e)
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in GET /v1/market/offers: %s: %s", type(e).__name__, str(e))
        raise


@router.get("/v1/market/offers/{offer_id}")
async def get_offer(offer_id: str, svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Get a specific market offer"""
    try:
        logger.info("GET /v1/market/offers/%s called", offer_id)
        result = await svc.get_offer(offer_id)
        if not result:
            # `get_offer` returns None for an offer that is not there, and this route used to
            # hand that straight back -- 200 with a body of `null`. Every other "not found" in
            # this service is a 404 with this exact body, including the three other callers of
            # this same method and the sibling `/offers/{id}/history` over the same resource.
            # A client that checked the status code got told the offer existed (V23-76).
            logger.info("GET /v1/market/offers/%s: not found", offer_id)
            return JSONResponse(status_code=404, content={"error": "Offer not found"})
        logger.info("GET /v1/market/offers/%s returned an offer", offer_id)
        # to_jsonable: the raw SQLModel would be float-cast by
        # jsonable_encoder on its Decimal price columns (#1635).
        return to_jsonable(result.model_dump(mode="python"))
    except Exception as e:
        logger.error("Error in GET /v1/market/offers/%s: %s: %s", offer_id, type(e).__name__, str(e))
        raise


async def _create_escrow_bg(job_id: str, buyer: str, provider: str, amount: Decimal) -> None:
    """Fire-and-forget escrow creation — runs outside the SQLAlchemy session."""
    try:
        headers = {"X-API-Key": settings.blockchain_rpc_api_key} if settings.blockchain_rpc_api_key else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.blockchain_rpc_url}/rpc/escrow/create",
                json={"job_id": job_id, "buyer": buyer, "provider": provider, "amount": str(amount)},
                headers=headers,
            )
            if resp.status_code == 200:
                logger.info("Escrow created for job %s: %s", job_id, resp.json().get("contract_id"))
            else:
                logger.warning("Escrow creation returned %s: %s", resp.status_code, resp.text)
    except _OPS_ERRORS as e:
        logger.warning("Escrow creation skipped (non-fatal): %s", e)


@router.post("/v1/market/offers/{offer_id}/book", dependencies=[Depends(require_market_api_key)])
async def book_offer(
    offer_id: str,
    booking_data: dict[str, Any],
    background_tasks: BackgroundTasks,
    request: Request,
    svc: Annotated[MarketService, Depends(get_market_service)],
) -> Any:
    """Book/purchase a market offer"""
    key, attempt, early = await _begin_operation(request, "book_offer", {"offer_id": offer_id, "body": booking_data})
    if early is not None:
        return early
    try:
        logger.info("POST /v1/market/offers/%s/book called with data keys: %s", offer_id, booking_data.keys())
        # #1893: booking creates a bid + escrow naming the buyer — the buyer
        # wallet in the body is self-asserted, so it must be proven by a
        # signature (or the operator credential) before any offer state is
        # touched or escrow is created.
        buyer_canonical = _canonical_or_none(booking_data.get("wallet") or booking_data.get("buyer"))
        book_gate = await _party_or_operator_gate(
            request,
            booking_data,
            f"/v1/market/offers/{offer_id}/book",
            {buyer_canonical} if buyer_canonical else set(),
            action="book",
        )
        if book_gate is not None:
            return await _reject_operation(key, attempt, book_gate)
        # `svc.book_offer` signals both "no such offer" and "offer is not available" by
        # raising ValueError, and this handler re-raised both into a 500 -- so booking a
        # typo'd offer id looked like the service had fallen over (V23-81). Checked here in
        # the shape `cancel_offer` uses over the same resource: 404 for absent, 400 for the
        # wrong state, same body. The service keeps its ValueErrors as the backstop.
        offer = await svc.get_offer(offer_id)
        if not offer:
            return await _reject_operation(key, attempt, JSONResponse(status_code=404, content={"error": "Offer not found"}))
        if try_to_offer_status(offer.status) is not OfferStatus.AVAILABLE:
            return await _reject_operation(
                key,
                attempt,
                JSONResponse(status_code=400, content={"error": f"Offer is not available (status={offer.status})"}),
            )
        result = await svc.book_offer(offer_id, booking_data)
        logger.info("POST /v1/market/offers/%s/book completed", offer_id)
        buyer = booking_data.get("wallet") or booking_data.get("buyer")
        provider = booking_data.get("provider") or result.get("provider")
        # The booking already committed — a malformed amount must not turn a
        # successful booking into a 500, and a non-finite one must never reach
        # the on-chain escrow payload (svc.book_offer rejects these up front;
        # this is the belt-and-braces read of the same fields).
        try:
            amount = Decimal(str(booking_data.get("amount") or booking_data.get("price") or 0))
        except _OPS_ERRORS:
            amount = Decimal("0")
        bid_id = result.get("bid_id")
        if bid_id and buyer and provider and amount.is_finite() and amount > 0:
            background_tasks.add_task(_create_escrow_bg, bid_id, buyer, provider, amount)
            result["escrow_contract_id"] = "(pending — created in background)"
        if key:
            await _get_operations_ledger().complete_async(key, attempt, result)
        return result
    except ValueError as e:
        # The pre-check narrows the window but does not close it: another request can book
        # the offer between the two calls, and `svc.book_offer` raises `ValueError` again.
        # Every `ValueError` reachable from here is the caller's -- the service's two status
        # checks, plus `float(duration_hours)` over a request field -- so 400 is right for
        # all of them, and a race no longer reads as the service failing.
        #
        # Not `Decimal(price)`: that raises `InvalidOperation`, an `ArithmeticError`, and
        # still reaches the client as a 500. Left alone because the same conversion runs
        # again below on `amount`, after the bid has been committed, where answering 400
        # would deny a booking that happened.
        logger.info("Rejecting booking of offer %s: %s", offer_id, e)
        return await _reject_operation(key, attempt, JSONResponse(status_code=400, content={"error": str(e)}))
    except Exception as e:
        logger.error("Error in POST /v1/market/offers/%s/book: %s: %s", offer_id, type(e).__name__, str(e))
        await _fail_operation(key, attempt, type(e).__name__)
        raise


@router.post("/v1/market/bids/{bid_id}/complete", dependencies=[Depends(require_market_api_key)])
async def complete_bid(
    bid_id: str,
    request_data: dict[str, Any],
    request: Request,
    svc: Annotated[MarketService, Depends(get_market_service)],
) -> Any:
    """Complete a market bid after on-chain payment confirms.

    The confirmed payment tx must carry a payload reference binding it to
    this bid or its offer — ``bid_id``, ``offer_id``, ``order_id``, or
    ``job_id`` (the escrow convention keys ``payload.job_id`` to the bid
    id). A plain unbound transfer is refused (#1914)."""
    tx_hash = request_data.get("tx_hash") or request_data.get("transaction_hash", "")
    if not tx_hash:
        return JSONResponse(status_code=400, content={"error": "tx_hash is required"})
    key, attempt, early = await _begin_operation(request, "complete_bid", {"bid_id": bid_id, "body": request_data})
    if early is not None:
        return early
    try:
        result = await svc.complete_bid(bid_id, tx_hash)
        if key:
            await _get_operations_ledger().complete_async(key, attempt, jsonable_encoder(result))
        return result
    except ValueError as e:
        logger.info("Rejecting bid completion: %s", e)
        return await _reject_operation(key, attempt, JSONResponse(status_code=400, content={"error": str(e)}))
    except Exception as e:
        logger.error("Error in POST /v1/market/bids/%s/complete: %s: %s", bid_id, type(e).__name__, str(e))
        await _fail_operation(key, attempt, type(e).__name__)
        raise


class MatchRequest(BaseModel):
    """Request model for market matching (v0.6.6)."""

    requirements: dict[str, Any] = Field(default_factory=dict)
    max_price: Decimal | None = None
    preferred_region: str | None = None
    chain_id: str | None = None

    @field_validator("max_price")
    @classmethod
    def _bounded_max_price(cls, v: Decimal | None) -> Decimal | None:
        # Same money ceiling as offer/booking/payment fields — a NaN or
        # unbounded max_price would otherwise reach the SQL price filter and
        # the coordinator task payload unchecked.
        if v is None:
            return v
        if not v.is_finite() or v < 0 or v > MAX_PAYMENT_AMOUNT:
            raise ValueError(f"max_price must be a finite amount between 0 and {MAX_PAYMENT_AMOUNT}")
        return v


@router.post("/v1/market/match", dependencies=[Depends(require_market_api_key)])
async def match_request(
    request: MatchRequest, http_request: Request, svc: Annotated[MatchingService, Depends(get_matching_service)]
) -> Any:
    """Match a compute request to the best available GPU offer (v0.6.6).

    Uses price-time priority matching and integrates with the agent-coordinator
    task queue. Reserves the matched offer via OfferFSM.

    Ledgered like the other mutating routes: the reservation commits before
    the coordinator task is submitted, so a retry cannot tell whether the
    first attempt reserved an offer (and possibly already queued the job).
    ``allow_adopt=False`` -- a replayed match would reserve a second offer,
    so ambiguous outcomes go ``uncertain`` and 409 until reconciled rather
    than silently double-reserving.
    """
    key, attempt, early = await _begin_operation(
        http_request, "match_request", request.model_dump(mode="python"), allow_adopt=False
    )
    if early is not None:
        return early
    try:
        logger.info("POST /v1/market/match called (chain_id=%s)", request.chain_id)
        match = await svc.match_and_assign(
            request.requirements,
            max_price=request.max_price,
            preferred_region=request.preferred_region,
            chain_id=request.chain_id,
        )
        result = {"status": "success", "match": match}
        if key:
            await _get_operations_ledger().complete_async(key, attempt, result)
        return result
    except Exception as e:
        logger.error("Error in POST /v1/market/match: %s: %s", type(e).__name__, str(e))
        await _fail_operation(key, attempt, type(e).__name__)
        raise


@router.post("/v1/market/offers", dependencies=[Depends(require_market_api_key)])
async def create_offer(
    offer_data: dict[str, Any], request: Request, svc: Annotated[MarketService, Depends(get_market_service)]
) -> Any:
    """Create a new market offer"""
    key = ""
    attempt = 0
    try:
        logger.info("POST /v1/market/offers called with data keys: %s", offer_data.keys())
        if "provider" not in offer_data:
            if "wallet" in offer_data:
                offer_data["provider"] = offer_data["wallet"]
            elif "metadata" in offer_data and "provider" in offer_data.get("metadata", {}):
                offer_data["provider"] = offer_data["metadata"]["provider"]
            else:
                offer_data["provider"] = "default-provider"
        # Re-executing a crashed create would mint a second offer id, so this
        # op is non-adoptable: an expired lease goes ``uncertain`` for operator
        # resolution instead of risking a duplicate.
        key, attempt, early = await _begin_operation(request, "create_offer", offer_data, allow_adopt=False)
        if early is not None:
            return early
        result = await svc.create_offer(offer_data)
        logger.info("POST /v1/market/offers created offer with id: %s", result.id)
        # to_jsonable keeps Decimal prices exact — the raw model would be
        # float-cast by jsonable_encoder (#1635). The ledger stores the same
        # encoding so replay matches the live response.
        response_body = to_jsonable(result.model_dump(mode="python"))
        if key:
            await _get_operations_ledger().complete_async(key, attempt, response_body)
        return response_body
    except ValueError as e:
        # Only reachable from the status validation the service now does: a request naming a
        # state this service does not have. 400 rather than the 500 that splatting the body
        # into the model produced for every other kind of bad field (V23-83).
        logger.info("Rejecting offer creation: %s", e)
        return await _reject_operation(key, attempt, JSONResponse(status_code=400, content={"error": str(e)}))
    except Exception as e:
        logger.error("Error in POST /v1/market/offers: %s: %s", type(e).__name__, str(e))
        # create_offer may have committed before raising — terminal so a
        # retry cannot mint a duplicate offer.
        await _fail_operation(key, attempt, type(e).__name__, terminal=True)
        raise


@router.get("/v1/market/analytics")
async def get_analytics(
    svc: Annotated[MarketService, Depends(get_market_service)],
    # `period_type: str | None` with no default is a *required* query parameter to FastAPI --
    # the same accident V23-83 found on cancel_offer and v0.6.6 found on /offers. The service
    # below has always declared `period_type: str = "daily"`, and that default was unreachable:
    # a caller who omitted the parameter got 422 instead, and one who supplied it overrode it.
    # Stating "daily" here restores the intended behaviour and puts the default in the spec.
    period_type: str = "daily",
) -> Any:
    """Get market analytics"""
    return await svc.get_analytics(period_type=period_type)


@router.get("/v1/market")
async def get_market_overview(svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Get hardware+software bundle market overview"""
    logger.info("GET /v1/market called - market overview")
    offers = await svc.list_offers()
    # By state, not by spelling: one of the four offers in the deployed database is stored as
    # "open", so it was counted in `total_offers` and left out of `active_offers`, and left out
    # of the regions and service types the overview advertises -- an offer that is available
    # and invisible (V23-83).
    active_offers = [o for o in offers if try_to_offer_status(str(o.get("status", ""))) is OfferStatus.AVAILABLE]
    avg_price = Decimal("0")
    if active_offers:
        # `.get("price_per_hour", 0)` returns the default only when the key is missing, and it
        # never is -- `list_offers` puts it in every dict. `price_per_hour` is nullable and
        # defaults to None, so one priceless offer made this `int + None` and the whole
        # overview answered 500. Not reachable before: `active_offers` was only ever empty in
        # the tests, and every offer in the deployed database happens to carry a price
        # (V23-83).
        # Via `str` because these dicts are untyped: a price that arrived as a float would
        # otherwise raise on `Decimal + float` rather than quietly rounding.
        prices = [Decimal(str(o.get("price_per_hour") or 0)) for o in active_offers]
        avg_price = sum(prices, Decimal("0")) / len(active_offers)
    return {
        "status": "operational",
        "total_offers": len(offers),
        "active_offers": len(active_offers),
        "average_price_per_hour": str(avg_price),
        "regions": list({o.get("region", "unknown") for o in active_offers}),
        "service_types": list({o.get("service_type", "unknown") for o in active_offers}),
        "timestamp": svc.get_current_timestamp(),
    }


@router.get("/v1/market/offers/{offer_id}/history")
async def get_offer_history(offer_id: str, svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Get offer history (migrated from Coordinator API)"""
    logger.info("GET /v1/market/offers/%s/history called", offer_id)
    offer = await svc.get_offer(offer_id)
    if not offer:
        return JSONResponse(status_code=404, content={"error": "Offer not found"})
    history = {
        "offer_id": offer_id,
        "created_at": offer.created_at,
        "price_history": [
            {
                "price": str(offer.price_per_hour) if offer.price_per_hour is not None else None,
                "timestamp": offer.created_at,
                "reason": "initial_listing",
            }
        ],
        "booking_count": 0,
        "total_revenue": 0,
        "last_booked": None,
    }
    return history


@router.post("/v1/market/offers/{offer_id}/cancel", dependencies=[Depends(require_market_api_key)])
async def cancel_offer(
    offer_id: str,
    request: Request,
    svc: Annotated[MarketService, Depends(get_market_service)],
    # `reason: str | None` with no default is a *required* query parameter to FastAPI, and the
    # published spec said so. Cancelling without one answered 422 -- so the 500 underneath was
    # only reachable by a caller who happened to send `?reason=`, which is why this endpoint
    # looked merely awkward rather than broken. The body already defaults it (V23-83).
    reason: str | None = None,
    cancel_data: dict[str, Any] | None = None,
) -> Any:
    """Cancel offer (migrated from Coordinator API)"""
    logger.info("POST /v1/market/offers/%s/cancel called", offer_id)
    key, attempt, early = await _begin_operation(request, "cancel_offer", {"offer_id": offer_id, "reason": reason})
    if early is not None:
        return early
    # #1893 respin: signature precheck runs BEFORE the offer lookup so
    # unsigned/badly-signed callers get 403 without learning whether the
    # offer exists; the signer↔provider match still happens post-lookup.
    is_operator, signer, gate_error = await _party_signature_precheck(
        request,
        cancel_data or {},
        f"/v1/market/offers/{offer_id}/cancel",
        action="offer cancel",
    )
    if gate_error is not None:
        return await _reject_operation(key, attempt, gate_error)
    offer = await svc.get_offer(offer_id)
    if not offer:
        return await _reject_operation(key, attempt, JSONResponse(status_code=404, content={"error": "Offer not found"}))
    provider_canonical = _canonical_or_none(getattr(offer, "provider", None))
    if not is_operator and (signer is None or provider_canonical is None or signer != provider_canonical):
        return await _reject_operation(
            key, attempt, JSONResponse(status_code=403, content={"error": "signer is not a party to this object"})
        )

    current = try_to_offer_status(offer.status)
    if current is OfferStatus.DELISTED:
        # Compared by state: "closed" and "delisted" are this end state too, and an offer
        # stored under either used to fall through to the transition and be told the
        # transition was invalid, rather than that it was already cancelled.
        return await _reject_operation(
            key, attempt, JSONResponse(status_code=400, content={"error": "Offer already cancelled"})
        )
    if current is None:
        return await _reject_operation(
            key, attempt, JSONResponse(status_code=400, content={"error": f"Offer has an unknown status: '{offer.status}'"})
        )
    if current in (OfferStatus.RESERVED, OfferStatus.IN_USE):
        # A buyer holds this offer (reserved) or is running paid work on it
        # (in_use/escrowed). Cancelling must not silently release the hold or
        # delist out from under the job — the stranded-reservation recovery
        # path (#816) did exactly that and is replaced by an explicit refusal;
        # the hold is released by the booking/bid lifecycle, not by cancel.
        logger.info("Refusing to cancel offer %s in status %s", offer_id, offer.status)
        return await _reject_operation(
            key,
            attempt,
            JSONResponse(status_code=400, content={"error": f"Offer cannot be cancelled while it is {offer.status}"}),
        )
    try:
        await svc.update_offer_status(offer_id, "cancelled")
    except ValueError:
        # Reached for an offer someone holds: RESERVED can go to IN_USE, back to AVAILABLE, or
        # EXPIRED, but not straight to DELISTED -- a provider cannot delist out from under a
        # buyer who has reserved. 400 rather than 409 to match `book_offer` over this same
        # resource, where 409 is reserved for optimistic-concurrency mismatches (V23-81).
        logger.info("Refusing to cancel offer %s in status %s", offer_id, offer.status)
        return await _reject_operation(
            key,
            attempt,
            JSONResponse(status_code=400, content={"error": f"Offer cannot be cancelled while it is {offer.status}"}),
        )
    cancelled_offer = {
        "offer_id": offer_id,
        "status": "cancelled",
        "cancelled_at": svc.get_current_timestamp(),
        "reason": reason or "user_requested",
    }
    if key:
        await _get_operations_ledger().complete_async(key, attempt, cancelled_offer)
    logger.info("Cancelled offer %s", offer_id)
    return cancelled_offer


@router.get("/v1/market/performance")
async def get_market_performance(
    svc: Annotated[MarketService, Depends(get_market_service)],
    # Required by the same accident as /analytics above, and feeding the same service default.
    period: str = "daily",
) -> Any:
    """Get market performance metrics (migrated from Coordinator API)"""
    logger.info("GET /v1/market/performance called with period=%s", period)
    analytics = await svc.get_analytics(period_type=period)
    performance = {
        "period": period,
        "total_volume": analytics.get("total_volume", 0),
        "total_trades": analytics.get("total_trades", 0),
        "average_price": analytics.get("average_price", 0),
        "price_volatility": analytics.get("price_volatility", 0),
        "liquidity_score": analytics.get("liquidity_score", 0),
        "active_providers": analytics.get("active_providers", 0),
        "utilization_rate": analytics.get("utilization_rate", 0),
        "fill_rate": analytics.get("fill_rate", 0),
    }
    return performance


@router.post("/v1/market/dynamic-pricing", dependencies=[Depends(require_market_api_key)])
async def calculate_dynamic_pricing(
    offer_id: str,
    current_demand: int,
    current_supply: int,
    svc: Annotated[MarketService, Depends(get_market_service)],
) -> Any:
    """Calculate dynamic pricing based on supply/demand (migrated from Coordinator API)"""
    logger.info("POST /v1/market/dynamic-pricing called for offer %s", offer_id)
    offer = await svc.get_offer(offer_id)
    if not offer:
        return JSONResponse(status_code=404, content={"error": "Offer not found"})
    base_price = offer.price_per_hour or 0
    supply_demand_ratio = current_demand / max(current_supply, 1)
    if supply_demand_ratio > 1.5:
        price_multiplier = 1.2
    elif supply_demand_ratio > 1.0:
        price_multiplier = 1.1
    elif supply_demand_ratio < 0.5:
        price_multiplier = 0.9
    else:
        price_multiplier = 1.0
    suggested_price = base_price * Decimal(str(price_multiplier))
    return {
        "offer_id": offer_id,
        # str(Decimal): price fields must not be float-cast by
        # jsonable_encoder (#1635).
        "base_price": str(base_price) if base_price else "0",
        "suggested_price": str(suggested_price),
        "price_multiplier": price_multiplier,
        "supply_demand_ratio": supply_demand_ratio,
        "current_demand": current_demand,
        "current_supply": current_supply,
        "reason": "dynamic_pricing_calculation",
    }
