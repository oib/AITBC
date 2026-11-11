"""
Multi-tenant data models for AITBC coordinator
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar

from sqlalchemy import Column, Index, JSON
from sqlalchemy.orm import relationship
from sqlmodel import Field
from sqlmodel import SQLModel as Base


class TenantStatus(Enum):
    """Tenant status enumeration"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
    TRIAL = "trial"


class Tenant(Base, table=True):
    """Tenant model for multi-tenancy"""

    __tablename__ = "tenants"

    # Primary key
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)

    # Tenant information
    name: str = Field(max_length=255, nullable=False)
    slug: str = Field(max_length=100, unique=True, nullable=False)
    domain: str | None = Field(max_length=255, unique=True, nullable=True)

    # Status and configuration
    status: str = Field(default=TenantStatus.PENDING.value, max_length=50)
    plan: str = Field(default="trial", max_length=50)

    # Contact information
    contact_email: str = Field(max_length=255, nullable=False)
    billing_email: str | None = Field(max_length=255, nullable=True)

    # Configuration
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    features: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime | None = Field(default_factory=datetime.now)
    updated_at: datetime | None = Field(default_factory=datetime.now)
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None

    # Relationships
    quotas: ClassVar = relationship("TenantQuota", back_populates="tenant", cascade="all, delete-orphan")
    usage_records: ClassVar = relationship("UsageRecord", back_populates="tenant", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (Index("idx_tenant_status", "status"), Index("idx_tenant_plan", "plan"))


class TenantQuota(Base, table=True):
    """Resource quotas for tenants"""

    __tablename__ = "tenant_quotas"

    # Primary key
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)

    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)

    # Quota definitions
    resource_type: str = Field(max_length=100, nullable=False)  # gpu_hours, storage_gb, api_calls
    limit_value: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)  # Maximum allowed
    used_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=8, nullable=False)  # Current usage

    # Time period
    period_type: str = Field(default="monthly", max_length=50)  # daily, weekly, monthly
    period_start: datetime | None = None
    period_end: datetime | None = None

    # Status
    is_active: bool = Field(default=True)

    # Relationships
    tenant: ClassVar = relationship("Tenant", back_populates="quotas")

    # Indexes
    __table_args__ = (
        Index("idx_tenant_quota", "tenant_id", "resource_type", "period_start"),
        Index("idx_quota_period", "period_start", "period_end"),
    )


class UsageRecord(Base, table=True):
    """Usage tracking records for billing"""

    __tablename__ = "usage_records"

    # Primary key
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)

    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)

    # Usage details
    resource_type: str = Field(max_length=100, nullable=False)  # gpu_hours, storage_gb, api_calls
    resource_id: str | None = Field(max_length=255, nullable=True)  # Specific resource ID
    quantity: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)
    unit: str = Field(max_length=50, nullable=False)  # hours, gb, calls

    # Cost information
    unit_price: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)
    total_cost: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)
    currency: str = Field(default="USD", max_length=10)

    # Time tracking
    usage_start: datetime | None = None
    usage_end: datetime | None = None
    recorded_at: datetime | None = Field(default_factory=datetime.now)

    # Metadata
    job_id: str | None = Field(max_length=255, nullable=True)  # Associated job if applicable
    usage_metadata: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    # Relationships
    tenant: ClassVar = relationship("Tenant", back_populates="usage_records")

    # Indexes
    __table_args__ = (
        Index("idx_tenant_usage", "tenant_id", "usage_start"),
        Index("idx_usage_type", "resource_type", "usage_start"),
        Index("idx_usage_job", "job_id"),
    )


class Invoice(Base, table=True):
    """Billing invoices for tenants"""

    __tablename__ = "invoices"

    # Primary key
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)

    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)

    # Invoice details
    invoice_number: str = Field(max_length=100, unique=True, nullable=False)
    status: str = Field(default="draft", max_length=50)

    # Period
    period_start: datetime | None = None
    period_end: datetime | None = None
    due_date: datetime | None = None

    # Amounts
    subtotal: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)
    tax_amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=8, nullable=False)
    total_amount: Decimal = Field(max_digits=18, decimal_places=8, nullable=False)
    currency: str = Field(default="USD", max_length=10)

    # Breakdown
    line_items: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))

    # Payment
    paid_at: datetime | None = None
    payment_method: str | None = Field(max_length=100, nullable=True)

    # Timestamps
    created_at: datetime | None = Field(default_factory=datetime.now)
    updated_at: datetime | None = Field(default_factory=datetime.now)

    # Metadata
    invoice_metadata: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    # Indexes
    __table_args__ = (
        Index("idx_invoice_tenant", "tenant_id", "period_start"),
        Index("idx_invoice_status", "status"),
        Index("idx_invoice_due", "due_date"),
    )
