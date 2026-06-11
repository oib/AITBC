"""Schemas for Hermes autonomous resource management."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """Types of resources that can be managed."""
    GPU = "gpu"
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"


class ResourceStatus(str, Enum):
    """Status of resources."""
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    RESERVED = "reserved"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class AllocationStrategy(str, Enum):
    """Resource allocation strategies."""
    DEMAND_BASED = "demand_based"
    PRIORITY_BASED = "priority_based"
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"


class Resource(BaseModel):
    """Resource definition."""
    resource_id: str
    resource_type: ResourceType
    agent_id: str
    status: ResourceStatus
    capacity: float
    allocated: float = Field(default=0.0, ge=0.0)
    utilization: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: Optional[dict] = None


class ResourceAllocationRequest(BaseModel):
    """Request to allocate resources."""
    resource_type: ResourceType
    agent_id: str
    required_capacity: float = Field(gt=0.0)
    strategy: AllocationStrategy = AllocationStrategy.DEMAND_BASED
    priority: int = Field(default=5, ge=1, le=10)
    duration_hours: Optional[float] = None
    metadata: Optional[dict] = None


class ResourceAllocationResponse(BaseModel):
    """Response to resource allocation request."""
    allocation_id: str
    resource_id: str
    allocated_capacity: float
    status: str
    message: str
    expires_at: Optional[datetime] = None


class ResourceReleaseRequest(BaseModel):
    """Request to release allocated resources."""
    allocation_id: str
    agent_id: str


class ResourceReleaseResponse(BaseModel):
    """Response to resource release request."""
    allocation_id: str
    status: str
    message: str
    released_capacity: float


class PricingAdjustment(BaseModel):
    """Pricing adjustment for resources."""
    resource_id: str
    current_price: float
    new_price: float
    adjustment_factor: float
    reason: str
    timestamp: datetime


class ResourcePool(BaseModel):
    """Resource pool for management."""
    pool_id: str
    resource_type: ResourceType
    total_capacity: float
    available_capacity: float
    allocated_capacity: float
    average_utilization: float
    pricing: Optional[float] = None
