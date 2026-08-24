"""Provider-bond eligibility mapping for the marketplace."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column, text
from sqlmodel import Field, Session, SQLModel, select


class ProviderBondStatus(StrEnum):
    """Lifecycle status of a provider's required performance bond."""

    PENDING = "pending"
    ACTIVE = "active"
    LOCKED = "locked"
    SHORTFALL = "shortfall"
    LIQUIDATED = "liquidated"
    RELEASED = "released"


class ProviderBond(SQLModel, table=True):
    """Bond record that maps a provider to its current bond status."""

    __tablename__ = "provider_bond"
    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: f"pb_{uuid4().hex[:10]}",
        max_length=32,
        primary_key=True,
    )
    provider_id: str = Field(default="", max_length=255, index=True)
    bond_id: str = Field(default="", max_length=255, index=True)
    status: str = Field(default=ProviderBondStatus.PENDING.value, max_length=20, index=True)
    amount: Decimal = Field(default=Decimal("0.0"), max_digits=20, decimal_places=8)
    required_amount: Decimal = Field(default=Decimal("0.0"), max_digits=20, decimal_places=8)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


def _default_bond_min_amount() -> Decimal:
    """Global floor for provider-bond eligibility."""
    return Decimal(os.getenv("COORDINATOR_BOND_MIN_AMOUNT", "1"))


def is_provider_eligible(
    session: Session,
    provider_id: str,
    min_amount: Decimal | None = None,
) -> bool:
    """Return True if the provider has an active/locked bond that meets the floor.

    If ``min_amount`` is not supplied, the provider's own ``required_amount`` is
    used when set, otherwise the global ``COORDINATOR_BOND_MIN_AMOUNT`` floor.
    """
    statement = select(ProviderBond).where(ProviderBond.provider_id == provider_id)
    bond = session.exec(statement).first()
    if bond is None:
        return False
    if bond.status not in {ProviderBondStatus.ACTIVE.value, ProviderBondStatus.LOCKED.value}:
        return False
    if min_amount is None:
        if bond.required_amount and bond.required_amount > 0:
            min_amount = bond.required_amount
        else:
            min_amount = _default_bond_min_amount()
    return bond.amount >= min_amount


def set_provider_bond_status(
    session: Session,
    provider_id: str,
    status: ProviderBondStatus,
    amount: Decimal | None = None,
    required_amount: Decimal | None = None,
    bond_id: str = "",
) -> ProviderBond:
    """Upsert the bond status for a provider.

    ``amount`` and ``required_amount`` are preserved when not explicitly
    supplied, so lock/release/slash operations do not accidentally zero the bond.
    """
    statement = select(ProviderBond).where(ProviderBond.provider_id == provider_id)
    bond = session.exec(statement).first()
    if bond is None:
        bond = ProviderBond(provider_id=provider_id)
        session.add(bond)
    bond.status = status.value if isinstance(status, ProviderBondStatus) else status
    if amount is not None:
        bond.amount = amount
    if required_amount is not None:
        bond.required_amount = required_amount
    if bond_id:
        bond.bond_id = bond_id
    bond.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(bond)
    return bond
