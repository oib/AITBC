"""
Disputes Router - Dispute resolution API endpoints

Provides:
- Dispute filing
- Evidence submission
- Arbitrator voting
- Case tracking
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ....auth import AuthDep
from ....storage import SessionDep
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from ...infrastructure.domain.job import Job
from ...infrastructure.domain.user import Wallet
from ...staking.domain.staking import AgentStake, StakeStatus
from ..services.dispute_resolution import DisputeResolutionService, DisputeStatus, get_dispute_service
from aitbc.rate_limiting import rate_limit

router = APIRouter(prefix="/disputes", tags=["disputes"])


def _caller_identities(session: Any, user: dict[str, Any]) -> set[str]:
    """Lowercased identities the JWT subject can act as: its sub plus every
    wallet address registered to the user (#1854)."""
    sub = str(user.get("sub") or "")
    identities = {sub.lower()} if sub else set()
    if sub:
        identities |= {
            str(w.address).lower()
            for w in session.execute(select(Wallet).where(Wallet.user_id == sub)).scalars().all()
            if w.address
        }
    return identities


def _active_stake_total(session: Any, identities: set[str]) -> Decimal:
    """Sum of the caller's ACTIVE AgentStake amounts, matched on wallet
    addresses (stake rows are address-keyed, never user subs)."""
    if not identities:
        return Decimal(0)
    rows = (
        session.execute(
            select(AgentStake).where(
                AgentStake.status == StakeStatus.ACTIVE,
                (func.lower(AgentStake.staker_address).in_(identities))
                | (func.lower(AgentStake.agent_wallet).in_(identities)),
            )
        )
        .scalars()
        .all()
    )
    return sum((r.amount for r in rows), Decimal(0))


def _is_party(dispute: Any, identities: set[str]) -> bool:
    parties = {str(dispute.client).lower(), str(dispute.provider).lower(), str(dispute.filed_by).lower()}
    return bool(parties & identities)


class FileDisputeRequest(BaseModel):
    """Request to file a dispute"""

    job_id: str
    client: str
    provider: str
    amount: int
    reason: str
    initial_evidence: str | None = None


class SubmitEvidenceRequest(BaseModel):
    """Request to submit evidence"""

    dispute_id: str
    evidence_type: str
    description: str
    ipfs_hash: str | None = None


class CastVoteRequest(BaseModel):
    """Request to cast a vote"""

    dispute_id: str
    outcome: str  # client_wins, provider_wins, split
    reasoning: str
    stake_amount: int


@router.post("/file", summary="File a dispute")
@rate_limit(rate=20, per=60)
def file_dispute(request: Request, req: FileDisputeRequest, user: AuthDep, session: SessionDep) -> dict[str, Any]:
    """File a new dispute for a job.

    The job must exist and the caller must be one of its parties
    (``client_id``, ``provider_address`` or ``assigned_miner_id``); admins
    bypass the party check. Parties and amount are taken from the job row —
    the request's ``client``/``provider``/``amount`` fields are accepted for
    compatibility but never trusted (#1854).
    """
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        job = session.get(Job, req.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {req.job_id} not found")

        filed_by = str(user["sub"])
        if user.get("role") != "admin":
            job_parties = {
                str(job.client_id or "").lower(),
                str(job.provider_address or "").lower(),
                str(job.assigned_miner_id or "").lower(),
            } - {""}
            if not (_caller_identities(session, user) & job_parties):
                raise HTTPException(status_code=403, detail="Caller is not a party to this job")

        # Parties/amount come from the job row only — a NULL provider or
        # payment_amount is a data conflict, never a reason to trust the
        # request body (#1879).
        provider = job.provider_address or job.assigned_miner_id
        if provider is None:
            raise HTTPException(status_code=409, detail="Job has no provider assigned")
        if job.payment_amount is None:
            raise HTTPException(status_code=409, detail="Job has no payment amount")

        dispute = service.file_dispute(
            job_id=req.job_id,
            client=str(job.client_id),
            provider=str(provider),
            amount=int(job.payment_amount),
            reason=req.reason,
            filed_by=filed_by,
            initial_evidence=req.initial_evidence,
        )

        return {"success": True, **dispute.to_dict()}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/evidence", summary="Submit evidence")
@rate_limit(rate=20, per=60)
def submit_evidence(request: Request, req: SubmitEvidenceRequest, user: AuthDep, session: SessionDep) -> dict[str, Any]:
    """Submit evidence for a dispute"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # The submitter is the authenticated caller — the service still
        # enforces membership in {client, provider} (#1333), now against the
        # caller's full identity set so a provider filing under a user sub
        # still matches the job's provider address (#1854).
        submitted_by = user["sub"]
        identities = _caller_identities(session, user)

        success = service.submit_evidence(
            dispute_id=req.dispute_id,
            submitted_by=submitted_by,
            evidence_type=req.evidence_type,
            description=req.description,
            ipfs_hash=req.ipfs_hash,
            caller_identities=identities,
        )

        return {"success": success, "dispute_id": req.dispute_id, "message": "Evidence submitted"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/vote", summary="Cast arbitrator vote")
@rate_limit(rate=20, per=60)
def cast_vote(request: Request, req: CastVoteRequest, user: AuthDep, session: SessionDep) -> dict[str, Any]:
    """Cast a vote as an arbitrator"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # The arbitrator is the authenticated caller — never a constant
        # (#1334). One vote per arbitrator now actually binds per identity.
        arbitrator = user["sub"]

        # Verify is arbitrator
        if not service.is_arbitrator(arbitrator):
            raise HTTPException(status_code=403, detail="Not a registered arbitrator")

        # The declared stake must be covered by the caller's ACTIVE on-chain
        # stake records — stake_amount is no longer caller-asserted (#1854).
        stake_total = _active_stake_total(session, _caller_identities(session, user))
        if Decimal(req.stake_amount) > stake_total:
            raise HTTPException(status_code=403, detail="stake_amount exceeds caller's active stake")

        success = service.cast_vote(
            dispute_id=req.dispute_id,
            arbitrator=arbitrator,
            outcome=req.outcome,
            reasoning=req.reasoning,
            stake_amount=req.stake_amount,
        )

        return {"success": success, "dispute_id": req.dispute_id, "arbitrator": arbitrator, "outcome": req.outcome}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/health", summary="Health check")
def disputes_health(request: Request) -> dict[str, Any]:
    """Check disputes service health.

    The service is process-local (``init_dispute_service`` wires it at
    startup); when it was never initialized every route below 503s, so
    health must say so instead of reporting a hardcoded zero.
    """
    service = get_dispute_service()
    if service is None:
        return {"status": "unhealthy", "active_disputes": 0, "service": "disputes"}
    active = [d for d in service.list_disputes() if d.status not in (DisputeStatus.resolved,)]
    return {"status": "healthy", "active_disputes": len(active), "service": "disputes"}


@router.get("/{dispute_id}", summary="Get dispute details")
def get_dispute(request: Request, dispute_id: str, user: AuthDep, session: SessionDep) -> dict[str, Any]:
    """Get details of a specific dispute.

    Non-admin callers may only read disputes they are a party to
    (client/provider/filed_by, matched against their full identity set);
    admins read all (#1854).
    """
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        dispute = service.get_dispute(dispute_id)
        if not dispute:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")
        if user.get("role") != "admin" and not _is_party(dispute, _caller_identities(session, user)):
            raise HTTPException(status_code=403, detail="Not a party to this dispute")

        return dispute.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/", summary="List disputes")
def list_disputes(
    request: Request, user: AuthDep, session: SessionDep, status: str | None = None, party: str | None = None
) -> dict[str, Any]:
    """List disputes with optional filters.

    Non-admin callers only see disputes they are a party to (#1854).
    """
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        disputes = service.list_disputes(status=status, party=party)
        if user.get("role") != "admin":
            identities = _caller_identities(session, user)
            disputes = [d for d in disputes if _is_party(d, identities)]

        return {
            "disputes": [d.to_dict() for d in disputes],
            "count": len(disputes),
            "filters": {"status": status, "party": party},
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/arbitrators/register", summary="Register as arbitrator")
@rate_limit(rate=20, per=60)
def register_arbitrator(request: Request, address: str, user: AuthDep, session: SessionDep) -> dict[str, Any]:
    """Register an address as an arbitrator.

    Callers may only register their own authenticated identity — the
    ``address`` parameter is retained for compatibility and must match
    the caller's subject (#1335). Registration additionally requires
    ACTIVE stake covering ``MIN_STAKE_AMOUNT`` on the caller's identities,
    so the arbitrator set cannot be self-minted by fresh accounts (#1854).

    Note (#1879): arbitrator stake is declarative weight, not escrowed —
    the same ACTIVE stake can back votes across unlimited disputes. The
    vote path bounds each vote's ``stake_amount`` by the caller's current
    active total, which is the enforced limit for this in-memory service;
    real escrow/slashing is out of scope until disputes move on-chain.
    """
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        if address != user["sub"]:
            raise HTTPException(status_code=403, detail="Can only register your own identity as arbitrator")
        stake_total = _active_stake_total(session, _caller_identities(session, user))
        if stake_total < Decimal(DisputeResolutionService.MIN_STAKE_AMOUNT):
            raise HTTPException(
                status_code=403,
                detail=f"Arbitrator registration requires active stake >= {DisputeResolutionService.MIN_STAKE_AMOUNT}",
            )
        success = service.register_arbitrator(user["sub"])

        return {"success": success, "address": address, "message": "Arbitrator registered"}

    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
