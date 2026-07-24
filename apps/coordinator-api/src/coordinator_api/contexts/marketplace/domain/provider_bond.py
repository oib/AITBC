"""Provider-bond eligibility mapping for the marketplace."""

from __future__ import annotations

from datetime import UTC, datetime
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
    amount: float = Field(default=0.0)
    required_amount: float = Field(default=0.0)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


def is_provider_eligible(session: Session, provider_id: str) -> bool:
    """Return True if the provider has an active or locked bond and no shortfall."""
    statement = select(ProviderBond).where(ProviderBond.provider_id == provider_id)
    bond = session.exec(statement).first()
    if bond is None:
        return False
    return bond.status in {ProviderBondStatus.ACTIVE.value, ProviderBondStatus.LOCKED.value}


def set_provider_bond_status(
    session: Session,
    provider_id: str,
    status: ProviderBondStatus,
    amount: float = 0.0,
    required_amount: float = 0.0,
    bond_id: str = "",
) -> ProviderBond:
    """Upsert the bond status for a provider."""
    statement = select(ProviderBond).where(ProviderBond.provider_id == provider_id)
    bond = session.exec(statement).first()
    if bond is None:
        bond = ProviderBond(provider_id=provider_id)
        session.add(bond)
    bond.status = status.value if isinstance(status, ProviderBondStatus) else status
    bond.amount = amount
    bond.required_amount = required_amount
    bond.bond_id = bond_id
    bond.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(bond)
    return bond
