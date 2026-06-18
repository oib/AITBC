"""
Resource quota enforcement service for multi-tenant AITBC coordinator
"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from ..exceptions import QuotaExceededError, TenantError  # type: ignore[import-not-found]
from ..middleware.tenant_context import get_current_tenant_id  # type: ignore[import-not-found]
from ..models.multitenant import Tenant, TenantQuota, UsageRecord  # type: ignore[import-not-found]


class QuotaEnforcementService:
    """Service for enforcing tenant resource quotas"""

    def __init__(self, db: Session, redis_client: redis.Redis | None = None):
        self.db = db
        self.redis = redis_client
        self.logger = __import__("logging").getLogger(f"aitbc.{self.__class__.__name__}")
        self._quota_cache: dict[str, Any] = {}
        self._cache_ttl = 300
        if self.redis is None:
            self.logger.warning("Redis client not provided - quota caching disabled, falling back to database only")

    async def check_quota(self, resource_type: str, quantity: float, tenant_id: str | None = None) -> bool:
        """Check if tenant has sufficient quota for a resource"""
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        quota = await self._get_current_quota(tenant_id, resource_type)
        if not quota:
            tenant = await self._get_tenant(tenant_id)
            if tenant and tenant.plan in ["enterprise", "unlimited"]:
                return True
            raise QuotaExceededError(f"No quota configured for {resource_type}")
        current_usage = await self._get_current_usage(tenant_id, resource_type)
        if current_usage + quantity > quota.limit_value:
            self.logger.warning(
                "Quota exceeded for tenant %s: %s %s/%s", tenant_id, resource_type, current_usage + quantity, quota.limit_value
            )
            raise QuotaExceededError(f"Quota exceeded for {resource_type}: {current_usage + quantity}/{quota.limit_value}")
        return True

    async def consume_quota(
        self,
        resource_type: str,
        quantity: float,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> UsageRecord:
        """Consume quota and record usage"""
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        await self.check_quota(resource_type, quantity, tenant_id)
        usage_record = UsageRecord(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            quantity=quantity,
            unit=self._get_unit_for_resource(resource_type),
            unit_price=await self._get_unit_price(resource_type),
            total_cost=await self._calculate_cost(resource_type, quantity),
            currency="USD",
            usage_start=datetime.now(UTC),
            usage_end=datetime.now(UTC),
            metadata=metadata or {},
        )
        self.db.add(usage_record)
        await self._update_quota_usage(tenant_id, resource_type, quantity)
        cache_key = f"quota_usage:{tenant_id}:{resource_type}"
        if self.redis:
            current = self.redis.get(cache_key)
            if current:
                self.redis.incrbyfloat(cache_key, quantity)
                self.redis.expire(cache_key, self._cache_ttl)
        self.db.commit()
        self.logger.info("Consumed quota: tenant=%s, resource=%s, quantity=%s", tenant_id, resource_type, quantity)
        return usage_record

    async def release_quota(
        self, resource_type: str, quantity: float, usage_record_id: str, tenant_id: str | None = None
    ) -> None:
        """Release quota (e.g., when job completes early)"""
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        stmt = (
            update(UsageRecord)
            .where(and_(UsageRecord.id == usage_record_id, UsageRecord.tenant_id == tenant_id))
            .values(
                quantity=UsageRecord.quantity - quantity,
                total_cost=UsageRecord.total_cost - await self._calculate_cost(resource_type, quantity),
            )
        )
        result = self.db.execute(stmt)
        if result.rowcount > 0:  # type: ignore[attr-defined]
            await self._update_quota_usage(tenant_id, resource_type, -quantity)
            cache_key = f"quota_usage:{tenant_id}:{resource_type}"
            if self.redis:
                current = self.redis.get(cache_key)
                if current:
                    self.redis.incrbyfloat(cache_key, -quantity)
                    self.redis.expire(cache_key, self._cache_ttl)
            self.db.commit()
            self.logger.info("Released quota: tenant=%s, resource=%s, quantity=%s", tenant_id, resource_type, quantity)

    async def get_quota_status(self, resource_type: str | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        """Get current quota status for a tenant"""
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        stmt = select(TenantQuota).where(and_(TenantQuota.tenant_id == tenant_id, TenantQuota.is_active))
        if resource_type:
            stmt = stmt.where(TenantQuota.resource_type == resource_type)
        quotas = self.db.execute(stmt).scalars().all()
        status: dict[str, Any] = {
            "tenant_id": tenant_id,
            "quotas": {},
            "summary": {"total_resources": len(quotas), "over_limit": 0, "near_limit": 0},
        }
        for quota in quotas:
            current_usage = await self._get_current_usage(tenant_id, quota.resource_type)
            usage_percent = current_usage / quota.limit_value * 100 if quota.limit_value > 0 else 0
            quota_status = {
                "limit": float(quota.limit_value),
                "used": float(current_usage),
                "remaining": float(quota.limit_value - current_usage),
                "usage_percent": round(usage_percent, 2),
                "period": quota.period_type,
                "period_start": quota.period_start.isoformat(),
                "period_end": quota.period_end.isoformat(),
            }
            status["quotas"][quota.resource_type] = quota_status
            if usage_percent >= 100:
                status["summary"]["over_limit"] += 1
            elif usage_percent >= 80:
                status["summary"]["near_limit"] += 1
        return status

    @asynccontextmanager
    async def quota_reservation(
        self, resource_type: str, quantity: float, timeout: int = 300, tenant_id: str | None = None
    ) -> Any:
        """Context manager for temporary quota reservation"""
        tenant_id = tenant_id or get_current_tenant_id()
        reservation_id = f"reserve:{tenant_id}:{resource_type}:{datetime.now(UTC).timestamp()}"
        try:
            await self.check_quota(resource_type, quantity, tenant_id)
            if self.redis:
                reservation_data = {
                    "tenant_id": tenant_id,
                    "resource_type": resource_type,
                    "quantity": quantity,
                    "created_at": datetime.now(UTC).isoformat(),
                }
                self.redis.setex(f"reservation:{reservation_id}", timeout, json.dumps(reservation_data))
            yield reservation_id
        finally:
            if self.redis:
                self.redis.delete(f"reservation:{reservation_id}")

    async def reset_quota_period(self, tenant_id: str, resource_type: str) -> None:
        """Reset quota for a new period"""
        stmt = select(TenantQuota).where(
            and_(TenantQuota.tenant_id == tenant_id, TenantQuota.resource_type == resource_type, TenantQuota.is_active)
        )
        quota = self.db.execute(stmt).scalar_one_or_none()
        if not quota:
            return
        now = datetime.now(UTC)
        if quota.period_type == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        elif quota.period_type == "weekly":
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=6)
        else:
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
        quota.period_start = period_start
        quota.period_end = period_end
        quota.used_value = 0
        self.db.commit()
        cache_key = f"quota_usage:{tenant_id}:{resource_type}"
        if self.redis:
            self.redis.delete(cache_key)
        self.logger.info("Reset quota period: tenant=%s, resource=%s, period=%s", tenant_id, resource_type, quota.period_type)

    async def get_quota_alerts(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """Get quota alerts for tenants approaching or exceeding limits"""
        tenant_id = tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise TenantError("No tenant context found")
        alerts = []
        status = await self.get_quota_status(tenant_id=tenant_id)
        for resource_type, quota_status in status["quotas"].items():
            usage_percent = quota_status["usage_percent"]
            if usage_percent >= 100:
                alerts.append(
                    {
                        "severity": "critical",
                        "resource_type": resource_type,
                        "message": f"Quota exceeded for {resource_type}",
                        "usage_percent": usage_percent,
                        "used": quota_status["used"],
                        "limit": quota_status["limit"],
                    }
                )
            elif usage_percent >= 90:
                alerts.append(
                    {
                        "severity": "warning",
                        "resource_type": resource_type,
                        "message": f"Quota almost exceeded for {resource_type}",
                        "usage_percent": usage_percent,
                        "used": quota_status["used"],
                        "limit": quota_status["limit"],
                    }
                )
            elif usage_percent >= 80:
                alerts.append(
                    {
                        "severity": "info",
                        "resource_type": resource_type,
                        "message": f"Quota usage high for {resource_type}",
                        "usage_percent": usage_percent,
                        "used": quota_status["used"],
                        "limit": quota_status["limit"],
                    }
                )
        return alerts

    async def _get_current_quota(self, tenant_id: str, resource_type: str) -> TenantQuota | None:
        """Get current quota for tenant and resource type"""
        cache_key = f"quota:{tenant_id}:{resource_type}"
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                quota_data = json.loads(cached)
                quota = TenantQuota(**quota_data)
                if quota.period_end >= datetime.now(UTC):
                    return quota
        stmt = select(TenantQuota).where(
            and_(
                TenantQuota.tenant_id == tenant_id,
                TenantQuota.resource_type == resource_type,
                TenantQuota.is_active,
                TenantQuota.period_start <= datetime.now(UTC),
                TenantQuota.period_end >= datetime.now(UTC),
            )
        )
        quota = self.db.execute(stmt).scalar_one_or_none()
        if quota and self.redis:
            quota_data = {
                "id": str(quota.id),
                "tenant_id": str(quota.tenant_id),
                "resource_type": quota.resource_type,
                "limit_value": float(quota.limit_value),
                "used_value": float(quota.used_value),
                "period_start": quota.period_start.isoformat(),
                "period_end": quota.period_end.isoformat(),
            }
            self.redis.setex(cache_key, self._cache_ttl, json.dumps(quota_data))
        return quota

    async def _get_current_usage(self, tenant_id: str, resource_type: str) -> float:
        """Get current usage for tenant and resource type"""
        cache_key = f"quota_usage:{tenant_id}:{resource_type}"
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                return float(cached)
        stmt = select(func.sum(UsageRecord.quantity)).where(
            and_(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.resource_type == resource_type,
                UsageRecord.usage_start >= func.date_trunc("month", func.current_date()),
            )
        )
        result = self.db.execute(stmt).scalar()
        usage = float(result) if result else 0.0
        if self.redis:
            self.redis.setex(cache_key, self._cache_ttl, str(usage))
        return usage

    async def _update_quota_usage(self, tenant_id: str, resource_type: str, quantity: float) -> None:
        """Update quota usage in database"""
        stmt = (
            update(TenantQuota)
            .where(and_(TenantQuota.tenant_id == tenant_id, TenantQuota.resource_type == resource_type, TenantQuota.is_active))
            .values(used_value=TenantQuota.used_value + quantity)
        )
        self.db.execute(stmt)

    async def _get_tenant(self, tenant_id: str) -> Tenant | None:
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
            "compute_hours": "hours",
        }
        return unit_map.get(resource_type, "units")

    async def _get_unit_price(self, resource_type: str) -> float:
        """Get unit price for resource type"""
        price_map = {"gpu_hours": 0.5, "storage_gb": 0.02, "api_calls": 0.0001, "bandwidth_gb": 0.01, "compute_hours": 0.3}
        return price_map.get(resource_type, 0.0)

    async def _calculate_cost(self, resource_type: str, quantity: float) -> float:
        """Calculate cost for resource usage"""
        unit_price = await self._get_unit_price(resource_type)
        return unit_price * quantity


class QuotaMiddleware:
    """Middleware to enforce quotas on API endpoints"""

    def __init__(self, quota_service: QuotaEnforcementService):
        self.quota_service = quota_service
        self.logger = __import__("logging").getLogger(f"aitbc.{self.__class__.__name__}")
        self.endpoint_costs = {
            "/jobs": {"resource": "compute_hours", "cost": 0.1},
            "/models": {"resource": "storage_gb", "cost": 0.1},
            "/data": {"resource": "storage_gb", "cost": 0.05},
            "/analytics": {"resource": "api_calls", "cost": 1},
        }

    async def check_endpoint_quota(self, endpoint: str, estimated_cost: float = 0) -> None:
        """Check if endpoint call is within quota"""
        resource_config = self.endpoint_costs.get(endpoint)
        if not resource_config:
            return
        try:
            await self.quota_service.check_quota(resource_config["resource"], resource_config["cost"] + estimated_cost)  # type: ignore[arg-type, operator]
        except QuotaExceededError as e:
            self.logger.warning("Quota exceeded for endpoint %s: %s", endpoint, e)
            raise

    async def consume_endpoint_quota(self, endpoint: str, actual_cost: float = 0) -> None:
        """Consume quota after endpoint execution"""
        resource_config = self.endpoint_costs.get(endpoint)
        if not resource_config:
            return
        try:
            await self.quota_service.consume_quota(resource_config["resource"], resource_config["cost"] + actual_cost)  # type: ignore[arg-type, operator]
        except Exception as e:
            self.logger.error("Failed to consume quota for %s: %s", endpoint, e)
