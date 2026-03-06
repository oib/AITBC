"""
Tenant context middleware for multi-tenant isolation
"""

import hashlib
from datetime import datetime
from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import event, select, and_
from contextvars import ContextVar

from sqlmodel import SQLModel as Base
from ..models.multitenant import Tenant, TenantApiKey
from ..services.tenant_management import TenantManagementService
from ..exceptions import TenantError
from ..storage.db_pg import get_db


# Context variable for current tenant
current_tenant: ContextVar[Optional[Tenant]] = ContextVar('current_tenant', default=None)
current_tenant_id: ContextVar[Optional[str]] = ContextVar('current_tenant_id', default=None)


def get_current_tenant() -> Optional[Tenant]:
    """Get the current tenant from context"""
    return current_tenant.get()


def get_current_tenant_id() -> Optional[str]:
    """Get the current tenant ID from context"""
    return current_tenant_id.get()


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and set tenant context"""
    
    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/favicon.ico",
            "/static"
        ]
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip tenant extraction for excluded paths
        if self._should_exclude(request.url.path):
            return await call_next(request)
        
        # Extract tenant from request
        tenant = await self._extract_tenant(request)
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant not found or invalid"
            )
        
        # Check tenant status
        if tenant.status not in ["active", "trial"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tenant is {tenant.status}"
            )
        
        # Set tenant context
        current_tenant.set(tenant)
        current_tenant_id.set(str(tenant.id))
        
        # Add tenant to request state for easy access
        request.state.tenant = tenant
        request.state.tenant_id = str(tenant.id)
        
        # Process request
        response = await call_next(request)
        
        # Clear context
        current_tenant.set(None)
        current_tenant_id.set(None)
        
        return response
    
    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded from tenant extraction"""
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                return True
        return False
    
    async def _extract_tenant(self, request: Request) -> Optional[Tenant]:
        """Extract tenant from request using various methods"""
        
        # Method 1: Subdomain
        tenant = await self._extract_from_subdomain(request)
        if tenant:
            return tenant
        
        # Method 2: Custom header
        tenant = await self._extract_from_header(request)
        if tenant:
            return tenant
        
        # Method 3: API key
        tenant = await self._extract_from_api_key(request)
        if tenant:
            return tenant
        
        # Method 4: JWT token (if using OAuth)
        tenant = await self._extract_from_token(request)
        if tenant:
            return tenant
        
        return None
    
    async def _extract_from_subdomain(self, request: Request) -> Optional[Tenant]:
        """Extract tenant from subdomain"""
        host = request.headers.get("host", "").split(":")[0]
        
        # Split hostname to get subdomain
        parts = host.split(".")
        if len(parts) > 2:
            subdomain = parts[0]
            
            # Skip common subdomains
            if subdomain in ["www", "api", "admin", "app"]:
                return None
            
            # Look up tenant by subdomain/slug
            db = next(get_db())
            try:
                service = TenantManagementService(db)
                return await service.get_tenant_by_slug(subdomain)
            finally:
                db.close()
        
        return None
    
    async def _extract_from_header(self, request: Request) -> Optional[Tenant]:
        """Extract tenant from custom header"""
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            return None
        
        db = next(get_db())
        try:
            service = TenantManagementService(db)
            return await service.get_tenant(tenant_id)
        finally:
            db.close()
    
    async def _extract_from_api_key(self, request: Request) -> Optional[Tenant]:
        """Extract tenant from API key"""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        
        api_key = auth_header[7:]  # Remove "Bearer "
        
        # Hash the key to compare with stored hash
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        db = next(get_db())
        try:
            # Look up API key
            stmt = select(TenantApiKey).where(
                and_(
                    TenantApiKey.key_hash == key_hash,
                    TenantApiKey.is_active == True
                )
            )
            api_key_record = db.execute(stmt).scalar_one_or_none()
            
            if not api_key_record:
                return None
            
            # Check if key has expired
            if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
                return None
            
            # Update last used timestamp
            api_key_record.last_used_at = datetime.utcnow()
            db.commit()
            
            # Get tenant
            service = TenantManagementService(db)
            return await service.get_tenant(str(api_key_record.tenant_id))
            
        finally:
            db.close()
    
    async def _extract_from_token(self, request: Request) -> Optional[Tenant]:
        """Extract tenant from JWT token (HS256 signed)."""
        import json, hmac as _hmac, base64 as _b64

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        parts = token.split(".")
        if len(parts) != 3:
            return None

        try:
            # Verify HS256 signature
            secret = request.app.state.jwt_secret if hasattr(request.app.state, "jwt_secret") else ""
            if not secret:
                return None
            expected_sig = _hmac.new(
                secret.encode(), f"{parts[0]}.{parts[1]}".encode(), "sha256"
            ).hexdigest()
            if not _hmac.compare_digest(parts[2], expected_sig):
                return None

            # Decode payload
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(_b64.urlsafe_b64decode(padded))
            tenant_id = payload.get("tenant_id")
            if not tenant_id:
                return None

            db = next(get_db())
            try:
                service = TenantManagementService(db)
                return await service.get_tenant(tenant_id)
            finally:
                db.close()
        except Exception:
            return None


class TenantRowLevelSecurity:
    """Row-level security implementation for tenant isolation"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    def enable_rls(self):
        """Enable row-level security for the session"""
        tenant_id = get_current_tenant_id()
        
        if not tenant_id:
            raise TenantError("No tenant context found")
        
        # Set session variable for PostgreSQL RLS
        self.db.execute(
            "SET SESSION aitbc.current_tenant_id = :tenant_id",
            {"tenant_id": tenant_id}
        )
        
        self.logger.debug(f"Enabled RLS for tenant: {tenant_id}")
    
    def disable_rls(self):
        """Disable row-level security for the session"""
        self.db.execute("RESET aitbc.current_tenant_id")
        self.logger.debug("Disabled RLS")


# Database event listeners for automatic RLS
@event.listens_for(Session, "after_begin")
def on_session_begin(session, transaction):
    """Enable RLS when session begins"""
    try:
        tenant_id = get_current_tenant_id()
        if tenant_id:
            session.execute(
                "SET SESSION aitbc.current_tenant_id = :tenant_id",
                {"tenant_id": tenant_id}
            )
    except Exception as e:
        # Log error but don't fail
        logger = __import__('logging').getLogger(__name__)
        logger.error(f"Failed to set tenant context: {e}")


# Decorator for tenant-aware endpoints
def requires_tenant(func):
    """Decorator to ensure tenant context is present"""
    async def wrapper(*args, **kwargs):
        tenant = get_current_tenant()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant context required"
            )
        return await func(*args, **kwargs)
    return wrapper


# Dependency for FastAPI
async def get_current_tenant_dependency(request: Request) -> Tenant:
    """FastAPI dependency to get current tenant"""
    tenant = getattr(request.state, "tenant", None)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant not found"
        )
    return tenant


# Utility functions
def with_tenant_context(tenant_id: str):
    """Execute code with specific tenant context"""
    token = current_tenant_id.set(tenant_id)
    try:
        yield
    finally:
        current_tenant_id.reset(token)


def is_tenant_admin(user_permissions: list) -> bool:
    """Check if user has tenant admin permissions"""
    return "tenant:admin" in user_permissions or "admin" in user_permissions


def has_tenant_permission(permission: str, user_permissions: list) -> bool:
    """Check if user has specific tenant permission"""
    return permission in user_permissions or "tenant:admin" in user_permissions
