"""
Multi-tenant data models for AITBC coordinator
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, JSON, ForeignKey, Index, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Tenant information
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    domain = Column(String(255), unique=True, nullable=True, index=True)
    
    # Status and configuration
    status = Column(String(50), nullable=False, default=TenantStatus.PENDING.value)
    plan = Column(String(50), nullable=False, default="trial")
    
    # Contact information
    contact_email = Column(String(255), nullable=False)
    billing_email = Column(String(255), nullable=True)
    
    # Configuration
    settings = Column(JSON, nullable=False, default={})
    features = Column(JSON, nullable=False, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    users = relationship("TenantUser", back_populates="tenant", cascade="all, delete-orphan")
    quotas = relationship("TenantQuota", back_populates="tenant", cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="tenant", cascade="all, delete-orphan")
    
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('aitbc.tenants.id'), nullable=False)
    user_id = Column(String(255), nullable=False)  # User ID from auth system
    
    # Role and permissions
    role = Column(String(50), nullable=False, default="member")
    permissions = Column(JSON, nullable=False, default=[])
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    invited_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    metadata = Column(JSON, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('aitbc.tenants.id'), nullable=False)
    
    # Quota definitions
    resource_type = Column(String(100), nullable=False)  # gpu_hours, storage_gb, api_calls
    limit_value = Column(Numeric(20, 4), nullable=False)  # Maximum allowed
    used_value = Column(Numeric(20, 4), nullable=False, default=0)  # Current usage
    
    # Time period
    period_type = Column(String(50), nullable=False, default="monthly")  # daily, weekly, monthly
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="quotas")
    
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('aitbc.tenants.id'), nullable=False)
    
    # Usage details
    resource_type = Column(String(100), nullable=False)  # gpu_hours, storage_gb, api_calls
    resource_id = Column(String(255), nullable=True)  # Specific resource ID
    quantity = Column(Numeric(20, 4), nullable=False)
    unit = Column(String(50), nullable=False)  # hours, gb, calls
    
    # Cost information
    unit_price = Column(Numeric(10, 4), nullable=False)
    total_cost = Column(Numeric(20, 4), nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    
    # Time tracking
    usage_start = Column(DateTime(timezone=True), nullable=False)
    usage_end = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Metadata
    job_id = Column(String(255), nullable=True)  # Associated job if applicable
    metadata = Column(JSON, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="usage_records")
    
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('aitbc.tenants.id'), nullable=False)
    
    # Invoice details
    invoice_number = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(50), nullable=False, default="draft")
    
    # Period
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=False)
    
    # Amounts
    subtotal = Column(Numeric(20, 4), nullable=False)
    tax_amount = Column(Numeric(20, 4), nullable=False, default=0)
    total_amount = Column(Numeric(20, 4), nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    
    # Breakdown
    line_items = Column(JSON, nullable=False, default=[])
    
    # Payment
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_method = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Metadata
    metadata = Column(JSON, nullable=True)
    
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('aitbc.tenants.id'), nullable=False)
    
    # Key details
    key_id = Column(String(100), unique=True, nullable=False, index=True)
    key_hash = Column(String(255), unique=True, nullable=False, index=True)
    key_prefix = Column(String(20), nullable=False)  # First few characters for identification
    
    # Permissions and restrictions
    permissions = Column(JSON, nullable=False, default=[])
    rate_limit = Column(Integer, nullable=True)  # Requests per minute
    allowed_ips = Column(JSON, nullable=True)  # IP whitelist
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(String(255), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('aitbc.tenants.id'), nullable=False)
    
    # Event details
    event_type = Column(String(100), nullable=False, index=True)
    event_category = Column(String(50), nullable=False, index=True)
    actor_id = Column(String(255), nullable=False)  # User who performed action
    actor_type = Column(String(50), nullable=False)  # user, api_key, system
    
    # Target information
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(255), nullable=True)
    
    # Event data
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    metadata = Column(JSON, nullable=True)
    
    # Request context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    api_key_id = Column(String(100), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('aitbc.tenants.id'), nullable=False)
    
    # Metric details
    metric_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # counter, gauge, histogram
    
    # Value
    value = Column(Numeric(20, 4), nullable=False)
    unit = Column(String(50), nullable=True)
    
    # Dimensions
    dimensions = Column(JSON, nullable=False, default={})
    
    # Time
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_metric_tenant', 'tenant_id', 'metric_name', 'timestamp'),
        Index('idx_metric_time', 'timestamp'),
        {'schema': 'aitbc'}
    )
