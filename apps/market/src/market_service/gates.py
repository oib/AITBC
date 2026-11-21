"""Signature and party gates for the market service's routes.

Extracted from ``main.py``: the wallet-signature proofs (#1634, #1784,
#1893, #1922, #1976) and the credential-transport helpers the handlers
call before touching service state. Leaf module — imports ``deps`` only.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market.job_request_signature import verify_jobs_request_signature
from aitbc.utils.chain_id import resolve_chain_id

from .config import settings
from .services.market_service import MarketService, _secret_matches

# Keep the historic logger name: caplog filters and log-schema checks key on
# "market_service.main".
logger = get_logger("market_service.main")


def _is_operator(request: Request) -> bool:
    """Resolve through ``market_service.main`` at call time.

    The release-window tests monkeypatch ``market_service.main._is_operator``
    to simulate a non-operator caller; binding the deps function directly
    here would bypass that patch. ``main`` re-exports the deps implementation,
    so unpatched behaviour is identical. Lazy import keeps this a leaf module.
    """
    from market_service import main as _main

    return _main._is_operator(request)


def _warn_secret_query_transport(access_key: str, access_secret: str | None, x_access_secret: str | None) -> None:
    """#1942: the ``access_secret`` query parameter leaks the credential into
    proxy access logs — callers must move to ``X-Access-Secret``. Still
    accepted for legacy callers; the warning gives ops a migration signal."""
    if access_secret is not None and x_access_secret is None:
        logger.warning(
            "access_secret supplied as query parameter (access_key=%s) — migrate to X-Access-Secret header", access_key
        )


def _canonical_or_none(raw: Any) -> str | None:
    """Canonicalize an address-like field, or None when it is not one."""
    if not raw:
        return None
    try:
        return canonical_address(str(raw))
    except (TypeError, ValueError):
        return None


async def _party_or_operator_gate(
    request: Request,
    data: dict[str, Any],
    route: str,
    allowed_addresses: set[str],
    *,
    action: str,
) -> JSONResponse | None:
    """#1893: object-scoped mutations need a wallet signature naming an
    allowed party — or the operator credential. The user-tier API key alone
    is not sufficient: it is distributed to CLI users, so an unsigned
    request must not act as an arbitrary buyer/provider/offer owner.
    Returns a ready error response, or None when the request may proceed.
    """
    if _is_operator(request):
        return None
    if not any(
        (
            data.get("signer_address"),
            data.get("chain_id"),
            data.get("issued_at") is not None,
            data.get("signature"),
        )
    ):
        return JSONResponse(
            status_code=403,
            content={"error": f"{action} requires a party signature or the operator credential"},
        )
    error, signer = verify_jobs_request_signature(
        signer_address=data.get("signer_address"),
        chain_id=data.get("chain_id"),
        issued_at=data.get("issued_at"),
        route=route,
        signature=data.get("signature"),
        expected_chain_id=settings.default_chain_id or resolve_chain_id(),
    )
    if error or not signer:
        return JSONResponse(status_code=403, content={"error": error or f"invalid {action} signature"})
    if canonical_address(signer) not in allowed_addresses:
        return JSONResponse(status_code=403, content={"error": "signer is not a party to this object"})
    return None


async def _party_signature_precheck(
    request: Request,
    data: dict[str, Any],
    route: str,
    *,
    action: str,
) -> tuple[bool, str | None, JSONResponse | None]:
    """Pre-lookup half of the #1893 party gate.

    Runs before the target object is fetched so unsigned or badly-signed
    callers cannot probe object existence/state. Returns
    ``(is_operator, canonical_signer, error_response)`` — exactly one of
    ``is_operator``/``signer`` is set on success; ``error_response`` is a
    ready 403 when the request must be rejected. The caller still compares
    ``signer`` against the object's party set after loading it.
    """
    if _is_operator(request):
        return True, None, None
    if not any(
        (
            data.get("signer_address"),
            data.get("chain_id"),
            data.get("issued_at") is not None,
            data.get("signature"),
        )
    ):
        return (
            False,
            None,
            JSONResponse(
                status_code=403,
                content={"error": f"{action} requires a party signature or the operator credential"},
            ),
        )
    error, signer = verify_jobs_request_signature(
        signer_address=data.get("signer_address"),
        chain_id=data.get("chain_id"),
        issued_at=data.get("issued_at"),
        route=route,
        signature=data.get("signature"),
        expected_chain_id=settings.default_chain_id or resolve_chain_id(),
    )
    if error or not signer:
        return False, None, JSONResponse(status_code=403, content={"error": error or f"invalid {action} signature"})
    return False, canonical_address(signer), None


def _alias_claim_signature_gate(request: Request, job_data: dict[str, Any]) -> JSONResponse | None:
    """#2326: a job that aliases a foreign escrow key (``payload.escrow_job_id``)
    must carry a buyer-wallet signature over ``(escrow_job_id, buyer_address)``.

    Market job ids are predictable and the user-tier API key is distributed to
    every CLI user, so without this gate a squatter could register a guessed
    escrow key first and have the victim's locked escrow authorize its token.
    The signature binds the escrow key being claimed and the buyer the job
    asserts — the on-chain escrow's buyer must match that address at verify
    time, so only the escrow's buyer can produce a usable claim. The operator
    credential bypasses, same as the other party gates.
    """
    payload = job_data.get("payload")
    escrow_job_id = payload.get("escrow_job_id") if isinstance(payload, dict) else None
    if not escrow_job_id:
        return None
    if _is_operator(request):
        return None
    buyer_address = job_data.get("buyer_address")
    if not buyer_address:
        return JSONResponse(status_code=403, content={"error": "alias escrow claims require buyer_address"})
    if not any(
        (
            job_data.get("signer_address"),
            job_data.get("chain_id"),
            job_data.get("issued_at") is not None,
            job_data.get("signature"),
        )
    ):
        return JSONResponse(
            status_code=403,
            content={"error": "alias escrow claims require a buyer wallet signature"},
        )
    error, signer = verify_jobs_request_signature(
        signer_address=job_data.get("signer_address"),
        chain_id=job_data.get("chain_id"),
        issued_at=job_data.get("issued_at"),
        route="/v1/market/jobs",
        signature=job_data.get("signature"),
        expected_chain_id=settings.default_chain_id or resolve_chain_id(),
        binding={"escrow_job_id": str(escrow_job_id), "buyer_address": str(buyer_address)},
    )
    if error or not signer:
        return JSONResponse(status_code=403, content={"error": error or "invalid alias claim signature"})
    buyer_canonical = _canonical_or_none(buyer_address)
    if buyer_canonical is None or canonical_address(signer) != buyer_canonical:
        return JSONResponse(status_code=403, content={"error": "alias claim signature does not match buyer_address"})
    return None


def _signed_jobs_request(
    *,
    route: str,
    signer_address: str | None,
    chain_id: str | None,
    issued_at: int | None,
    signature: str | None,
) -> tuple[str | None, JSONResponse | None]:
    """Resolve an optional wallet-signed job request.

    Returns ``(signer, None)`` when the signature verifies, ``(None,
    JSONResponse(403))`` when signature params were supplied but fail, and
    ``(None, None)`` when no signature params were sent at all (anonymous
    caller — the redacted public view still applies).
    """
    if not any((signer_address, chain_id, issued_at is not None, signature)):
        return None, None
    error, signer = verify_jobs_request_signature(
        signer_address=signer_address,
        chain_id=chain_id,
        issued_at=issued_at,
        route=route,
        signature=signature,
        expected_chain_id=settings.default_chain_id or resolve_chain_id(),
    )
    if error or not signer:
        return None, JSONResponse(status_code=403, content={"error": error or "invalid job request signature"})
    return signer, None


def _job_party_addresses(job: dict[str, Any]) -> set[str]:
    """Canonical addresses of a job's buyer/provider, skipping malformed rows.

    Stored addresses are caller-influenced at write time; one that no longer
    canonicalizes is dropped rather than crashing the read (#1449).
    """
    parties: set[str] = set()
    for key in ("buyer_address", "provider_address"):
        raw = job.get(key)
        if not raw:
            continue
        try:
            parties.add(canonical_address(str(raw)))
        except (TypeError, ValueError):
            continue
    return parties


async def _job_party_signature_gate(
    svc: MarketService,
    job_id: str,
    data: dict[str, Any],
    route: str,
    request: Request,
    *,
    action: str,
) -> JSONResponse | None:
    """#1784: settlement-route signature gate, same rule as cancel (#1634).

    #1893: the market API key is user-distributed, so an *unsigned* request
    must present the operator credential — otherwise any key holder could
    act as an arbitrary job party. When signature fields are presented the
    wallet proof must verify AND recover to a job party (buyer or
    provider). Returns a ready error response, or None when the request
    may proceed — a rejected signature never reaches the service, so
    escrow state is untouched.
    """
    if not any(
        (
            data.get("signer_address"),
            data.get("chain_id"),
            data.get("issued_at") is not None,
            data.get("signature"),
        )
    ):
        if _is_operator(request):
            return None
        return JSONResponse(
            status_code=403,
            content={"error": f"{action} requires a job-party signature or the operator credential"},
        )
    job = await svc.get_market_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": f"Job not found: {job_id}"})
    error, signer = verify_jobs_request_signature(
        signer_address=data.get("signer_address"),
        chain_id=data.get("chain_id"),
        issued_at=data.get("issued_at"),
        route=route,
        signature=data.get("signature"),
        expected_chain_id=settings.default_chain_id or resolve_chain_id(),
    )
    if error or not signer:
        return JSONResponse(status_code=403, content={"error": error or f"invalid {action} signature"})
    if canonical_address(signer) not in _job_party_addresses(job):
        return JSONResponse(status_code=403, content={"error": "signer is not a party to this job"})
    return None


async def _pin_confirm_attestation_gate(
    svc: MarketService,
    job_id: str,
    confirm_data: dict[str, Any],
    pin_size: int | None,
) -> JSONResponse | None:
    """#1922: verify the provider's pin-confirm delivery attestation.

    Returns a ready error response, or None when the request may proceed —
    either ``provider_confirmed`` was not claimed (unsigned reports are
    informational and need no gate) or the provider wallet signature over
    the route-bound ``{"cid", "size"}`` binding verified against this job.
    """
    if not confirm_data.get("provider_confirmed"):
        return None
    job = await svc.get_market_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": f"Job not found: {job_id}"})
    binding = confirm_data.get("binding")
    if not isinstance(binding, dict):
        return JSONResponse(
            status_code=403,
            content={"error": 'provider_confirmed requires a signed binding {"cid", "size"}'},
        )
    error, signer = verify_jobs_request_signature(
        signer_address=confirm_data.get("signer_address"),
        chain_id=confirm_data.get("chain_id"),
        issued_at=confirm_data.get("issued_at"),
        route=f"/v1/market/jobs/{job_id}/pin-confirm",
        signature=confirm_data.get("signature"),
        expected_chain_id=settings.default_chain_id or resolve_chain_id(),
        binding=binding,
    )
    if error or not signer:
        return JSONResponse(status_code=403, content={"error": error or "provider signature required"})
    if canonical_address(signer) != canonical_address(str(job.get("provider_address") or "")):
        return JSONResponse(status_code=403, content={"error": "signer is not this job's provider"})
    # The signature covers ``binding`` verbatim; these checks bind the
    # attested content to THIS job — the stored CID is authoritative
    # (set at creation, immutable afterwards) and the attested size
    # must be the size this call records.
    job_payload = job.get("payload") or {}
    if str(binding.get("cid") or "") != str(job_payload.get("cid") or ""):
        return JSONResponse(status_code=403, content={"error": "pin attestation cid does not match this job"})
    if binding.get("size") != pin_size:
        return JSONResponse(status_code=403, content={"error": "pin attestation size does not match the reported size"})
    return None


async def _billing_access_gate(
    svc: MarketService,
    job_id: str,
    x_access_key: str | None,
    x_access_secret: str | None,
    x_job_id: str | None,
) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """#2365: secondary credential check for billing reports.

    Returns ``(job, None)`` when the access-token triple is present, valid,
    and bound to this job — the provider signature gate then decides
    authorization. Returns ``(None, response)`` with the refusal otherwise.
    """
    if not x_access_key or not x_access_secret or not x_job_id:
        return None, JSONResponse(
            status_code=401, content={"error": "X-Access-Key, X-Access-Secret and X-Job-Id are required"}
        )
    job = await svc.get_market_job(job_id)
    if not job:
        return None, JSONResponse(status_code=404, content={"error": f"Job not found: {job_id}"})
    payload = job.get("payload") or {}
    if job.get("access_key") != x_access_key or not _secret_matches(str(payload.get("access_secret") or ""), x_access_secret):
        return None, JSONResponse(status_code=403, content={"error": "invalid access token"})
    if x_job_id != job_id:
        return None, JSONResponse(status_code=403, content={"error": "access token not issued for this job"})
    return job, None


async def _billing_attestation_gate(
    svc: MarketService,
    job_id: str,
    body: dict[str, Any],
    job: dict[str, Any],
) -> JSONResponse | None:
    """#2365: a billing report is settlement input — it must come from the
    provider, not from whoever holds the buyer-issued access token.

    The ``X-Access-Key``/``X-Access-Secret``/``X-Job-Id`` triple proves only
    "holder of the job access token", which the *buyer* minted for the shop
    gate — a buyer could otherwise sign ``{"eval_count": 1, "final": true}``
    and under-bill the provider's escrow. The report therefore also carries
    the job provider's wallet signature over the route-bound
    ``{"metrics", "final"}`` binding (same canonical jobs-request proof as
    pin-confirm, #1922), verified against ``job.provider_address``. The
    access-token triple stays as a secondary check binding the report to
    the serving credential, but it is no longer the authorization.
    """
    binding = {"metrics": body.get("metrics"), "final": body.get("final")}
    error, signer = verify_jobs_request_signature(
        signer_address=body.get("signer_address"),
        chain_id=body.get("chain_id"),
        issued_at=body.get("issued_at"),
        route=f"/v1/market/jobs/{job_id}/billing",
        signature=body.get("signature"),
        expected_chain_id=settings.default_chain_id or resolve_chain_id(),
        binding=binding,
    )
    if error or not signer:
        return JSONResponse(status_code=403, content={"error": error or "provider signature required"})
    if canonical_address(signer) != canonical_address(str(job.get("provider_address") or "")):
        return JSONResponse(status_code=403, content={"error": "signer is not this job's provider"})
    return None


def _buyer_acceptance_window() -> timedelta:
    """How long the buyer has to dispute after the provider's pin attestation (#1976)."""
    raw = os.getenv("MARKET_BUYER_ACCEPTANCE_SECONDS", "86400")
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 86400
    return timedelta(seconds=max(seconds, 0))


def _parse_naive_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


async def _provider_release_window_gate(
    svc: MarketService,
    job_id: str,
    release_data: dict[str, Any],
    request: Request,
) -> JSONResponse | None:
    """#1976: the provider alone may not release its own escrow right after pin-confirm.

    The pin attestation is the provider's own signature (#1922 design limit),
    so provider-attested delivery plus a provider-signed release paid out with
    no buyer input. A release signed ONLY by the provider is therefore held
    until the buyer-acceptance window since ``provider_confirmed_at`` has
    elapsed (the buyer can dispute inside it, which freezes settlement). The
    buyer's own signature or the operator credential release immediately.
    Runs after ``_job_party_signature_gate``, so a presented signature is
    already verified to recover to a job party.
    """
    if _is_operator(request) or not release_data.get("signature"):
        return None
    job = await svc.get_market_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": f"Job not found: {job_id}"})
    _, signer = verify_jobs_request_signature(
        signer_address=release_data.get("signer_address"),
        chain_id=release_data.get("chain_id"),
        issued_at=release_data.get("issued_at"),
        route=f"/v1/market/jobs/{job_id}/release",
        signature=release_data.get("signature"),
        expected_chain_id=settings.default_chain_id or resolve_chain_id(),
    )
    if not signer:
        return None
    signer_addr = canonical_address(signer)
    buyer_raw = str(job.get("buyer_address") or "")
    try:
        if buyer_raw and canonical_address(buyer_raw) == signer_addr:
            return None
    except (TypeError, ValueError):
        pass
    payload = job.get("payload") or {}
    started = _parse_naive_utc(payload.get("provider_confirmed_at")) or _parse_naive_utc(job.get("updated_at"))
    if started is None:
        return JSONResponse(status_code=403, content={"error": "provider release has no acceptance-window start"})
    opens_at = started + _buyer_acceptance_window()
    if datetime.now(UTC).replace(tzinfo=None) < opens_at:
        return JSONResponse(
            status_code=403,
            content={
                "error": "provider cannot release before the buyer-acceptance window ends; the buyer may release or dispute",
                "release_opens_at": opens_at.isoformat(),
            },
        )
    return None
