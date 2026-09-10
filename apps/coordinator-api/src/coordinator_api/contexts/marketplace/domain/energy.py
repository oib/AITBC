"""Native (non-EVM) energy pricing tables for AITBC GPU rentals.

These store operator-attested energy profiles and the global AIT/EUR rate in the
coordinator database so fixed-duration GPU quotes can be built on the native AIT
settlement rail without relying on an EVM testnet.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class NativeEnergyProfile(SQLModel, table=True):
    """Operator-attested energy profile for a GPU resource."""

    __tablename__ = "native_energy_profiles"
    __table_args__ = {"extend_existing": True}

    resource_id: str = Field(primary_key=True)
    provider: str = Field(index=True)
    model_id: str = Field(index=True)
    tdp_watts: int = Field(gt=0)
    eur_per_kwh_scaled: int = Field(gt=0)
    enabled: bool = Field(default=True)
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class NativeEnergyRate(SQLModel, table=True):
    """Global AIT/EUR rate used for native energy quotes."""

    __tablename__ = "native_energy_rates"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=1, primary_key=True)
    ait_per_eur_scaled: int = Field(gt=0)
    version: int = Field(default=1, ge=1)
    observed_at: int = Field(default=0)
    submitted_at: int = Field(default=0)
    source_kind: str = Field(default="native_operator")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
