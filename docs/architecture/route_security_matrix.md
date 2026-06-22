# AITBC Route Security Matrix

## Overview
This document catalogs the authentication and authorization patterns used across AITBC applications to identify inconsistencies and plan normalization.

## Current Auth Patterns by Application

### Coordinator API
**Location**: `apps/coordinator-api/src/app/deps.py`
**Auth Method**: API Key Validation
**Implementation**:
- `require_client_key()` - Client API key via X-Api-Key header
- `require_miner_key()` - Miner API key via X-Api-Key header
- `require_admin_key()` - Admin API key via X-Api-Key header
- `get_miner_id()` - Miner ID via X-Miner-ID header
- Legacy `APIKeyValidator` class for backward compatibility

**Security Level**: Medium (API keys, no JWT support)
**Environment Check**: Bypasses validation in dev mode (APP_ENV=dev)

### Agent Coordinator
**Location**: `apps/agent-coordinator/src/app/auth/`
**Auth Method**: JWT + API Key
**Implementation**:
- `jwt_handler.py` - JWT token generation and validation
- `middleware.py` - Auth middleware for request interception
- `routers/auth.py` - Auth endpoints for token management

**Security Level**: High (JWT with refresh tokens)
**Features**: Token expiry, refresh tokens, secret key management

### Agent Management
**Location**: `apps/agent-management/src/app/deps.py`
**Auth Method**: API Key Validation
**Implementation**: Similar to coordinator-api pattern
**Security Level**: Medium

### Exchange
**Location**: `apps/exchange/exchange_api.py`
**Auth Method**: API Key + JWT
**Implementation**: Mixed pattern with both API key and JWT support
**Security Level**: High

### Wallet
**Location**: `apps/wallet/src/app/main.py`
**Auth Method**: API Key
**Implementation**: Coordinator API key validation
**Security Level**: Medium

### Edge API
**Location**: `apps/edge/src/aitbc_edge/config.py`
**Auth Method**: JWT
**Implementation**: JWT secret key configuration
**Security Level**: High

## Inconsistencies Identified

### 1. Mixed Auth Methods
- **Coordinator API**: API keys only
- **Agent Coordinator**: JWT + API keys
- **Exchange**: API keys + JWT
- **Edge**: JWT only
- **Others**: API keys only

### 2. Environment Bypasses
- Coordinator API bypasses auth in dev mode (`APP_ENV=dev`)
- This creates security risk if dev config is accidentally used in production

### 3. Header Inconsistencies
- Most use `X-Api-Key` header
- Some use `Authorization: Bearer` for JWT
- Miner ID uses `X-Miner-ID` header

### 4. Secret Management
- Different secret key storage methods across apps
- Some use environment variables, some use config files
- No centralized secret rotation strategy

### 5. Token Management
- Only Agent Coordinator and Exchange have refresh token support
- Other apps lack token refresh mechanisms
- No standardized token expiry times

## Proposed Normalization Strategy

### Phase 1: Unified Auth Library
Create shared auth library in `aitbc/auth/`:
- `jwt_handler.py` - Standardized JWT implementation
- `api_key_handler.py` - Standardized API key validation
- `middleware.py` - Auth middleware for FastAPI
- `dependencies.py` - FastAPI dependency functions

### Phase 2: Security Levels
Define clear security levels:
- **Level 1 (Public)**: No auth required (health checks, public docs)
- **Level 2 (API Key)**: API key authentication (basic operations)
- **Level 3 (JWT)**: JWT authentication (user operations)
- **Level 4 (Admin)**: Admin API key + JWT (admin operations)

### Phase 3: Route Security Matrix
Document required auth level for each route:
```
Route                          | Method | Auth Level | Implementation
-------------------------------|--------|------------|----------------
/v1/health                    | GET    | Level 1    | None
/v1/miners/register          | POST   | Level 2    | API Key
/v1/jobs/submit              | POST   | Level 3    | JWT
/v1/admin/users              | GET    | Level 4    | Admin Key + JWT
```

### Phase 4: Migration Path
1. Deploy shared auth library
2. Update apps to use shared library
3. Remove environment bypasses
4. Standardize header names
5. Implement secret rotation
6. Add monitoring for auth failures

## Implementation Priority

### High Priority (Security Critical)
1. Remove dev mode auth bypass
2. Standardize secret management
3. Add auth failure monitoring
4. Implement rate limiting on auth endpoints

### Medium Priority (Consistency)
1. Create shared auth library
2. Standardize header names
3. Document route security matrix
4. Add token refresh support

### Low Priority (Enhancement)
1. Add OAuth2 support
2. Implement multi-factor auth
3. Add audit logging for auth events
4. Implement session management

## Dependencies
- Requires coordination with Agent B's feature flags (Goal 13)
- Should follow duplicate route removal (Goal 32)
- Depends on configuration normalization (Agent B Goal 2)

## Success Criteria
- [ ] All apps use shared auth library
- [ ] No environment-based auth bypasses
- [ ] Consistent header names across all apps
- [ ] Documented security matrix for all routes
- [ ] Auth failure monitoring in place
- [ ] Secret rotation strategy implemented
