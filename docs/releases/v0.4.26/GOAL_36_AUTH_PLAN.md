# Goal 36: Normalize Auth (Route Security Matrix + JWT Support) - Implementation Plan

## Current State Analysis

### Existing Auth Infrastructure

1. **Basic Auth Module** (`apps/coordinator-api/src/app/auth.py`)
   - Currently just returns "test-key" - placeholder implementation
   - Needs to be replaced with proper JWT-based auth

2. **Dependency Injection** (`apps/coordinator-api/src/app/deps.py`)
   - `require_client_key()` - Client API key validation
   - `require_miner_key()` - Miner API key validation
   - `require_admin_key()` - Admin API key validation
   - `get_miner_id()` - Miner ID from header
   - `APIKeyValidator` - Legacy validator class
   - Uses X-Api-Key header for authentication
   - Dev mode bypasses validation

3. **JWT Configuration** (`apps/coordinator-api/src/app/config_pg.py`)
   - `jwt_secret` - Required environment variable
   - `jwt_algorithm` - HS256
   - `jwt_expiration_hours` - 24 hours
   - Validation on import ensures secret is set and not default

4. **Current Auth Usage**
   - 69 files in coordinator-api use Depends/dependency
   - Mix of API key-based auth across different contexts
   - No centralized auth matrix
   - Inconsistent auth patterns across routers

### Problems Identified

1. **No JWT Implementation**: JWT config exists but no actual JWT encoding/decoding/validation
2. **Inconsistent Auth**: Different routers use different auth patterns
3. **No Security Matrix**: No documentation of which routes require which auth level
4. **API Key Only**: Currently only supports API keys, no JWT tokens
5. **No Role-Based Access**: No concept of roles (admin, client, miner, etc.) in JWT
6. **Dev Mode Bypass**: Dev mode bypasses all auth validation (security risk)

## Implementation Plan

### Phase 1: Create JWT Auth Module

**File**: `apps/coordinator-api/src/app/auth/jwt_auth.py`

```python
"""
JWT-based authentication module for Coordinator API
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt

from ..config_pg import settings


class JWTAuth:
    """JWT authentication handler"""

    def __init__(self):
        self.secret = settings.jwt_secret
        self.algorithm = settings.jwt_algorithm
        self.expiration_hours = settings.jwt_expiration_hours

    def create_token(self, payload: dict[str, Any]) -> str:
        """Create JWT token with expiration"""
        expire = datetime.utcnow() + timedelta(hours=self.expiration_hours)
        to_encode = payload.copy()
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret, algorithm=self.algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode and validate JWT token"""
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

    def verify_token(self, token: str, required_role: str | None = None) -> dict[str, Any]:
        """Verify token and optionally check role"""
        payload = self.decode_token(token)
        if required_role and payload.get("role") != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return payload


# Global JWT auth instance
jwt_auth = JWTAuth()


def create_access_token(user_id: str, role: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create access token for user"""
    payload = {"sub": user_id, "role": role}
    if extra_claims:
        payload.update(extra_claims)
    return jwt_auth.create_token(payload)


def verify_access_token(token: str, required_role: str | None = None) -> dict[str, Any]:
    """Verify access token and return payload"""
    return jwt_auth.verify_token(token, required_role)
```

### Phase 2: Create Role-Based Auth Dependencies

**File**: `apps/coordinator-api/src/app/auth/dependencies.py`

```python
"""
Role-based authentication dependencies
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from .jwt_auth import verify_access_token


def get_token(authorization: str | None = Header(default=None, alias="Authorization")) -> str:
    """Extract Bearer token from Authorization header"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[7:]  # Remove "Bearer " prefix


def require_auth() -> dict[str, Any]:
    """Require valid JWT token (any role)"""
    token = get_token()
    return verify_access_token(token)


def require_admin() -> dict[str, Any]:
    """Require admin role"""
    token = get_token()
    return verify_access_token(token, required_role="admin")


def require_client() -> dict[str, Any]:
    """Require client role"""
    token = get_token()
    return verify_access_token(token, required_role="client")


def require_miner() -> dict[str, Any]:
    """Require miner role"""
    token = get_token()
    return verify_access_token(token, required_role="miner")


# Type aliases for dependency injection
AuthDep = Annotated[dict[str, Any], Depends(require_auth)]
AdminDep = Annotated[dict[str, Any], Depends(require_admin)]
ClientDep = Annotated[dict[str, Any], Depends(require_client)]
MinerDep = Annotated[dict[str, Any], Depends(require_miner)]
```

### Phase 3: Create Route Security Matrix

**File**: `apps/coordinator-api/src/app/auth/security_matrix.py`

```python
"""
Route security matrix - defines auth requirements for all routes
"""

from enum import Enum
from typing import Literal


class AuthLevel(Enum):
    """Authentication levels"""
    NONE = "none"  # No authentication required
    ANY = "any"  # Any valid JWT token
    ADMIN = "admin"  # Admin role required
    CLIENT = "client"  # Client role required
    MINER = "miner"  # Miner role required
    ADMIN_OR_CLIENT = "admin_or_client"  # Admin or client role


# Route security matrix
# Format: {"router:path": AuthLevel}
ROUTE_SECURITY_MATRIX = {
    # Public routes
    "/health": AuthLevel.NONE,
    "/docs": AuthLevel.NONE,
    "/openapi.json": AuthLevel.NONE,

    # Admin routes
    "/admin/*": AuthLevel.ADMIN,
    "/routers/admin": AuthLevel.ADMIN,

    # Client routes
    "/routers/client": AuthLevel.CLIENT,
    "/contexts/certification/*": AuthLevel.CLIENT,
    "/contexts/trading/*": AuthLevel.CLIENT,

    # Miner routes
    "/routers/miner": AuthLevel.MINER,
    "/contexts/marketplace/*": AuthLevel.MINER,

    # Mixed auth routes
    "/contexts/agent_coordination/*": AuthLevel.ANY,
    "/contexts/hermes/*": AuthLevel.ANY,
}


def get_auth_level(path: str) -> AuthLevel:
    """Get required auth level for a given path"""
    # Check exact match first
    if path in ROUTE_SECURITY_MATRIX:
        return ROUTE_SECURITY_MATRIX[path]

    # Check prefix matches
    for pattern, level in ROUTE_SECURITY_MATRIX.items():
        if pattern.endswith("*") and path.startswith(pattern[:-1]):
            return level

    # Default to requiring auth
    return AuthLevel.ANY
```

### Phase 4: Create Auth Middleware

**File**: `apps/coordinator-api/src/app/auth/middleware.py`

```python
"""
Auth middleware for automatic route protection
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .security_matrix import get_auth_level
from .jwt_auth import verify_access_token


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce auth requirements based on route security matrix"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip auth for public routes
        from .security_matrix import AuthLevel

        auth_level = get_auth_level(path)
        if auth_level == AuthLevel.NONE:
            return await call_next(request)

        # Extract token from Authorization header
        authorization = request.headers.get("Authorization")
        if not authorization:
            return Response(
                status_code=401,
                content='{"detail": "Authorization header required"}',
                media_type="application/json",
            )

        if not authorization.startswith("Bearer "):
            return Response(
                status_code=401,
                content='{"detail": "Invalid authorization header format"}',
                media_type="application/json",
            )

        token = authorization[7:]

        try:
            # Verify token
            payload = verify_access_token(token)

            # Check role if required
            if auth_level != AuthLevel.ANY:
                required_role = auth_level.value
                if payload.get("role") != required_role:
                    return Response(
                        status_code=403,
                        content=f'{{"detail": "Role \'{required_role}\' required"}}',
                        media_type="application/json",
                    )

            # Add user info to request state
            request.state.user = payload
            request.state.user_id = payload.get("sub")
            request.state.user_role = payload.get("role")

        except Exception as e:
            return Response(
                status_code=401,
                content=f'{{"detail": "Invalid token: {str(e)}"}}',
                media_type="application/json",
            )

        return await call_next(request)
```

### Phase 5: Migration Strategy

1. **Gradual Migration**:
   - Keep existing API key auth in parallel with JWT
   - Add JWT support to new routes first
   - Gradually migrate existing routes
   - Deprecate API key auth after migration complete

2. **Backward Compatibility**:
   - Support both API key and JWT auth during transition
   - API key auth uses existing deps.py functions
   - JWT auth uses new auth/dependencies.py functions
   - Deprecation warnings for API key auth

3. **Testing**:
   - Add tests for JWT encoding/decoding
   - Add tests for role-based access control
   - Add tests for auth middleware
   - Test migration of each router

### Phase 6: Router Migration Order

1. **Low-risk routers first**:
   - Health check endpoints
   - Documentation endpoints
   - Read-only endpoints

2. **Medium-risk routers**:
   - Client-facing endpoints
   - Miner-facing endpoints
   - Analytics endpoints

3. **High-risk routers**:
   - Admin endpoints
   - Financial endpoints
   - Critical infrastructure endpoints

### Phase 7: Coordination with Agent B

**Agent B Goal 13**: Optional routers behind flags

**Coordination Points**:
1. Auth normalization should happen BEFORE optional router flags
2. Security matrix should account for optional routers
3. JWT auth should work with feature flags
4. Test both auth and feature flags together

## Success Criteria

- [x] JWT auth module created and tested
- [ ] Role-based auth dependencies created
- [ ] Route security matrix documented
- [ ] Auth middleware implemented
- [ ] All routers migrated to JWT auth
- [ ] API key auth deprecated
- [ ] Tests pass for all auth scenarios
- [ ] Documentation updated
- [ ] Coordination with Agent B complete

## Estimated Effort

- Phase 1 (JWT Module): 1 day
- Phase 2 (Auth Dependencies): 0.5 day
- Phase 3 (Security Matrix): 0.5 day
- Phase 4 (Auth Middleware): 1 day
- Phase 5 (Migration Strategy): 0.5 day
- Phase 6 (Router Migration): 3-5 days
- Phase 7 (Agent B Coordination): 1 day
- Testing & Documentation: 2 days

**Total**: 9.5-11.5 days

## Notes

- This is a large, complex task requiring coordination
- Should be done incrementally to minimize risk
- Requires thorough testing before deployment
- Should coordinate with Agent B's optional router flags work
- Consider feature flag for JWT auth rollout
