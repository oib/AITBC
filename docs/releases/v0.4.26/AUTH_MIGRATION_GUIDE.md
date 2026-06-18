# Authentication Migration Guide: API Keys to JWT

## Overview

This guide documents the migration from API key-based authentication to JWT-based authentication for the Coordinator API.

## Current State

### Existing API Key Auth

- Located in `apps/coordinator-api/src/app/deps.py`
- Functions:
  - `require_client_key()` - Client API key validation
  - `require_miner_key()` - Miner API key validation
  - `require_admin_key()` - Admin API key validation
  - `get_miner_id()` - Miner ID from header
- Uses `X-Api-Key` header
- Dev mode bypasses validation

### New JWT Auth

- Located in `apps/coordinator-api/src/app/auth/`
- Components:
  - `jwt_auth.py` - JWT encoding/decoding/validation
  - `dependencies.py` - Role-based auth dependencies
  - `security_matrix.py` - Route security matrix
  - `middleware.py` - Auth middleware for automatic protection
- Uses `Authorization: Bearer <token>` header
- Supports roles: admin, client, miner
- Configurable via `config_pg.py` (JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS)

## Migration Strategy

### Phase 1: Parallel Operation (Current)

Both API key and JWT auth will work in parallel during the transition period.

**Status**: ✅ JWT infrastructure created, ready for parallel operation

### Phase 2: Gradual Router Migration

Migrate routers from API key auth to JWT auth incrementally:

1. **Low-risk routers first**:
   - Health check endpoints (already public)
   - Documentation endpoints (already public)
   - Read-only endpoints

2. **Medium-risk routers**:
   - Client-facing endpoints
   - Miner-facing endpoints
   - Analytics endpoints

3. **High-risk routers**:
   - Admin endpoints
   - Financial endpoints
   - Critical infrastructure endpoints

### Phase 3: Deprecation

After all routers are migrated:
1. Add deprecation warnings to API key auth
2. Document migration deadline
3. Remove API key auth after grace period

## Router Migration Steps

### Step 1: Update Router Imports

**Before**:
```python
from ..deps import require_client_key
```

**After**:
```python
from ..auth import ClientDep
```

### Step 2: Update Route Dependencies

**Before**:
```python
@router.get("/jobs")
async def list_jobs(api_key: str = Depends(require_client_key())):
    ...
```

**After**:
```python
@router.get("/jobs")
async def list_jobs(user: dict = ClientDep):
    user_id = user["sub"]
    user_role = user["role"]
    ...
```

### Step 3: Update Token Generation

**Before**:
```python
# API key from environment
api_key = os.getenv("CLIENT_API_KEY")
```

**After**:
```python
from ..auth import create_access_token

token = create_access_token(
    user_id="client-123",
    role="client",
    extra_claims={"permissions": ["jobs:read", "jobs:write"]}
)
```

### Step 4: Update Client Code

**Before**:
```python
headers = {"X-Api-Key": "your-api-key"}
response = requests.get(url, headers=headers)
```

**After**:
```python
headers = {"Authorization": f"Bearer {token}"}
response = requests.get(url, headers=headers)
```

## Token Management

### Creating Tokens

```python
from app.auth import create_access_token

# Create token for client
client_token = create_access_token(
    user_id="client-123",
    role="client"
)

# Create token for miner
miner_token = create_access_token(
    user_id="miner-456",
    role="miner",
    extra_claims={"capabilities": ["gpt2", "llama2"]}
)

# Create token for admin
admin_token = create_access_token(
    user_id="admin-789",
    role="admin"
)
```

### Verifying Tokens

```python
from app.auth import verify_access_token

# Verify token
payload = verify_access_token(token)
user_id = payload["sub"]
role = payload["role"]
```

### Token Expiration

Tokens expire after `JWT_EXPIRATION_HOURS` (default: 24 hours).

Refresh tokens can be implemented by:
1. Issuing a new token before expiration
2. Using refresh tokens (not implemented yet)
3. Re-authenticating with credentials

## Security Matrix

The security matrix defines auth requirements for routes:

```python
from app.auth import get_auth_level, AuthLevel

auth_level = get_auth_level("/routers/admin")
# Returns: AuthLevel.ADMIN

auth_level = get_auth_level("/health")
# Returns: AuthLevel.NONE
```

### Auth Levels

- `NONE`: No authentication required
- `ANY`: Any valid JWT token
- `ADMIN`: Admin role required
- `CLIENT`: Client role required
- `MINER`: Miner role required
- `ADMIN_OR_CLIENT`: Admin or client role

## Middleware Integration

To enable automatic route protection via middleware:

```python
from app.auth import AuthMiddleware

app.add_middleware(AuthMiddleware)
```

**Note**: Middleware is optional. You can also use dependencies per-route.

## Testing

### Test JWT Auth

```python
import pytest
from app.auth import create_access_token, verify_access_token

def test_jwt_auth():
    # Create token
    token = create_access_token("user-123", "client")

    # Verify token
    payload = verify_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "client"

    # Test role verification
    payload = verify_access_token(token, required_role="client")
    assert payload["role"] == "client"

    # Test invalid role
    with pytest.raises(HTTPException):
        verify_access_token(token, required_role="admin")
```

### Test Security Matrix

```python
from app.auth import get_auth_level, AuthLevel

def test_security_matrix():
    assert get_auth_level("/health") == AuthLevel.NONE
    assert get_auth_level("/routers/admin") == AuthLevel.ADMIN
    assert get_auth_level("/routers/client") == AuthLevel.CLIENT
```

## Rollback Plan

If issues arise during migration:

1. **Disable JWT middleware**: Remove `AuthMiddleware` from app
2. **Revert router changes**: Restore API key dependencies
3. **Keep JWT infrastructure**: JWT code remains for future use
4. **Document issues**: Record what went wrong for future reference

## Monitoring

Monitor the following during migration:

1. **Auth failure rates**: Track 401/403 errors
2. **Token usage**: Track JWT vs API key usage
3. **Performance**: Compare latency between auth methods
4. **User feedback**: Collect feedback from API users

## Timeline

- **Week 1**: JWT infrastructure (✅ Complete)
- **Week 2-3**: Parallel operation testing
- **Week 4-6**: Router migration (incremental)
- **Week 7**: Deprecation warnings
- **Week 8**: Remove API key auth

## Success Criteria

- ✅ JWT auth infrastructure created
- ✅ Security matrix documented
- ✅ Role-based dependencies implemented
- ⏳ All routers migrated to JWT
- ⏳ API key auth deprecated
- ⏳ Tests pass for all auth scenarios
- ⏳ Documentation updated
- ⏳ Zero production incidents

## Questions?

For questions about the migration:
1. Review this guide
2. Check `docs/releases/v0.4.26/GOAL_36_AUTH_PLAN.md`
3. Consult with the security team
4. Open an issue for discussion
