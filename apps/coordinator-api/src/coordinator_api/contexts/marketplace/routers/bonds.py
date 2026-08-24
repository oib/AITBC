"""Coordinator API router for provider performance bonds."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from ....auth import require_auth
from ....storage import get_session
from ..domain.provider_bond import (
    ProviderBond,
    ProviderBondStatus,
    _default_bond_min_amount,
    is_provider_eligible,
    set_provider_bond_status,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/marketplace", tags=["marketplace-bonds"])


class BondCreate(BaseModel):
    bond_id: str = Field(default_factory=lambda: "")
    amount: str | int | Decimal = Field(default="0.0")
    required_amount: str | int | Decimal = Field(default="0.0")


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
async def create_bond(
    request: Request,
    provider_id: str,
    body: BondCreate,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Create or top-up a provider performance bond record.

    The bond's ``required_amount`` is raised to the global floor if the caller
    supplies a smaller value, and the bond is left ``PENDING`` until the posted
    ``amount`` meets that floor.
    """
    amount = _to_decimal(body.amount)
    required_amount = _to_decimal(body.required_amount)
    floor = _default_bond_min_amount()
    if required_amount < floor:
        required_amount = floor
    status = ProviderBondStatus.ACTIVE if amount >= required_amount else ProviderBondStatus.PENDING
    bond = set_provider_bond_status(
        session,
        provider_id,
        status,
        amount=amount,
        required_amount=required_amount,
        bond_id=body.bond_id or f"bond-{provider_id}",
    )
    return _bond_response(bond)


@router.get("/providers/{provider_id}/eligibility", summary="Check provider bond eligibility")
async def get_eligibility(
    request: Request,
    provider_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondStatusResponse:
    """Return whether a provider is eligible for high-value jobs."""
    statement = select(ProviderBond).where(ProviderBond.provider_id == provider_id)
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
async def get_bond_by_id(
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
async def lock_bond(
    request: Request,
    provider_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Lock a provider's bond while a high-value job is in flight."""
    bond = set_provider_bond_status(session, provider_id, ProviderBondStatus.LOCKED)
    return _bond_response(bond)


@router.post("/providers/{provider_id}/bonds/release", summary="Release a locked provider bond")
async def release_bond(
    request: Request,
    provider_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Release a locked bond back to active status."""
    bond = set_provider_bond_status(session, provider_id, ProviderBondStatus.ACTIVE)
    return _bond_response(bond)


@router.post("/providers/{provider_id}/bonds/slash", summary="Slash a provider bond")
async def slash_bond(
    request: Request,
    provider_id: str,
    body: BondAction,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> BondResponse:
    """Slash a provider's bond for misbehavior."""
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
