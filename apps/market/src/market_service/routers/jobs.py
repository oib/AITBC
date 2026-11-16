"""Market-job routes (v0.25.7 first-class IPFS and future software jobs)
plus the access-token read routes.

Extracted verbatim from ``main.py`` — route paths, methods, dependencies,
and handler bodies are unchanged; only the registration target moved from
``app`` to an ``APIRouter`` included by ``main``. ``/v1/market/jobs/usage``
must stay registered before ``/v1/market/jobs/{job_id}`` — the order below
matches the original file.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address

from ..deps import _is_market_admin, get_market_service, require_market_api_key, require_market_operator_key
from ..gates import (
    _job_party_addresses,
    _job_party_signature_gate,
    _pin_confirm_attestation_gate,
    _provider_release_window_gate,
    _signed_jobs_request,
    _warn_secret_query_transport,
)
from ..services.market_service import MarketService, _secret_matches, max_page_size, public_job_view

# Keep the historic logger name: caplog filters and log-schema checks key on
# "market_service.main".
logger = get_logger("market_service.main")

router = APIRouter()


@router.post("/v1/market/jobs", dependencies=[Depends(require_market_api_key)])
async def create_market_job(job_data: dict[str, Any], svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Create a market job and payment record."""
    try:
        logger.info("POST /v1/market/jobs called with data keys: %s", job_data.keys())
        result = await svc.create_market_job(job_data)
        logger.info("POST /v1/market/jobs created job: %s", result.get("job_id"))
        return result
    except ValueError as e:
        logger.info("Rejecting market job creation: %s", e)
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/market/jobs: %s: %s", type(e).__name__, str(e))
        raise


@router.get("/v1/market/jobs")
async def list_market_jobs(
    svc: Annotated[MarketService, Depends(get_market_service)],
    request: Request,
    buyer_address: str | None = None,
    provider_address: str | None = None,
    service_type: str | None = None,
    state: str | None = None,
    offer_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    signer_address: str | None = None,
    chain_id: str | None = None,
    issued_at: int | None = None,
    signature: str | None = None,
) -> Any:
    """List market jobs.

    Anonymous callers get the redacted public view — no customer file or
    rental detail. A wallet-signed request (``signer_address`` +
    ``chain_id`` + ``issued_at`` + ``signature`` over the canonical
    jobs-request message) returns full rows for jobs the signer is a party
    to; the service API key returns full rows unfiltered.
    """
    try:
        logger.info("GET /v1/market/jobs called")
        limit = min(limit, max_page_size())
        signer, error_response = _signed_jobs_request(
            route="/v1/market/jobs",
            signer_address=signer_address,
            chain_id=chain_id,
            issued_at=issued_at,
            signature=signature,
        )
        if error_response is not None:
            return error_response
        if signer:
            # Full rows go only to the recovered signer — an address filter
            # naming someone else contradicts the proof and is a 403.
            for claimed in (buyer_address, provider_address):
                if not claimed:
                    continue
                try:
                    matches = canonical_address(claimed) == canonical_address(signer)
                except (AttributeError, TypeError, ValueError):
                    matches = False
                if not matches:
                    return JSONResponse(status_code=403, content={"error": "address filter does not match signer"})
            return await svc.list_market_jobs(
                buyer_address=buyer_address,
                provider_address=provider_address,
                service_type=service_type,
                state=state,
                offer_id=offer_id,
                limit=limit,
                offset=offset,
                owner_address=signer,
            )
        jobs = await svc.list_market_jobs(
            buyer_address=buyer_address,
            provider_address=provider_address,
            service_type=service_type,
            state=state,
            offer_id=offer_id,
            limit=limit,
            offset=offset,
        )
        if _is_market_admin(request):
            return jobs
        return [public_job_view(job) for job in jobs]
    except Exception as e:
        logger.error("Error in GET /v1/market/jobs: %s: %s", type(e).__name__, str(e))
        raise


@router.get("/v1/market/jobs/usage")
async def get_market_job_usage(
    buyer_address: str,
    offer_id: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
) -> Any:
    """Return active storage usage in bytes for a buyer/offer pair."""
    try:
        logger.info("GET /v1/market/jobs/usage called")
        return {
            "buyer_address": buyer_address,
            "offer_id": offer_id,
            "used_bytes": await svc.get_market_job_usage(buyer_address, offer_id),
        }
    except Exception as e:
        logger.error("Error in GET /v1/market/jobs/usage: %s: %s", type(e).__name__, str(e))
        raise


@router.get("/v1/market/jobs/{job_id}")
async def get_market_job(
    job_id: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
    request: Request,
    signer_address: str | None = None,
    chain_id: str | None = None,
    issued_at: int | None = None,
    signature: str | None = None,
    x_access_key: str | None = Header(default=None),
    x_access_secret: str | None = Header(default=None),
) -> Any:
    """Get a market job by ID.

    Anonymous callers get the redacted public view. The full record goes to
    the service API key, the job's rental credential (``X-Access-Key`` +
    ``X-Access-Secret`` — the same check ``/v1/market/access/{key}`` runs),
    or a wallet signature from the job's buyer or provider.
    """
    try:
        logger.info("GET /v1/market/jobs/%s called", job_id)
        result = await svc.get_market_job(job_id)
        if not result:
            return JSONResponse(status_code=404, content={"error": f"Job not found: {job_id}"})
        if _is_market_admin(request):
            return result
        auth_attempted = False
        if x_access_key or x_access_secret:
            auth_attempted = True
            payload = result.get("payload") or {}
            if result.get("access_key") == x_access_key and _secret_matches(
                str(payload.get("access_secret") or ""), x_access_secret or ""
            ):
                return result
        signer, error_response = _signed_jobs_request(
            route=f"/v1/market/jobs/{job_id}",
            signer_address=signer_address,
            chain_id=chain_id,
            issued_at=issued_at,
            signature=signature,
        )
        if error_response is not None:
            return error_response
        if signer:
            if canonical_address(signer) in _job_party_addresses(result):
                return result
            auth_attempted = True
        if auth_attempted:
            return JSONResponse(status_code=403, content={"error": "not authorized for this job's full record"})
        return public_job_view(result)
    except Exception as e:
        logger.error("Error in GET /v1/market/jobs/%s: %s: %s", job_id, type(e).__name__, str(e))
        raise


@router.post("/v1/market/jobs/{job_id}/cancel", dependencies=[Depends(require_market_api_key)])
async def cancel_market_job(
    job_id: str,
    request: Request,
    svc: Annotated[MarketService, Depends(get_market_service)],
    cancel_data: dict[str, Any] | None = None,
) -> Any:
    """Cancel a market job and request a refund."""
    try:
        cancel_data = cancel_data or {}
        logger.info("POST /v1/market/jobs/%s/cancel called", job_id)
        # #1634/#1893: a cancel flips the job to CANCELED and queues a refund,
        # so it needs a job-party wallet signature — or the operator
        # credential for sweeper/admin flows. The shared gate enforces both.
        gate = await _job_party_signature_gate(
            svc, job_id, cancel_data, f"/v1/market/jobs/{job_id}/cancel", request, action="cancel"
        )
        if gate is not None:
            return gate
        result = await svc.cancel_market_job(job_id, reason=cancel_data.get("reason", ""))
        return result
    except ValueError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/market/jobs/%s/cancel: %s: %s", job_id, type(e).__name__, str(e))
        raise


@router.post("/v1/market/jobs/{job_id}/dispute", dependencies=[Depends(require_market_api_key)])
async def dispute_market_job(
    job_id: str,
    request: Request,
    svc: Annotated[MarketService, Depends(get_market_service)],
    dispute_data: dict[str, Any] | None = None,
) -> Any:
    """Open a dispute freeze on a market job's escrow settlement (#1783).

    Same rule as cancel (#1634/#1893): a job-party wallet signature, or the
    operator credential for sweeper/admin flows.
    """
    try:
        dispute_data = dispute_data or {}
        logger.info("POST /v1/market/jobs/%s/dispute called", job_id)
        gate = await _job_party_signature_gate(
            svc, job_id, dispute_data, f"/v1/market/jobs/{job_id}/dispute", request, action="dispute"
        )
        if gate is not None:
            return gate
        result = await svc.dispute_market_job(job_id, reason=dispute_data.get("reason", ""))
        return result
    except ValueError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/market/jobs/%s/dispute: %s: %s", job_id, type(e).__name__, str(e))
        raise


@router.post("/v1/market/jobs/{job_id}/dispute/resolve", dependencies=[Depends(require_market_operator_key)])
async def resolve_market_job_dispute(
    job_id: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
) -> Any:
    """Clear a dispute freeze so the sweeper can settle/refund (#1783).

    Operator-tier only: resolution is an admin action, not a party one.
    """
    try:
        logger.info("POST /v1/market/jobs/%s/dispute/resolve called", job_id)
        result = await svc.resolve_market_job_dispute(job_id)
        return result
    except ValueError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/market/jobs/%s/dispute/resolve: %s: %s", job_id, type(e).__name__, str(e))
        raise


@router.post("/v1/market/jobs/{job_id}/pin-confirm", dependencies=[Depends(require_market_api_key)])
async def confirm_market_job_pin(
    job_id: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
    confirm_data: dict[str, Any] | None = None,
) -> Any:
    """Confirm that a job's content has been pinned.

    #1922: unsigned ``size`` / ``pin_tx_hash`` updates are informational
    only — the buyer's ``aitbc market host`` flow reports the pinned size
    that way, but they never mark the job delivered: the state stays
    QUEUED/RUNNING-as-was and release still demands verified pin evidence.
    ``provider_confirmed`` is the provider's own delivery attestation, so
    it requires the job provider's wallet signature (the same canonical
    jobs-request proof the read routes accept, bound to this route) plus a
    ``binding`` object ``{"cid": ..., "size": ...}`` folded into the signed
    message and checked against the job's stored CID and the reported size
    — the attestation cannot be replayed for different content or a
    different size. ``pin_tx_hash`` remains an unverified caller claim in
    both modes; no on-chain pin-proof convention exists to check it
    against.
    """
    try:
        confirm_data = confirm_data or {}
        logger.info("POST /v1/market/jobs/%s/pin-confirm called", job_id)
        # size lands verbatim in job.payload and is later summed into usage
        # analytics — reject anything that is not a non-negative int before
        # any state is touched (#1449).
        pin_size = confirm_data.get("size")
        if pin_size is not None and (isinstance(pin_size, bool) or not isinstance(pin_size, int) or pin_size < 0):
            return JSONResponse(status_code=400, content={"error": "size must be a non-negative integer"})
        gate = await _pin_confirm_attestation_gate(svc, job_id, confirm_data, pin_size)
        if gate is not None:
            return gate
        result = await svc.confirm_market_job_pin(
            job_id,
            size=confirm_data.get("size"),
            pin_tx_hash=confirm_data.get("pin_tx_hash"),
            provider_confirmed=bool(confirm_data.get("provider_confirmed")),
        )
        return result
    except ValueError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/market/jobs/%s/pin-confirm: %s: %s", job_id, type(e).__name__, str(e))
        raise


@router.post("/v1/market/jobs/{job_id}/release", dependencies=[Depends(require_market_api_key)])
async def release_market_job_payment(
    job_id: str,
    request: Request,
    svc: Annotated[MarketService, Depends(get_market_service)],
    release_data: dict[str, Any] | None = None,
) -> Any:
    """Release the escrow payment for a market job.

    #1893: a job-party wallet signature, or the operator credential —
    unsigned user-key requests are refused.
    """
    try:
        release_data = release_data or {}
        logger.info("POST /v1/market/jobs/%s/release called", job_id)
        gate = await _job_party_signature_gate(
            svc, job_id, release_data, f"/v1/market/jobs/{job_id}/release", request, action="release"
        )
        if gate is not None:
            return gate
        gate = await _provider_release_window_gate(svc, job_id, release_data, request)
        if gate is not None:
            return gate
        result = await svc.release_market_job_payment(job_id, release_data=release_data)
        return result
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/market/jobs/%s/release: %s: %s", job_id, type(e).__name__, str(e))
        raise


@router.post("/v1/market/jobs/{job_id}/refund", dependencies=[Depends(require_market_api_key)])
async def refund_market_job_payment(
    job_id: str,
    request: Request,
    svc: Annotated[MarketService, Depends(get_market_service)],
    refund_data: dict[str, Any] | None = None,
) -> Any:
    """Refund the escrow payment for a market job.

    #1893: a job-party wallet signature, or the operator credential —
    unsigned user-key requests are refused.
    """
    try:
        refund_data = refund_data or {}
        logger.info("POST /v1/market/jobs/%s/refund called", job_id)
        gate = await _job_party_signature_gate(
            svc, job_id, refund_data, f"/v1/market/jobs/{job_id}/refund", request, action="refund"
        )
        if gate is not None:
            return gate
        result = await svc.refund_market_job_payment(job_id, reason=refund_data.get("reason", ""), refund_data=refund_data)
        return result
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/market/jobs/%s/refund: %s: %s", job_id, type(e).__name__, str(e))
        raise


@router.get("/v1/market/jobs/{job_id}/access")
async def get_market_job_access(
    job_id: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
    authenticated: Annotated[dict[str, Any], Depends(require_market_api_key)],
) -> Any:
    """Return the access metadata for a market job (customer only).

    access_secret is no longer returned: it is stored as a digest, so the
    plaintext cannot be recovered here — the customer receives it once in
    the CLI output at purchase time.
    """
    try:
        logger.info("GET /v1/market/jobs/%s/access called", job_id)
        job = await svc.get_market_job(job_id)
        if not job:
            return JSONResponse(status_code=404, content={"error": f"Job not found: {job_id}"})
        return {
            "cid": job.get("payload", {}).get("cid"),
            "ipfs_api": job.get("payload", {}).get("ipfs_api"),
            "public_endpoint": job.get("payload", {}).get("public_endpoint"),
            "access_key": job.get("payload", {}).get("access_key"),
            "expires_at": job.get("expires_at"),
            "size": job.get("payload", {}).get("size"),
        }
    except Exception as e:
        logger.error("Error in GET /v1/market/jobs/%s/access: %s: %s", job_id, type(e).__name__, str(e))
        raise


@router.get("/v1/market/access/{access_key}")
async def get_market_access_token(
    access_key: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
    access_secret: str | None = None,
    x_access_secret: Annotated[str | None, Header()] = None,
) -> Any:
    """Validate an access token and return the CID and retrieval metadata.

    The secret may arrive as the ``access_secret`` query parameter (legacy
    callers) or the ``X-Access-Secret`` header (shop_gate since #1613 — keeps
    the credential out of URLs and access logs). Header wins when both are
    sent so a stale query value cannot shadow the fresh credential.
    """
    secret = x_access_secret if x_access_secret is not None else access_secret
    _warn_secret_query_transport(access_key, access_secret, x_access_secret)
    if not secret:
        return JSONResponse(status_code=401, content={"error": "access_secret is required (X-Access-Secret header preferred)"})
    try:
        logger.info("GET /v1/market/access/%s called", access_key)
        result = await svc.get_market_job_access_token(access_key, secret)
        if not result:
            return JSONResponse(status_code=404, content={"error": "Invalid, expired, or unknown access token"})
        return result
    except Exception as e:
        logger.error("Error in GET /v1/market/access/%s: %s: %s", access_key, type(e).__name__, str(e))
        raise
