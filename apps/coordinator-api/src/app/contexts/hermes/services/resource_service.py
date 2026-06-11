"""Service for Hermes autonomous resource management."""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

from ....schemas.hermes_resource import (
    AllocationStrategy,
    PricingAdjustment,
    Resource,
    ResourceAllocationRequest,
    ResourceAllocationResponse,
    ResourcePool,
    ResourceReleaseRequest,
    ResourceReleaseResponse,
    ResourceStatus,
    ResourceType,
)


class ResourceService:
    """Service for autonomous resource management."""

    def __init__(self):
        # In-memory storage for resources (replace with database in production)
        self.resources: Dict[str, Resource] = {}
        self.allocations: Dict[str, dict] = {}
        self.resource_pools: Dict[str, ResourcePool] = {}

    def register_resource(
        self,
        resource: Resource,
        session: Session
    ) -> str:
        """Register a new resource for autonomous management."""
        self.resources[resource.resource_id] = resource

        # Update or create resource pool
        pool_key = f"{resource.resource_type.value}:pool"
        if pool_key not in self.resource_pools:
            self.resource_pools[pool_key] = ResourcePool(
                pool_id=pool_key,
                resource_type=resource.resource_type,
                total_capacity=resource.capacity,
                available_capacity=resource.capacity,
                allocated_capacity=0.0,
                average_utilization=0.0
            )
        else:
            pool = self.resource_pools[pool_key]
            pool.total_capacity += resource.capacity
            pool.available_capacity += resource.capacity

        logger.info(f"Resource registered: {resource.resource_id} - {resource.resource_type}")
        return resource.resource_id

    def allocate_resource(
        self,
        request: ResourceAllocationRequest,
        session: Session
    ) -> ResourceAllocationResponse:
        """Allocate resources based on strategy."""
        # Find available resources matching criteria
        candidates = [
            r for r in self.resources.values()
            if r.resource_type == request.resource_type
            and r.status == ResourceStatus.AVAILABLE
            and (r.capacity - r.allocated) >= request.required_capacity
        ]

        if not candidates:
            return ResourceAllocationResponse(
                allocation_id="",
                resource_id="",
                allocated_capacity=0.0,
                status="error",
                message="No available resources matching criteria"
            )

        # Select resource based on strategy
        selected_resource = self._select_resource(candidates, request.strategy)

        # Allocate resource
        allocation_id = str(uuid.uuid4())
        selected_resource.allocated += request.required_capacity
        selected_resource.utilization = selected_resource.allocated / selected_resource.capacity

        if selected_resource.allocated >= selected_resource.capacity:
            selected_resource.status = ResourceStatus.ALLOCATED

        # Record allocation
        expires_at = None
        if request.duration_hours:
            expires_at = datetime.utcnow() + timedelta(hours=request.duration_hours)

        self.allocations[allocation_id] = {
            "allocation_id": allocation_id,
            "resource_id": selected_resource.resource_id,
            "agent_id": request.agent_id,
            "capacity": request.required_capacity,
            "allocated_at": datetime.utcnow(),
            "expires_at": expires_at,
            "strategy": request.strategy,
            "priority": request.priority
        }

        # Update resource pool
        pool_key = f"{request.resource_type.value}:pool"
        if pool_key in self.resource_pools:
            pool = self.resource_pools[pool_key]
            pool.allocated_capacity += request.required_capacity
            pool.available_capacity -= request.required_capacity
            pool.average_utilization = pool.allocated_capacity / pool.total_capacity

        logger.info(
            f"Resource allocated: {allocation_id} - {selected_resource.resource_id} "
            f"to {request.agent_id} ({request.required_capacity} units)"
        )

        return ResourceAllocationResponse(
            allocation_id=allocation_id,
            resource_id=selected_resource.resource_id,
            allocated_capacity=request.required_capacity,
            status="success",
            message="Resource allocated successfully",
            expires_at=expires_at
        )

    def release_resource(
        self,
        request: ResourceReleaseRequest,
        session: Session
    ) -> ResourceReleaseResponse:
        """Release allocated resources."""
        if request.allocation_id not in self.allocations:
            return ResourceReleaseResponse(
                allocation_id=request.allocation_id,
                status="error",
                message="Allocation not found",
                released_capacity=0.0
            )

        allocation = self.allocations[request.allocation_id]

        # Verify agent ownership
        if allocation["agent_id"] != request.agent_id:
            return ResourceReleaseResponse(
                allocation_id=request.allocation_id,
                status="error",
                message="Agent does not own this allocation",
                released_capacity=0.0
            )

        # Release resource
        resource_id = allocation["resource_id"]
        if resource_id in self.resources:
            resource = self.resources[resource_id]
            resource.allocated -= allocation["capacity"]
            resource.utilization = resource.allocated / resource.capacity

            if resource.allocated == 0:
                resource.status = ResourceStatus.AVAILABLE
            else:
                resource.status = ResourceStatus.ALLOCATED

        # Update resource pool
        pool_key = f"{self.resources[resource_id].resource_type.value}:pool"
        if pool_key in self.resource_pools:
            pool = self.resource_pools[pool_key]
            pool.allocated_capacity -= allocation["capacity"]
            pool.available_capacity += allocation["capacity"]
            pool.average_utilization = pool.allocated_capacity / pool.total_capacity

        # Remove allocation
        released_capacity = allocation["capacity"]
        del self.allocations[request.allocation_id]

        logger.info(
            f"Resource released: {request.allocation_id} - {resource_id} "
            f"from {request.agent_id} ({released_capacity} units)"
        )

        return ResourceReleaseResponse(
            allocation_id=request.allocation_id,
            status="success",
            message="Resource released successfully",
            released_capacity=released_capacity
        )

    def _select_resource(
        self,
        candidates: List[Resource],
        strategy: AllocationStrategy
    ) -> Resource:
        """Select resource based on allocation strategy."""
        if strategy == AllocationStrategy.LEAST_LOADED:
            # Select resource with lowest utilization
            return min(candidates, key=lambda r: r.utilization)

        elif strategy == AllocationStrategy.PRIORITY_BASED:
            # Select resource with highest capacity
            return max(candidates, key=lambda r: r.capacity)

        elif strategy == AllocationStrategy.ROUND_ROBIN:
            # Simple round-robin (first available)
            return candidates[0]

        else:  # DEMAND_BASED (default)
            # Select resource with most available capacity
            return max(candidates, key=lambda r: r.capacity - r.allocated)

    def adjust_pricing(
        self,
        resource_type: ResourceType,
        session: Session
    ) -> Optional[PricingAdjustment]:
        """Automatically adjust pricing based on utilization."""
        pool_key = f"{resource_type.value}:pool"
        if pool_key not in self.resource_pools:
            return None

        pool = self.resource_pools[pool_key]
        utilization = pool.average_utilization

        # Pricing adjustment logic
        current_price = pool.pricing or 0.1
        adjustment_factor = 1.0

        if utilization > 0.8:
            # High demand - increase price
            adjustment_factor = 1.2
            reason = "High utilization (>80%)"
        elif utilization > 0.6:
            # Moderate demand - slight increase
            adjustment_factor = 1.1
            reason = "Moderate utilization (>60%)"
        elif utilization < 0.3:
            # Low demand - decrease price
            adjustment_factor = 0.9
            reason = "Low utilization (<30%)"
        else:
            # Normal demand - no change
            return None

        new_price = current_price * adjustment_factor
        pool.pricing = new_price

        # Create pricing adjustment record
        adjustment = PricingAdjustment(
            resource_id=pool_key,
            current_price=current_price,
            new_price=new_price,
            adjustment_factor=adjustment_factor,
            reason=reason,
            timestamp=datetime.utcnow()
        )

        logger.info(
            f"Pricing adjusted: {resource_type.value} - {current_price} -> {new_price} "
            f"({reason})"
        )

        return adjustment

    def get_resource_pools(
        self,
        session: Session
    ) -> List[ResourcePool]:
        """Get all resource pools."""
        return list(self.resource_pools.values())

    def get_allocations(
        self,
        agent_id: Optional[str] = None,
        session: Session = None
    ) -> List[dict]:
        """Get allocations with optional filtering."""
        results = list(self.allocations.values())

        if agent_id:
            results = [a for a in results if a["agent_id"] == agent_id]

        return results


# Global service instance
resource_service = ResourceService()
