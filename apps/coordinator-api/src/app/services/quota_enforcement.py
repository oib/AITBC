"""
Resource quota enforcement service for multi-tenant AITBC coordinator
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, update, and_, func
from contextlib import asynccontextmanager
import redis
import json

from ..models.multitenant import TenantQuota, UsageRecord, Tenant
from ..exceptions import QuotaExceededError, TenantError
from ..middleware.tenant_context import get_current_tenant_id


class QuotaEnforcementService:
    """Service for enforcing tenant resource quotas"""
    
    def __init__(self, db: Session, redis_client: Optional[redis.Redis] = None):
        self.db = db
        self.redis = redis_client
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
        
        # Cache for quota lookups
        self._quota_cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    async def check_quota(
        self,
        resource_type: str,
        quantity: float,
        tenant_id: Optional[str] = None
    ) -> bool:
        """Check if tenant has sufficient quota for a resource"""
        
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        
        # Get current quota and usage
        quota = await self._get_current_quota(tenant_id, resource_type)
        
        if not quota:
            # No quota set, check if unlimited plan
            tenant = await self._get_tenant(tenant_id)
            if tenant and tenant.plan in ["enterprise", "unlimited"]:
                return True
            raise QuotaExceededError(f"No quota configured for {resource_type}")
        
        # Check if adding quantity would exceed limit
        current_usage = await self._get_current_usage(tenant_id, resource_type)
        
        if current_usage + quantity > quota.limit_value:
            # Log quota exceeded
            self.logger.warning(
                f"Quota exceeded for tenant {tenant_id}: "
                f"{resource_type} {current_usage + quantity}/{quota.limit_value}"
            )
            
            raise QuotaExceededError(
                f"Quota exceeded for {resource_type}: "
                f"{current_usage + quantity}/{quota.limit_value}"
            )
        
        return True
    
    async def consume_quota(
        self,
        resource_type: str,
        quantity: float,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None
    ) -> UsageRecord:
        """Consume quota and record usage"""
        
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        
        # Check quota first
        await self.check_quota(resource_type, quantity, tenant_id)
        
        # Create usage record
        usage_record = UsageRecord(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            quantity=quantity,
            unit=self._get_unit_for_resource(resource_type),
            unit_price=await self._get_unit_price(resource_type),
            total_cost=await self._calculate_cost(resource_type, quantity),
            currency="USD",
            usage_start=datetime.utcnow(),
            usage_end=datetime.utcnow(),
            metadata=metadata or {}
        )
        
        self.db.add(usage_record)
        
        # Update quota usage
        await self._update_quota_usage(tenant_id, resource_type, quantity)
        
        # Update cache
        cache_key = f"quota_usage:{tenant_id}:{resource_type}"
        if self.redis:
            current = self.redis.get(cache_key)
            if current:
                self.redis.incrbyfloat(cache_key, quantity)
                self.redis.expire(cache_key, self._cache_ttl)
        
        self.db.commit()
        self.logger.info(
            f"Consumed quota: tenant={tenant_id}, "
            f"resource={resource_type}, quantity={quantity}"
        )
        
        return usage_record
    
    async def release_quota(
        self,
        resource_type: str,
        quantity: float,
        usage_record_id: str,
        tenant_id: Optional[str] = None
    ):
        """Release quota (e.g., when job completes early)"""
        
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        
        # Update usage record
        stmt = update(UsageRecord).where(
            and_(
                UsageRecord.id == usage_record_id,
                UsageRecord.tenant_id == tenant_id
            )
        ).values(
            quantity=UsageRecord.quantity - quantity,
            total_cost=UsageRecord.total_cost - await self._calculate_cost(resource_type, quantity)
        )
        
        result = self.db.execute(stmt)
        
        if result.rowcount > 0:
            # Update quota usage
            await self._update_quota_usage(tenant_id, resource_type, -quantity)
            
            # Update cache
            cache_key = f"quota_usage:{tenant_id}:{resource_type}"
            if self.redis:
                current = self.redis.get(cache_key)
                if current:
                    self.redis.incrbyfloat(cache_key, -quantity)
                    self.redis.expire(cache_key, self._cache_ttl)
            
            self.db.commit()
            self.logger.info(
                f"Released quota: tenant={tenant_id}, "
                f"resource={resource_type}, quantity={quantity}"
            )
    
    async def get_quota_status(
        self,
        resource_type: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get current quota status for a tenant"""
        
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        
        # Get all quotas for tenant
        stmt = select(TenantQuota).where(
            and_(
                TenantQuota.tenant_id == tenant_id,
                TenantQuota.is_active == True
            )
        )
        
        if resource_type:
            stmt = stmt.where(TenantQuota.resource_type == resource_type)
        
        quotas = self.db.execute(stmt).scalars().all()
        
        status = {
            "tenant_id": tenant_id,
            "quotas": {},
            "summary": {
                "total_resources": len(quotas),
                "over_limit": 0,
                "near_limit": 0
            }
        }
        
        for quota in quotas:
            current_usage = await self._get_current_usage(tenant_id, quota.resource_type)
            usage_percent = (current_usage / quota.limit_value) * 100 if quota.limit_value > 0 else 0
            
            quota_status = {
                "limit": float(quota.limit_value),
                "used": float(current_usage),
                "remaining": float(quota.limit_value - current_usage),
                "usage_percent": round(usage_percent, 2),
                "period": quota.period_type,
                "period_start": quota.period_start.isoformat(),
                "period_end": quota.period_end.isoformat()
            }
            
            status["quotas"][quota.resource_type] = quota_status
            
            # Update summary
            if usage_percent >= 100:
                status["summary"]["over_limit"] += 1
            elif usage_percent >= 80:
                status["summary"]["near_limit"] += 1
        
        return status
    
    @asynccontextmanager
    async def quota_reservation(
        self,
        resource_type: str,
        quantity: float,
        timeout: int = 300,  # 5 minutes
        tenant_id: Optional[str] = None
    ):
        """Context manager for temporary quota reservation"""
        
        tenant_id = tenant_id or get_current_tenant_id()
        reservation_id = f"reserve:{tenant_id}:{resource_type}:{datetime.utcnow().timestamp()}"
        
        try:
            # Reserve quota
            await self.check_quota(resource_type, quantity, tenant_id)
            
            # Store reservation in Redis
            if self.redis:
                reservation_data = {
                    "tenant_id": tenant_id,
                    "resource_type": resource_type,
                    "quantity": quantity,
                    "created_at": datetime.utcnow().isoformat()
                }
                self.redis.setex(
                    f"reservation:{reservation_id}",
                    timeout,
                    json.dumps(reservation_data)
                )
            
            yield reservation_id
            
        finally:
            # Clean up reservation
            if self.redis:
                self.redis.delete(f"reservation:{reservation_id}")
    
    async def reset_quota_period(self, tenant_id: str, resource_type: str):
        """Reset quota for a new period"""
        
        # Get current quota
        stmt = select(TenantQuota).where(
            and_(
                TenantQuota.tenant_id == tenant_id,
                TenantQuota.resource_type == resource_type,
                TenantQuota.is_active == True
            )
        )
        
        quota = self.db.execute(stmt).scalar_one_or_none()
        
        if not quota:
            return
        
        # Calculate new period
        now = datetime.utcnow()
        if quota.period_type == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        elif quota.period_type == "weekly":
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            period_end = period_start + timedelta(days=6)
        else:  # daily
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
        
        # Update quota
        quota.period_start = period_start
        quota.period_end = period_end
        quota.used_value = 0
        
        self.db.commit()
        
        # Clear cache
        cache_key = f"quota_usage:{tenant_id}:{resource_type}"
        if self.redis:
            self.redis.delete(cache_key)
        
        self.logger.info(
            f"Reset quota period: tenant={tenant_id}, "
            f"resource={resource_type}, period={quota.period_type}"
        )
    
    async def get_quota_alerts(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get quota alerts for tenants approaching or exceeding limits"""
        
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        
        alerts = []
        status = await self.get_quota_status(tenant_id=tenant_id)
        
        for resource_type, quota_status in status["quotas"].items():
            usage_percent = quota_status["usage_percent"]
            
            if usage_percent >= 100:
                alerts.append({
                    "severity": "critical",
                    "resource_type": resource_type,
                    "message": f"Quota exceeded for {resource_type}",
                    "usage_percent": usage_percent,
                    "used": quota_status["used"],
                    "limit": quota_status["limit"]
                })
            elif usage_percent >= 90:
                alerts.append({
                    "severity": "warning",
                    "resource_type": resource_type,
                    "message": f"Quota almost exceeded for {resource_type}",
                    "usage_percent": usage_percent,
                    "used": quota_status["used"],
                    "limit": quota_status["limit"]
                })
            elif usage_percent >= 80:
                alerts.append({
                    "severity": "info",
                    "resource_type": resource_type,
                    "message": f"Quota usage high for {resource_type}",
                    "usage_percent": usage_percent,
                    "used": quota_status["used"],
                    "limit": quota_status["limit"]
                })
        
        return alerts
    
    # Private methods
    
    async def _get_current_quota(self, tenant_id: str, resource_type: str) -> Optional[TenantQuota]:
        """Get current quota for tenant and resource type"""
        
        cache_key = f"quota:{tenant_id}:{resource_type}"
        
        # Check cache first
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                quota_data = json.loads(cached)
                quota = TenantQuota(**quota_data)
                # Check if still valid
                if quota.period_end >= datetime.utcnow():
                    return quota
        
        # Query database
        stmt = select(TenantQuota).where(
            and_(
                TenantQuota.tenant_id == tenant_id,
                TenantQuota.resource_type == resource_type,
                TenantQuota.is_active == True,
                TenantQuota.period_start <= datetime.utcnow(),
                TenantQuota.period_end >= datetime.utcnow()
            )
        )
        
        quota = self.db.execute(stmt).scalar_one_or_none()
        
        # Cache result
        if quota and self.redis:
            quota_data = {
                "id": str(quota.id),
                "tenant_id": str(quota.tenant_id),
                "resource_type": quota.resource_type,
                "limit_value": float(quota.limit_value),
                "used_value": float(quota.used_value),
                "period_start": quota.period_start.isoformat(),
                "period_end": quota.period_end.isoformat()
            }
            self.redis.setex(
                cache_key,
                self._cache_ttl,
                json.dumps(quota_data)
            )
        
        return quota
    
    async def _get_current_usage(self, tenant_id: str, resource_type: str) -> float:
        """Get current usage for tenant and resource type"""
        
        cache_key = f"quota_usage:{tenant_id}:{resource_type}"
        
        # Check cache first
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                return float(cached)
        
        # Query database
        stmt = select(func.sum(UsageRecord.quantity)).where(
            and_(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.resource_type == resource_type,
                UsageRecord.usage_start >= func.date_trunc('month', func.current_date())
            )
        )
        
        result = self.db.execute(stmt).scalar()
        usage = float(result) if result else 0.0
        
        # Cache result
        if self.redis:
            self.redis.setex(cache_key, self._cache_ttl, str(usage))
        
        return usage
    
    async def _update_quota_usage(self, tenant_id: str, resource_type: str, quantity: float):
        """Update quota usage in database"""
        
        stmt = update(TenantQuota).where(
            and_(
                TenantQuota.tenant_id == tenant_id,
                TenantQuota.resource_type == resource_type,
                TenantQuota.is_active == True
            )
        ).values(
            used_value=TenantQuota.used_value + quantity
        )
        
        self.db.execute(stmt)
    
    async def _get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        return self.db.execute(stmt).scalar_one_or_none()
    
    def _get_unit_for_resource(self, resource_type: str) -> str:
        """Get unit for resource type"""
        unit_map = {
            "gpu_hours": "hours",
            "storage_gb": "gb",
            "api_calls": "calls",
            "bandwidth_gb": "gb",
            "compute_hours": "hours"
        }
        return unit_map.get(resource_type, "units")
    
    async def _get_unit_price(self, resource_type: str) -> float:
        """Get unit price for resource type"""
        # In a real implementation, this would come from a pricing table
        price_map = {
            "gpu_hours": 0.50,  # $0.50 per hour
            "storage_gb": 0.02,  # $0.02 per GB per month
            "api_calls": 0.0001,  # $0.0001 per call
            "bandwidth_gb": 0.01,  # $0.01 per GB
            "compute_hours": 0.30  # $0.30 per hour
        }
        return price_map.get(resource_type, 0.0)
    
    async def _calculate_cost(self, resource_type: str, quantity: float) -> float:
        """Calculate cost for resource usage"""
        unit_price = await self._get_unit_price(resource_type)
        return unit_price * quantity


class QuotaMiddleware:
    """Middleware to enforce quotas on API endpoints"""
    
    def __init__(self, quota_service: QuotaEnforcementService):
        self.quota_service = quota_service
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
        
        # Resource costs per endpoint
        self.endpoint_costs = {
            "/api/v1/jobs": {"resource": "compute_hours", "cost": 0.1},
            "/api/v1/models": {"resource": "storage_gb", "cost": 0.1},
            "/api/v1/data": {"resource": "storage_gb", "cost": 0.05},
            "/api/v1/analytics": {"resource": "api_calls", "cost": 1}
        }
    
    async def check_endpoint_quota(self, endpoint: str, estimated_cost: float = 0):
        """Check if endpoint call is within quota"""
        
        resource_config = self.endpoint_costs.get(endpoint)
        if not resource_config:
            return  # No quota check for this endpoint
        
        try:
            await self.quota_service.check_quota(
                resource_config["resource"],
                resource_config["cost"] + estimated_cost
            )
        except QuotaExceededError as e:
            self.logger.warning(f"Quota exceeded for endpoint {endpoint}: {e}")
            raise
    
    async def consume_endpoint_quota(self, endpoint: str, actual_cost: float = 0):
        """Consume quota after endpoint execution"""
        
        resource_config = self.endpoint_costs.get(endpoint)
        if not resource_config:
            return
        
        try:
            await self.quota_service.consume_quota(
                resource_config["resource"],
                resource_config["cost"] + actual_cost
            )
        except Exception as e:
            self.logger.error(f"Failed to consume quota for {endpoint}: {e}")
            # Don't fail the request, just log the error
