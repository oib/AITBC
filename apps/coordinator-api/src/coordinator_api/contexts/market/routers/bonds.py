"""Coordinator API router for provider performance bonds."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError
from aitbc.rate_limiting import rate_limit
from aitbc.utils.units import units_to_ait
from ....auth import require_auth
from ....storage import get_session
from ....utils.ownership import caller_identities, is_admin
from ...blockchain.services.blockchain import BlockchainService
from ..domain.provider_bond import (
    ProviderBond,
    ProviderBondStatus,
    _default_bond_min_amount,
    is_provider_eligible,
    reconcile_provider_bond,
    set_provider_bond_status,
)
from ...infrastructure.domain.miner import Miner
from ...payments.provider_binding import miner_wallet_address
from ..services.bond_wallet_proof import issue_bond_challenge, verify_bond_wallet_proof
from aitbc.crypto.signature_recovery import canonical_address

logger = get_logger(__name__)
router = APIRouter(prefix="/market", tags=["market-bonds"])


class BondCreate(BaseModel):
    bond_id: str = Field(default_factory=lambda: "")
    amount: str | int | Decimal = Field(default="0.0")
    required_amount: str | int | Decimal = Field(default="0.0")
    # #1967: proof that the caller controls the provider's registered wallet.
    # Issued by POST .../bonds/challenge; single-use, 300s TTL.
    challenge_nonce: str = Field(default="")
    wallet_signature: str = Field(default="")


class BondChallengeResponse(BaseModel):
    nonce: str
    message: str
    wallet_address: str
    expires_in: int


class BondResponse(BaseModel):
    id: str
    provider_id: str
    bond_id: str | None = None
    status: str
    amount: str
    required_amount: str
    meta: dict[str, Any]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class BondStatusResponse(BaseModel):
    provider_id: str
    eligible: bool
    status: str
    amount: str
    required_amount: str
    bond_id: str | None = None


class BondAction(BaseModel):
    reason: str | None = None


def _provider_accessible(session: Session, user: dict[str, Any], provider_id: str) -> bool:
    """Whether the caller may act on ``provider_id``'s bond (#1881).

    provider_id is a Miner.id: a miner-role JWT carries it as ``sub``; a
    wallet-authenticated operator matches through the miner's registered
    payout wallet or their own wallets. Admin bypasses; everything else
    fails closed.
    """
    if is_admin(user):
        return True
    identities = caller_identities(session, user)
    if str(provider_id).lower() in identities:
        return True
    miner = session.get(Miner, provider_id)
    wallet = miner_wallet_address(miner) if miner is not None else None
    if not wallet:
        return False
    return canonical_address(wallet).lower() in identities


def _require_provider_access(session: Session, user: dict[str, Any], provider_id: str) -> None:
    if not _provider_accessible(session, user, provider_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the provider owner")


def _to_decimal(value: str | float | int | Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _bond_response(bond: ProviderBond) -> BondResponse:
    return BondResponse(
        id=bond.id,
        provider_id=bond.provider_id,
        bond_id=bond.bond_id or None,
        status=bond.status,
        amount=str(bond.amount),
        required_amount=str(bond.required_amount),
        meta=bond.meta or {},
        created_at=bond.created_at.isoformat() if bond.created_at else "",
        updated_at=bond.updated_at.isoformat() if bond.updated_at else "",
    )


@router.post("/providers/{provider_id}/bonds", summary="Create or update a provider bond")
@rate_limit(rate=20, per=60)
def create_bond(
    request: Request,
    provider_id: str,
    body: BondCreate,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Create or top-up a provider performance bond record.

    #1915: the record is a projection of VERIFIED chain state, not a
    self-declaration. ``bond_id`` must name an ``active`` on-chain bond the
    chain attributes to the provider's registered wallet; ``amount`` and
    ``status`` derive from that chain record (the body's ``amount`` is
    ignored). ``required_amount`` is raised to the global floor if the
    caller supplies a smaller value, and the bond is left ``PENDING`` until
    the chain-verified amount meets that floor.

    #1967: non-admin callers must also prove control of the provider's
    registered wallet — ``challenge_nonce`` + ``wallet_signature`` from
    ``POST .../bonds/challenge`` — and a ``bond_id`` may back only one
    provider (409 on a cross-provider claim).
    """
    _require_provider_access(session, user, provider_id)
    bond_id = (body.bond_id or "").strip()
    if not bond_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bond_id is required: bonds activate only from a verified on-chain BOND_LOCK record",
        )
    miner = session.get(Miner, provider_id)
    wallet = miner_wallet_address(miner) if miner is not None else None
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="provider has no registered wallet address; cannot bind an on-chain bond",
        )
    # #1967: the registered wallet is self-declared at miner registration —
    # prove key control before letting it claim an on-chain bond. Admin
    # bypasses, matching _require_provider_access; everyone else must post a
    # fresh single-use challenge signature.
    if not is_admin(user) and not verify_bond_wallet_proof(provider_id, wallet, body.challenge_nonce, body.wallet_signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid or expired bond wallet proof: request a challenge and sign it with the provider wallet",
        )
    # #1967: a chain bond_id may back exactly one provider — otherwise two
    # miners could share one on-chain bond. "" stays allowed: bondless
    # lock/release rows use it.
    claimed = session.exec(
        select(ProviderBond).where(
            ProviderBond.bond_id == bond_id,
            ProviderBond.provider_id != provider_id,
        )
    ).first()
    if claimed is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"bond {bond_id} is already bound to provider {claimed.provider_id}",
        )
    try:
        chain = BlockchainService().list_provider_bonds(wallet)
    except AITBCError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"could not verify bond {bond_id} against chain state",
        ) from e
    entry = next((b for b in chain.get("bonds", []) if str(b.get("bond_id")) == bond_id), None)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"bond {bond_id} is not an on-chain bond of this provider",
        )
    if entry.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"on-chain bond {bond_id} is {entry.get('status')}, not active",
        )
    amount = units_to_ait(int(entry.get("amount") or 0))
    required_amount = _to_decimal(body.required_amount)
    floor = _default_bond_min_amount()
    if required_amount < floor:
        required_amount = floor
    bond_status = ProviderBondStatus.ACTIVE if amount >= required_amount else ProviderBondStatus.PENDING
    try:
        bond = set_provider_bond_status(
            session,
            provider_id,
            bond_status,
            amount=amount,
            required_amount=required_amount,
            bond_id=bond_id,
        )
    except IntegrityError as e:
        # #1967: the partial unique index on bond_id is the race-safe backstop
        # for the pre-check above — two concurrent creates for different
        # providers must not both land.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"bond {bond_id} is already bound to another provider",
        ) from e
    bond.meta = {
        **(bond.meta or {}),
        "chain_bond_id": bond_id,
        "chain_provider": wallet,
        "chain_amount_units": int(entry.get("amount") or 0),
        "chain_status": entry.get("status"),
        "verified_at": datetime.now(UTC).isoformat(),
    }
    session.add(bond)
    session.commit()
    session.refresh(bond)
    return _bond_response(bond)


@router.post("/providers/{provider_id}/bonds/challenge", summary="Issue a bond wallet-ownership challenge")
@rate_limit(rate=20, per=60)
def create_bond_challenge(
    request: Request,
    provider_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondChallengeResponse:
    """Issue a single-use nonce the provider wallet must sign (#1967).

    Returns the canonical message to sign; post the nonce and resulting
    EIP-191 signature as ``challenge_nonce``/``wallet_signature`` on
    ``POST .../bonds``. The nonce is bound to this provider and its
    registered wallet, expires after 300s, and burns on first use.
    """
    _require_provider_access(session, user, provider_id)
    miner = session.get(Miner, provider_id)
    wallet = miner_wallet_address(miner) if miner is not None else None
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="provider has no registered wallet address; cannot bind an on-chain bond",
        )
    try:
        challenge = issue_bond_challenge(provider_id, wallet)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e)) from e
    return BondChallengeResponse(**challenge)


@router.get("/providers/{provider_id}/eligibility", summary="Check provider bond eligibility")
def get_eligibility(
    request: Request,
    provider_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondStatusResponse:
    """Return whether a provider is eligible for high-value jobs."""
    statement = select(ProviderBond).where(ProviderBond.provider_id == provider_id)
    bond = session.exec(statement).first()
    if bond is not None:
        # #1926: best-effort chain refresh — this is a read path, not a
        # money-moving decision, so the local answer stands when the chain
        # can't be consulted.
        reconcile_provider_bond(session, provider_id)
        bond = session.exec(statement).first()
    if bond is None:
        return BondStatusResponse(
            provider_id=provider_id,
            eligible=False,
            status=ProviderBondStatus.PENDING.value,
            amount="0",
            required_amount="0",
            bond_id=None,
        )
    return BondStatusResponse(
        provider_id=provider_id,
        eligible=is_provider_eligible(session, provider_id),
        status=bond.status,
        amount=str(bond.amount),
        required_amount=str(bond.required_amount),
        bond_id=bond.bond_id or None,
    )


@router.get("/bonds/{bond_id}", summary="Get a bond record by ID")
def get_bond_by_id(
    request: Request,
    bond_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Return a single bond record."""
    bond = session.get(ProviderBond, bond_id)
    if bond is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bond not found")
    return _bond_response(bond)


@router.post("/providers/{provider_id}/bonds/lock", summary="Lock a provider bond")
@rate_limit(rate=20, per=60)
def lock_bond(
    request: Request,
    provider_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Lock a provider's bond while a high-value job is in flight."""
    _require_provider_access(session, user, provider_id)
    bond = set_provider_bond_status(session, provider_id, ProviderBondStatus.LOCKED)
    return _bond_response(bond)


@router.post("/providers/{provider_id}/bonds/release", summary="Release a locked provider bond")
@rate_limit(rate=20, per=60)
def release_bond(
    request: Request,
    provider_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Release a locked bond back to active status."""
    _require_provider_access(session, user, provider_id)
    bond = set_provider_bond_status(session, provider_id, ProviderBondStatus.ACTIVE)
    return _bond_response(bond)


@router.post("/providers/{provider_id}/bonds/slash", summary="Slash a provider bond")
@rate_limit(rate=20, per=60)
def slash_bond(
    request: Request,
    provider_id: str,
    body: BondAction,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Slash a provider's bond for misbehavior."""
    _require_provider_access(session, user, provider_id)
    bond = set_provider_bond_status(
        session,
        provider_id,
        ProviderBondStatus.LIQUIDATED,
    )
    if body.reason:
        bond.meta = {**(bond.meta or {}), "slash_reason": body.reason, "slashed_by": user.get("sub", "unknown")}
        session.add(bond)
        session.commit()
        session.refresh(bond)
    return _bond_response(bond)
