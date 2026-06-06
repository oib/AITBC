"""Database models for Hermes autonomy features (SQLite compatible)."""

from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class DecisionModel(Base):
    """Database model for decision proposals."""
    __tablename__ = "hermes_decisions"

    id = Column(String, primary_key=True)
    decision_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    proposed_by = Column(String, nullable=False, index=True)
    voting_deadline = Column(DateTime, nullable=False)
    min_participation = Column(Float, default=0.5)
    required_approval = Column(Float, default=0.6)
    status = Column(String, default="pending", index=True)
    meta_data = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    concluded_at = Column(DateTime, nullable=True)


class VoteModel(Base):
    """Database model for votes on decisions."""
    __tablename__ = "hermes_votes"

    id = Column(String, primary_key=True)
    decision_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False, index=True)
    vote = Column(String, nullable=False)  # approve, reject, abstain
    weight = Column(Float, default=1.0)
    reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class HealthCheckModel(Base):
    """Database model for health checks."""
    __tablename__ = "hermes_health_checks"

    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, index=True)
    service_name = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    response_time_ms = Column(Float)
    error_message = Column(Text)
    meta_data = Column(Text, default="{}")


class ErrorReportModel(Base):
    """Database model for error reports."""
    __tablename__ = "hermes_error_reports"

    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, index=True)
    service_name = Column(String, nullable=False, index=True)
    error_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, index=True)
    error_message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    context = Column(Text, default="{}")


class RecoveryResultModel(Base):
    """Database model for recovery action results."""
    __tablename__ = "hermes_recovery_results"

    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, index=True)
    action_id = Column(String, nullable=False)
    success = Column(String, nullable=False)  # true/false as string for JSON compatibility
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class ResourceModel(Base):
    """Database model for resources."""
    __tablename__ = "hermes_resources"

    id = Column(String, primary_key=True)
    resource_id = Column(String, unique=True, nullable=False, index=True)
    resource_type = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False, index=True)
    status = Column(String, default="available", index=True)
    capacity = Column(Float, nullable=False)
    allocated = Column(Float, default=0.0)
    utilization = Column(Float, default=0.0)
    meta_data = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceAllocationModel(Base):
    """Database model for resource allocations."""
    __tablename__ = "hermes_resource_allocations"

    id = Column(String, primary_key=True)
    allocation_id = Column(String, unique=True, nullable=False, index=True)
    resource_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False, index=True)
    capacity = Column(Float, nullable=False)
    strategy = Column(String, nullable=False)
    priority = Column(Integer, default=5)
    allocated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


class PricingAdjustmentModel(Base):
    """Database model for pricing adjustments."""
    __tablename__ = "hermes_pricing_adjustments"

    id = Column(String, primary_key=True)
    resource_id = Column(String, nullable=False, index=True)
    current_price = Column(Float, nullable=False)
    new_price = Column(Float, nullable=False)
    adjustment_factor = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
