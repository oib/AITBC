"""Service for Hermes autonomous resource management with database storage."""

import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

from ....schemas.hermes_resource import (
    Resource,
    ResourceType,
    ResourceStatus,
    AllocationStrategy,
    ResourceAllocationRequest,
    ResourceAllocationResponse,
    ResourceReleaseRequest,
    ResourceReleaseResponse,
    PricingAdjustment,
    ResourcePool,
)
from ....models.hermes import (
    ResourceModel,
    ResourceAllocationModel,
    PricingAdjustmentModel,
)


class ResourceService:
    """Service for autonomous resource management with database storage."""

    def __init__(self):
        # Database storage for resources
        pass

    def register_resource(
        self,
        resource: Resource,
        session: Session
    ) -> str:
        """Register a new resource for autonomous management."""
        # Check if resource already exists
        existing = session.query(ResourceModel).filter_by(resource_id=resource.resource_id).first()
        if existing:
            # Update existing resource
            existing.resource_type = resource.resource_type
            existing.agent_id = resource.agent_id
            existing.status = resource.status
            existing.capacity = resource.capacity
            existing.allocated = resource.allocated
            existing.utilization = resource.utilization
            existing.meta_data = json.dumps(resource.metadata or {})
            existing.updated_at = datetime.utcnow()
        else:
            # Create new resource
            resource_record = ResourceModel(
                id=str(uuid.uuid4()),
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                agent_id=resource.agent_id,
                status=resource.status,
                capacity=resource.capacity,
                allocated=resource.allocated,
                utilization=resource.utilization,
                meta_data=json.dumps(resource.metadata or {}),
            )
            session.add(resource_record)

        session.commit()

        logger.info(f"Resource registered: {resource.resource_id} - {resource.resource_type}")
        return resource.resource_id

    def allocate_resource(
        self,
        request: ResourceAllocationRequest,
        session: Session
    ) -> ResourceAllocationResponse:
        """Allocate resources based on strategy."""
        # Find available resources matching criteria
        candidates = session.query(ResourceModel).filter(
            ResourceModel.resource_type == request.resource_type,
            ResourceModel.status == ResourceStatus.AVAILABLE,
            (ResourceModel.capacity - ResourceModel.allocated) >= request.required_capacity
        ).all()

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

        allocation_record = ResourceAllocationModel(
            id=str(uuid.uuid4()),
            allocation_id=allocation_id,
            resource_id=selected_resource.resource_id,
            agent_id=request.agent_id,
            capacity=request.required_capacity,
            strategy=request.strategy,
            priority=request.priority,
            allocated_at=datetime.utcnow(),
            expires_at=expires_at,
        )

        session.add(allocation_record)
        session.commit()

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
        # Find allocation
        allocation = session.query(ResourceAllocationModel).filter_by(
            allocation_id=request.allocation_id
        ).first()

        if not allocation:
            return ResourceReleaseResponse(
                allocation_id=request.allocation_id,
                status="error",
                message="Allocation not found",
                released_capacity=0.0
            )

        # Verify agent ownership
        if allocation.agent_id != request.agent_id:
            return ResourceReleaseResponse(
                allocation_id=request.allocation_id,
                status="error",
                message="Agent does not own this allocation",
                released_capacity=0.0
            )

        # Release resource
        resource = session.query(ResourceModel).filter_by(resource_id=allocation.resource_id).first()
        if resource:
            resource.allocated -= allocation.capacity
            resource.utilization = resource.allocated / resource.capacity

            if resource.allocated == 0:
                resource.status = ResourceStatus.AVAILABLE
            else:
                resource.status = ResourceStatus.ALLOCATED

        # Remove allocation
        released_capacity = allocation.capacity
        session.delete(allocation)
        session.commit()

        logger.info(
            f"Resource released: {request.allocation_id} - {allocation.resource_id} "
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
        candidates: List[ResourceModel],
        strategy: AllocationStrategy
    ) -> ResourceModel:
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
        # Calculate pool utilization
        resources = session.query(ResourceModel).filter_by(resource_type=resource_type).all()

        if not resources:
            return None

        total_capacity = sum(r.capacity for r in resources)
        total_allocated = sum(r.allocated for r in resources)
        utilization = total_allocated / total_capacity if total_capacity > 0 else 0

        # Pricing adjustment logic
        current_price = 0.1  # Default base price
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

        # Create pricing adjustment record
        adjustment = PricingAdjustmentModel(
            id=str(uuid.uuid4()),
            resource_id=f"{resource_type.value}:pool",
            current_price=current_price,
            new_price=new_price,
            adjustment_factor=adjustment_factor,
            reason=reason,
            timestamp=datetime.utcnow(),
        )

        session.add(adjustment)
        session.commit()

        logger.info(
            f"Pricing adjusted: {resource_type.value} - {current_price} -> {new_price} "
            f"({reason})"
        )

        return PricingAdjustment(
            resource_id=adjustment.resource_id,
            current_price=adjustment.current_price,
            new_price=adjustment.new_price,
            adjustment_factor=adjustment.adjustment_factor,
            reason=adjustment.reason,
            timestamp=adjustment.timestamp,
        )

    def get_resource_pools(
        self,
        session: Session
    ) -> List[ResourcePool]:
        """Get all resource pools."""
        pools = {}

        # Group resources by type
        resources = session.query(ResourceModel).all()
        for resource in resources:
            pool_key = f"{resource.resource_type.value}:pool"
            if pool_key not in pools:
                pools[pool_key] = {
                    "resource_type": resource.resource_type,
                    "total_capacity": 0.0,
                    "available_capacity": 0.0,
                    "allocated_capacity": 0.0,
                }

            pools[pool_key]["total_capacity"] += resource.capacity
            pools[pool_key]["allocated_capacity"] += resource.allocated

        # Calculate available capacity and utilization
        result = []
        for pool_key, data in pools.items():
            data["available_capacity"] = data["total_capacity"] - data["allocated_capacity"]
            data["average_utilization"] = data["allocated_capacity"] / data["total_capacity"]

            result.append(ResourcePool(
                pool_id=pool_key,
                resource_type=data["resource_type"],
                total_capacity=data["total_capacity"],
                available_capacity=data["available_capacity"],
                allocated_capacity=data["allocated_capacity"],
                average_utilization=data["average_utilization"],
                pricing=0.1,  # Default pricing
            ))

        return result

    def get_allocations(
        self,
        agent_id: Optional[str] = None,
        session: Session = None
    ) -> List[dict]:
        """Get allocations with optional filtering."""
        if not session:
            from ....storage.db_pg import SessionLocal
            session = SessionLocal()
            should_close = True
        else:
            should_close = False

        try:
            query = session.query(ResourceAllocationModel)

            if agent_id:
                query = query.filter_by(agent_id=agent_id)

            allocations = query.all()

            return [
                {
                    "allocation_id": a.allocation_id,
                    "resource_id": a.resource_id,
                    "agent_id": a.agent_id,
                    "capacity": a.capacity,
                    "allocated_at": a.allocated_at,
                    "expires_at": a.expires_at,
                    "strategy": a.strategy,
                    "priority": a.priority,
                }
                for a in allocations
            ]
        finally:
            if should_close:
                session.close()


# Global service instance
resource_service = ResourceService()
