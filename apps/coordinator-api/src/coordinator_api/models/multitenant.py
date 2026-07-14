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
    users: ClassVar = relationship("TenantUser", back_populates="tenant", cascade="all, delete-orphan")
    quotas: ClassVar = relationship("TenantQuota", back_populates="tenant", cascade="all, delete-orphan")
    usage_records: ClassVar = relationship("UsageRecord", back_populates="tenant", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (Index("idx_tenant_status", "status"), Index("idx_tenant_plan", "plan"))


class TenantUser(Base, table=True):
    """Association between users and tenants"""

    __tablename__ = "tenant_users"

    # Primary key
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)

    # Foreign keys
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)
    user_id: str = Field(max_length=255, nullable=False)  # User ID from auth system

    # Role and permissions
    role: str = Field(default="member", max_length=50)
    permissions: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Status
    is_active: bool = Field(default=True)
    invited_at: datetime | None = None
    joined_at: datetime | None = None

    # Metadata
    user_metadata: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    # Relationships
    tenant: ClassVar = relationship("Tenant", back_populates="users")

    # Indexes
    __table_args__ = (
        Index("idx_tenant_user", "tenant_id", "user_id"),
        Index("idx_user_tenants", "user_id"),
    )


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


class TenantApiKey(Base, table=True):
    """API keys for tenant authentication"""

    __tablename__ = "tenant_api_keys"

    # Primary key
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)

    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)

    # Key details
    key_id: str = Field(max_length=100, unique=True, nullable=False)
    key_hash: str = Field(max_length=255, unique=True, nullable=False)
    key_prefix: str = Field(max_length=20, nullable=False)  # First few characters for identification

    # Permissions and restrictions
    permissions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    rate_limit: int | None = None  # Requests per minute
    allowed_ips: list[str] | None = Field(default=None, sa_column=Column(JSON))  # IP whitelist

    # Status
    is_active: bool = Field(default=True)
    expires_at: datetime | None = None
    last_used_at: datetime | None = None

    # Metadata
    name: str = Field(max_length=255, nullable=False)
    description: str | None = None
    created_by: str = Field(max_length=255, nullable=False)

    # Timestamps
    created_at: datetime | None = Field(default_factory=datetime.now)
    revoked_at: datetime | None = None

    # Indexes
    __table_args__ = (
        Index("idx_api_key_tenant", "tenant_id", "is_active"),
        Index("idx_api_key_hash", "key_hash"),
    )


class TenantAuditLog(Base, table=True):
    """Audit logs for tenant activities"""

    __tablename__ = "tenant_audit_logs"

    # Primary key
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)

    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)

    # Event details
    event_type: str = Field(max_length=100, nullable=False)
    event_category: str = Field(max_length=50, nullable=False)
    actor_id: str = Field(max_length=255, nullable=False)  # User who performed action
    actor_type: str = Field(max_length=50, nullable=False)  # user, api_key, system

    # Target information
    resource_type: str = Field(max_length=100, nullable=False)
    resource_id: str | None = Field(max_length=255, nullable=True)

    # Event data
    old_values: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    new_values: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    event_metadata: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    # Request context
    ip_address: str | None = Field(max_length=45, nullable=True)
    user_agent: str | None = None
    api_key_id: str | None = Field(max_length=100, nullable=True)

    # Timestamp
    created_at: datetime | None = Field(default_factory=datetime.now)

    # Indexes
    __table_args__ = (
        Index("idx_audit_tenant", "tenant_id", "created_at"),
        Index("idx_audit_actor", "actor_id", "event_type"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )


class TenantMetric(Base, table=True):
    """Tenant-specific metrics and monitoring data"""

    __tablename__ = "tenant_metrics"

    # Primary key
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)

    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)

    # Metric details
    metric_name: str = Field(max_length=100, nullable=False)
    metric_type: str = Field(max_length=50, nullable=False)  # counter, gauge, histogram

    # Value
    value: float = Field(nullable=False)
    unit: str | None = Field(max_length=50, nullable=True)

    # Dimensions
    dimensions: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Time
    timestamp: datetime | None = None

    # Indexes
    __table_args__ = (
        Index("idx_metric_tenant", "tenant_id", "metric_name", "timestamp"),
        Index("idx_metric_time", "timestamp"),
    )
