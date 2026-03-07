"""
Multi-tenant data models for AITBC coordinator
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, ClassVar
from enum import Enum
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, JSON, ForeignKey, Index, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from sqlmodel import SQLModel as Base, Field


class TenantStatus(Enum):
    """Tenant status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
    TRIAL = "trial"


class Tenant(Base):
    """Tenant model for multi-tenancy"""
    __tablename__ = "tenants"
    
    # Primary key
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Tenant information
    name: str = Field(max_length=255, nullable=False)
    slug: str = Field(max_length=100, unique=True, nullable=False)
    domain: Optional[str] = Field(max_length=255, unique=True, nullable=True)
    
    # Status and configuration
    status: str = Field(default=TenantStatus.PENDING.value, max_length=50)
    plan: str = Field(default="trial", max_length=50)
    
    # Contact information
    contact_email: str = Field(max_length=255, nullable=False)
    billing_email: Optional[str] = Field(max_length=255, nullable=True)
    
    # Configuration
    settings: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)
    activated_at: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None
    
    # Relationships
    users: ClassVar = relationship("TenantUser", back_populates="tenant", cascade="all, delete-orphan")
    quotas: ClassVar = relationship("TenantQuota", back_populates="tenant", cascade="all, delete-orphan")
    usage_records: ClassVar = relationship("UsageRecord", back_populates="tenant", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_tenant_status', 'status'),
        Index('idx_tenant_plan', 'plan'),
        {'schema': 'aitbc'}
    )


class TenantUser(Base):
    """Association between users and tenants"""
    __tablename__ = "tenant_users"
    
    # Primary key
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Foreign keys
    tenant_id: uuid.UUID = Field(foreign_key="aitbc.tenants.id", nullable=False)
    user_id: str = Field(max_length=255, nullable=False)  # User ID from auth system
    
    # Role and permissions
    role: str = Field(default="member", max_length=50)
    permissions: List[str] = Field(default_factory=list)
    
    # Status
    is_active: bool = Field(default=True)
    invited_at: Optional[datetime] = None
    joined_at: Optional[datetime] = None
    
    # Metadata
    user_metadata: Optional[Dict[str, Any]] = None
    
    # Relationships
    tenant: ClassVar = relationship("Tenant", back_populates="users")
    
    # Indexes
    __table_args__ = (
        Index('idx_tenant_user', 'tenant_id', 'user_id'),
        Index('idx_user_tenants', 'user_id'),
        {'schema': 'aitbc'}
    )


class TenantQuota(Base):
    """Resource quotas for tenants"""
    __tablename__ = "tenant_quotas"
    
    # Primary key
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="aitbc.tenants.id", nullable=False)
    
    # Quota definitions
    resource_type: str = Field(max_length=100, nullable=False)  # gpu_hours, storage_gb, api_calls
    limit_value: float = Field(nullable=False)  # Maximum allowed
    used_value: float = Field(default=0.0, nullable=False)  # Current usage
    
    # Time period
    period_type: str = Field(default="monthly", max_length=50)  # daily, weekly, monthly
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    
    # Status
    is_active: bool = Field(default=True)
    
    # Relationships
    tenant: ClassVar = relationship("Tenant", back_populates="quotas")
    
    # Indexes
    __table_args__ = (
        Index('idx_tenant_quota', 'tenant_id', 'resource_type', 'period_start'),
        Index('idx_quota_period', 'period_start', 'period_end'),
        {'schema': 'aitbc'}
    )


class UsageRecord(Base):
    """Usage tracking records for billing"""
    __tablename__ = "usage_records"
    
    # Primary key
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="aitbc.tenants.id", nullable=False)
    
    # Usage details
    resource_type: str = Field(max_length=100, nullable=False)  # gpu_hours, storage_gb, api_calls
    resource_id: Optional[str] = Field(max_length=255, nullable=True)  # Specific resource ID
    quantity: float = Field(nullable=False)
    unit: str = Field(max_length=50, nullable=False)  # hours, gb, calls
    
    # Cost information
    unit_price: float = Field(nullable=False)
    total_cost: float = Field(nullable=False)
    currency: str = Field(default="USD", max_length=10)
    
    # Time tracking
    usage_start: Optional[datetime] = None
    usage_end: Optional[datetime] = None
    recorded_at: Optional[datetime] = Field(default_factory=datetime.now)
    
    # Metadata
    job_id: Optional[str] = Field(max_length=255, nullable=True)  # Associated job if applicable
    usage_metadata: Optional[Dict[str, Any]] = None
    
    # Relationships
    tenant: ClassVar = relationship("Tenant", back_populates="usage_records")
    
    # Indexes
    __table_args__ = (
        Index('idx_tenant_usage', 'tenant_id', 'usage_start'),
        Index('idx_usage_type', 'resource_type', 'usage_start'),
        Index('idx_usage_job', 'job_id'),
        {'schema': 'aitbc'}
    )


class Invoice(Base):
    """Billing invoices for tenants"""
    __tablename__ = "invoices"
    
    # Primary key
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="aitbc.tenants.id", nullable=False)
    
    # Invoice details
    invoice_number: str = Field(max_length=100, unique=True, nullable=False)
    status: str = Field(default="draft", max_length=50)
    
    # Period
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    due_date: Optional[datetime] = None
    
    # Amounts
    subtotal: float = Field(nullable=False)
    tax_amount: float = Field(default=0.0, nullable=False)
    total_amount: float = Field(nullable=False)
    currency: str = Field(default="USD", max_length=10)
    
    # Breakdown
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Payment
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = Field(max_length=100, nullable=True)
    
    # Timestamps
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)
    
    # Metadata
    invoice_metadata: Optional[Dict[str, Any]] = None
    
    # Indexes
    __table_args__ = (
        Index('idx_invoice_tenant', 'tenant_id', 'period_start'),
        Index('idx_invoice_status', 'status'),
        Index('idx_invoice_due', 'due_date'),
        {'schema': 'aitbc'}
    )


class TenantApiKey(Base):
    """API keys for tenant authentication"""
    __tablename__ = "tenant_api_keys"
    
    # Primary key
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="aitbc.tenants.id", nullable=False)
    
    # Key details
    key_id: str = Field(max_length=100, unique=True, nullable=False)
    key_hash: str = Field(max_length=255, unique=True, nullable=False)
    key_prefix: str = Field(max_length=20, nullable=False)  # First few characters for identification
    
    # Permissions and restrictions
    permissions: List[str] = Field(default_factory=list)
    rate_limit: Optional[int] = None  # Requests per minute
    allowed_ips: Optional[List[str]] = None  # IP whitelist
    
    # Status
    is_active: bool = Field(default=True)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    
    # Metadata
    name: str = Field(max_length=255, nullable=False)
    description: Optional[str] = None
    created_by: str = Field(max_length=255, nullable=False)
    
    # Timestamps
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    revoked_at: Optional[datetime] = None
    
    # Indexes
    __table_args__ = (
        Index('idx_api_key_tenant', 'tenant_id', 'is_active'),
        Index('idx_api_key_hash', 'key_hash'),
        {'schema': 'aitbc'}
    )


class TenantAuditLog(Base):
    """Audit logs for tenant activities"""
    __tablename__ = "tenant_audit_logs"
    
    # Primary key
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="aitbc.tenants.id", nullable=False)
    
    # Event details
    event_type: str = Field(max_length=100, nullable=False)
    event_category: str = Field(max_length=50, nullable=False)
    actor_id: str = Field(max_length=255, nullable=False)  # User who performed action
    actor_type: str = Field(max_length=50, nullable=False)  # user, api_key, system
    
    # Target information
    resource_type: str = Field(max_length=100, nullable=False)
    resource_id: Optional[str] = Field(max_length=255, nullable=True)
    
    # Event data
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    event_metadata: Optional[Dict[str, Any]] = None
    
    # Request context
    ip_address: Optional[str] = Field(max_length=45, nullable=True)
    user_agent: Optional[str] = None
    api_key_id: Optional[str] = Field(max_length=100, nullable=True)
    
    # Timestamp
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    
    # Indexes
    __table_args__ = (
        Index('idx_audit_tenant', 'tenant_id', 'created_at'),
        Index('idx_audit_actor', 'actor_id', 'event_type'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
        {'schema': 'aitbc'}
    )


class TenantMetric(Base):
    """Tenant-specific metrics and monitoring data"""
    __tablename__ = "tenant_metrics"
    
    # Primary key
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Foreign key
    tenant_id: uuid.UUID = Field(foreign_key="aitbc.tenants.id", nullable=False)
    
    # Metric details
    metric_name: str = Field(max_length=100, nullable=False)
    metric_type: str = Field(max_length=50, nullable=False)  # counter, gauge, histogram
    
    # Value
    value: float = Field(nullable=False)
    unit: Optional[str] = Field(max_length=50, nullable=True)
    
    # Dimensions
    dimensions: Dict[str, Any] = Field(default_factory=dict)
    
    # Time
    timestamp: Optional[datetime] = None
    
    # Indexes
    __table_args__ = (
        Index('idx_metric_tenant', 'tenant_id', 'metric_name', 'timestamp'),
        Index('idx_metric_time', 'timestamp'),
        {'schema': 'aitbc'}
    )
