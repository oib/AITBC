"""
Tenant management service for multi-tenant AITBC coordinator
"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete, and_, or_, func

from ..models.multitenant import (
    Tenant, TenantUser, TenantQuota, TenantApiKey,
    TenantAuditLog, TenantStatus
)
from ..storage.db import get_db
from ..exceptions import TenantError, QuotaExceededError


class TenantManagementService:
    """Service for managing tenants in multi-tenant environment"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    async def create_tenant(
        self,
        name: str,
        contact_email: str,
        plan: str = "trial",
        domain: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        features: Optional[Dict[str, Any]] = None
    ) -> Tenant:
        """Create a new tenant"""
        
        # Generate unique slug
        slug = self._generate_slug(name)
        if await self._tenant_exists(slug=slug):
            raise TenantError(f"Tenant with slug '{slug}' already exists")
        
        # Check domain uniqueness if provided
        if domain and await self._tenant_exists(domain=domain):
            raise TenantError(f"Domain '{domain}' is already in use")
        
        # Create tenant
        tenant = Tenant(
            name=name,
            slug=slug,
            domain=domain,
            contact_email=contact_email,
            plan=plan,
            status=TenantStatus.PENDING.value,
            settings=settings or {},
            features=features or {}
        )
        
        self.db.add(tenant)
        self.db.flush()
        
        # Create default quotas
        await self._create_default_quotas(tenant.id, plan)
        
        # Log creation
        await self._log_audit_event(
            tenant_id=tenant.id,
            event_type="tenant_created",
            event_category="lifecycle",
            actor_id="system",
            actor_type="system",
            resource_type="tenant",
            resource_id=str(tenant.id),
            new_values={"name": name, "plan": plan}
        )
        
        self.db.commit()
        self.logger.info(f"Created tenant: {tenant.id} ({name})")
        
        return tenant
    
    async def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        return self.db.execute(stmt).scalar_one_or_none()
    
    async def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get tenant by slug"""
        stmt = select(Tenant).where(Tenant.slug == slug)
        return self.db.execute(stmt).scalar_one_or_none()
    
    async def get_tenant_by_domain(self, domain: str) -> Optional[Tenant]:
        """Get tenant by domain"""
        stmt = select(Tenant).where(Tenant.domain == domain)
        return self.db.execute(stmt).scalar_one_or_none()
    
    async def update_tenant(
        self,
        tenant_id: str,
        updates: Dict[str, Any],
        actor_id: str,
        actor_type: str = "user"
    ) -> Tenant:
        """Update tenant information"""
        
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise TenantError(f"Tenant not found: {tenant_id}")
        
        # Store old values for audit
        old_values = {
            "name": tenant.name,
            "contact_email": tenant.contact_email,
            "billing_email": tenant.billing_email,
            "settings": tenant.settings,
            "features": tenant.features
        }
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        
        tenant.updated_at = datetime.utcnow()
        
        # Log update
        await self._log_audit_event(
            tenant_id=tenant.id,
            event_type="tenant_updated",
            event_category="lifecycle",
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type="tenant",
            resource_id=str(tenant.id),
            old_values=old_values,
            new_values=updates
        )
        
        self.db.commit()
        self.logger.info(f"Updated tenant: {tenant_id}")
        
        return tenant
    
    async def activate_tenant(
        self,
        tenant_id: str,
        actor_id: str,
        actor_type: str = "user"
    ) -> Tenant:
        """Activate a tenant"""
        
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise TenantError(f"Tenant not found: {tenant_id}")
        
        if tenant.status == TenantStatus.ACTIVE.value:
            return tenant
        
        tenant.status = TenantStatus.ACTIVE.value
        tenant.activated_at = datetime.utcnow()
        tenant.updated_at = datetime.utcnow()
        
        # Log activation
        await self._log_audit_event(
            tenant_id=tenant.id,
            event_type="tenant_activated",
            event_category="lifecycle",
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type="tenant",
            resource_id=str(tenant.id),
            old_values={"status": "pending"},
            new_values={"status": "active"}
        )
        
        self.db.commit()
        self.logger.info(f"Activated tenant: {tenant_id}")
        
        return tenant
    
    async def deactivate_tenant(
        self,
        tenant_id: str,
        reason: Optional[str] = None,
        actor_id: str = "system",
        actor_type: str = "system"
    ) -> Tenant:
        """Deactivate a tenant"""
        
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise TenantError(f"Tenant not found: {tenant_id}")
        
        if tenant.status == TenantStatus.INACTIVE.value:
            return tenant
        
        old_status = tenant.status
        tenant.status = TenantStatus.INACTIVE.value
        tenant.deactivated_at = datetime.utcnow()
        tenant.updated_at = datetime.utcnow()
        
        # Revoke all API keys
        await self._revoke_all_api_keys(tenant_id)
        
        # Log deactivation
        await self._log_audit_event(
            tenant_id=tenant.id,
            event_type="tenant_deactivated",
            event_category="lifecycle",
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type="tenant",
            resource_id=str(tenant.id),
            old_values={"status": old_status},
            new_values={"status": "inactive", "reason": reason}
        )
        
        self.db.commit()
        self.logger.info(f"Deactivated tenant: {tenant_id} (reason: {reason})")
        
        return tenant
    
    async def suspend_tenant(
        self,
        tenant_id: str,
        reason: Optional[str] = None,
        actor_id: str = "system",
        actor_type: str = "system"
    ) -> Tenant:
        """Suspend a tenant temporarily"""
        
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise TenantError(f"Tenant not found: {tenant_id}")
        
        old_status = tenant.status
        tenant.status = TenantStatus.SUSPENDED.value
        tenant.updated_at = datetime.utcnow()
        
        # Log suspension
        await self._log_audit_event(
            tenant_id=tenant.id,
            event_type="tenant_suspended",
            event_category="lifecycle",
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type="tenant",
            resource_id=str(tenant.id),
            old_values={"status": old_status},
            new_values={"status": "suspended", "reason": reason}
        )
        
        self.db.commit()
        self.logger.warning(f"Suspended tenant: {tenant_id} (reason: {reason})")
        
        return tenant
    
    async def add_user_to_tenant(
        self,
        tenant_id: str,
        user_id: str,
        role: str = "member",
        permissions: Optional[List[str]] = None,
        actor_id: str = "system"
    ) -> TenantUser:
        """Add a user to a tenant"""
        
        # Check if user already exists
        stmt = select(TenantUser).where(
            and_(TenantUser.tenant_id == tenant_id, TenantUser.user_id == user_id)
        )
        existing = self.db.execute(stmt).scalar_one_or_none()
        
        if existing:
            raise TenantError(f"User {user_id} already belongs to tenant {tenant_id}")
        
        # Create tenant user
        tenant_user = TenantUser(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            permissions=permissions or [],
            joined_at=datetime.utcnow()
        )
        
        self.db.add(tenant_user)
        
        # Log addition
        await self._log_audit_event(
            tenant_id=tenant_id,
            event_type="user_added",
            event_category="access",
            actor_id=actor_id,
            actor_type="system",
            resource_type="tenant_user",
            resource_id=str(tenant_user.id),
            new_values={"user_id": user_id, "role": role}
        )
        
        self.db.commit()
        self.logger.info(f"Added user {user_id} to tenant {tenant_id}")
        
        return tenant_user
    
    async def remove_user_from_tenant(
        self,
        tenant_id: str,
        user_id: str,
        actor_id: str = "system"
    ) -> bool:
        """Remove a user from a tenant"""
        
        stmt = select(TenantUser).where(
            and_(TenantUser.tenant_id == tenant_id, TenantUser.user_id == user_id)
        )
        tenant_user = self.db.execute(stmt).scalar_one_or_none()
        
        if not tenant_user:
            return False
        
        # Store for audit
        old_values = {
            "user_id": user_id,
            "role": tenant_user.role,
            "permissions": tenant_user.permissions
        }
        
        self.db.delete(tenant_user)
        
        # Log removal
        await self._log_audit_event(
            tenant_id=tenant_id,
            event_type="user_removed",
            event_category="access",
            actor_id=actor_id,
            actor_type="system",
            resource_type="tenant_user",
            resource_id=str(tenant_user.id),
            old_values=old_values
        )
        
        self.db.commit()
        self.logger.info(f"Removed user {user_id} from tenant {tenant_id}")
        
        return True
    
    async def create_api_key(
        self,
        tenant_id: str,
        name: str,
        permissions: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
        allowed_ips: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        created_by: str = "system"
    ) -> TenantApiKey:
        """Create a new API key for a tenant"""
        
        # Generate secure key
        key_id = f"ak_{secrets.token_urlsafe(16)}"
        api_key = f"ask_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_prefix = api_key[:8]
        
        # Create API key record
        api_key_record = TenantApiKey(
            tenant_id=tenant_id,
            key_id=key_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            permissions=permissions or [],
            rate_limit=rate_limit,
            allowed_ips=allowed_ips,
            expires_at=expires_at,
            created_by=created_by
        )
        
        self.db.add(api_key_record)
        self.db.flush()
        
        # Log creation
        await self._log_audit_event(
            tenant_id=tenant_id,
            event_type="api_key_created",
            event_category="security",
            actor_id=created_by,
            actor_type="user",
            resource_type="api_key",
            resource_id=str(api_key_record.id),
            new_values={
                "key_id": key_id,
                "name": name,
                "permissions": permissions,
                "rate_limit": rate_limit
            }
        )
        
        self.db.commit()
        self.logger.info(f"Created API key {key_id} for tenant {tenant_id}")
        
        # Return the key (only time it's shown)
        api_key_record.api_key = api_key
        return api_key_record
    
    async def revoke_api_key(
        self,
        tenant_id: str,
        key_id: str,
        actor_id: str = "system"
    ) -> bool:
        """Revoke an API key"""
        
        stmt = select(TenantApiKey).where(
            and_(
                TenantApiKey.tenant_id == tenant_id,
                TenantApiKey.key_id == key_id,
                TenantApiKey.is_active == True
            )
        )
        api_key = self.db.execute(stmt).scalar_one_or_none()
        
        if not api_key:
            return False
        
        api_key.is_active = False
        api_key.revoked_at = datetime.utcnow()
        
        # Log revocation
        await self._log_audit_event(
            tenant_id=tenant_id,
            event_type="api_key_revoked",
            event_category="security",
            actor_id=actor_id,
            actor_type="user",
            resource_type="api_key",
            resource_id=str(api_key.id),
            old_values={"key_id": key_id, "is_active": True}
        )
        
        self.db.commit()
        self.logger.info(f"Revoked API key {key_id} for tenant {tenant_id}")
        
        return True
    
    async def get_tenant_usage(
        self,
        tenant_id: str,
        resource_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get usage statistics for a tenant"""
        
        from ..models.multitenant import UsageRecord
        
        # Default to last 30 days
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Build query
        stmt = select(
            UsageRecord.resource_type,
            func.sum(UsageRecord.quantity).label("total_quantity"),
            func.sum(UsageRecord.total_cost).label("total_cost"),
            func.count(UsageRecord.id).label("record_count")
        ).where(
            and_(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.usage_start >= start_date,
                UsageRecord.usage_end <= end_date
            )
        )
        
        if resource_type:
            stmt = stmt.where(UsageRecord.resource_type == resource_type)
        
        stmt = stmt.group_by(UsageRecord.resource_type)
        
        results = self.db.execute(stmt).all()
        
        # Format results
        usage = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "by_resource": {}
        }
        
        for result in results:
            usage["by_resource"][result.resource_type] = {
                "quantity": float(result.total_quantity),
                "cost": float(result.total_cost),
                "records": result.record_count
            }
        
        return usage
    
    async def get_tenant_quotas(self, tenant_id: str) -> List[TenantQuota]:
        """Get all quotas for a tenant"""
        
        stmt = select(TenantQuota).where(
            and_(
                TenantQuota.tenant_id == tenant_id,
                TenantQuota.is_active == True
            )
        )
        
        return self.db.execute(stmt).scalars().all()
    
    async def check_quota(
        self,
        tenant_id: str,
        resource_type: str,
        quantity: float
    ) -> bool:
        """Check if tenant has sufficient quota for a resource"""
        
        # Get current quota
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
        
        if not quota:
            # No quota set, deny by default
            return False
        
        # Check if usage + quantity exceeds limit
        if quota.used_value + quantity > quota.limit_value:
            raise QuotaExceededError(
                f"Quota exceeded for {resource_type}: "
                f"{quota.used_value + quantity}/{quota.limit_value}"
            )
        
        return True
    
    async def update_quota_usage(
        self,
        tenant_id: str,
        resource_type: str,
        quantity: float
    ):
        """Update quota usage for a tenant"""
        
        # Get current quota
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
        
        if quota:
            quota.used_value += quantity
            self.db.commit()
    
    # Private methods
    
    def _generate_slug(self, name: str) -> str:
        """Generate a unique slug from name"""
        import re
        # Convert to lowercase and replace spaces with hyphens
        base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        # Add random suffix for uniqueness
        suffix = secrets.token_urlsafe(4)
        return f"{base}-{suffix}"
    
    async def _tenant_exists(self, slug: Optional[str] = None, domain: Optional[str] = None) -> bool:
        """Check if tenant exists by slug or domain"""
        
        conditions = []
        if slug:
            conditions.append(Tenant.slug == slug)
        if domain:
            conditions.append(Tenant.domain == domain)
        
        if not conditions:
            return False
        
        stmt = select(func.count(Tenant.id)).where(or_(*conditions))
        count = self.db.execute(stmt).scalar()
        
        return count > 0
    
    async def _create_default_quotas(self, tenant_id: str, plan: str):
        """Create default quotas based on plan"""
        
        # Define quota templates by plan
        quota_templates = {
            "trial": {
                "gpu_hours": {"limit": 100, "period": "monthly"},
                "storage_gb": {"limit": 10, "period": "monthly"},
                "api_calls": {"limit": 10000, "period": "monthly"}
            },
            "basic": {
                "gpu_hours": {"limit": 500, "period": "monthly"},
                "storage_gb": {"limit": 100, "period": "monthly"},
                "api_calls": {"limit": 100000, "period": "monthly"}
            },
            "pro": {
                "gpu_hours": {"limit": 2000, "period": "monthly"},
                "storage_gb": {"limit": 1000, "period": "monthly"},
                "api_calls": {"limit": 1000000, "period": "monthly"}
            },
            "enterprise": {
                "gpu_hours": {"limit": 10000, "period": "monthly"},
                "storage_gb": {"limit": 10000, "period": "monthly"},
                "api_calls": {"limit": 10000000, "period": "monthly"}
            }
        }
        
        quotas = quota_templates.get(plan, quota_templates["trial"])
        
        # Create quota records
        now = datetime.utcnow()
        period_end = now.replace(day=1) + timedelta(days=32)  # Next month
        period_end = period_end.replace(day=1) - timedelta(days=1)  # Last day of current month
        
        for resource_type, config in quotas.items():
            quota = TenantQuota(
                tenant_id=tenant_id,
                resource_type=resource_type,
                limit_value=config["limit"],
                used_value=0,
                period_type=config["period"],
                period_start=now,
                period_end=period_end
            )
            self.db.add(quota)
    
    async def _revoke_all_api_keys(self, tenant_id: str):
        """Revoke all API keys for a tenant"""
        
        stmt = update(TenantApiKey).where(
            and_(
                TenantApiKey.tenant_id == tenant_id,
                TenantApiKey.is_active == True
            )
        ).values(
            is_active=False,
            revoked_at=datetime.utcnow()
        )
        
        self.db.execute(stmt)
    
    async def _log_audit_event(
        self,
        tenant_id: str,
        event_type: str,
        event_category: str,
        actor_id: str,
        actor_type: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log an audit event"""
        
        audit_log = TenantAuditLog(
            tenant_id=tenant_id,
            event_type=event_type,
            event_category=event_category,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=old_values,
            new_values=new_values,
            metadata=metadata
        )
        
        self.db.add(audit_log)
