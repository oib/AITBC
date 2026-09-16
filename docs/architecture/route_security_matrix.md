# AITBC Route Security Matrix

## Overview

This document catalogs the authentication and authorization patterns used across AITBC applications.

> **Status update (implemented):** the shared auth library proposed below **exists and is in use** — `aitbc/auth/` provides `jwt.py` (`create_access_token`/`verify_access_token`), `api_key.py` (`APIKeyManager` digest store), `dependencies.py` (`require_auth`, `require_admin`, `require_client`, `require_admin_or_client`, `require_miner`, `APIKeyAuthenticator`, `AuthDep`/`AdminDep`/`ClientDep`/`AdminOrClientDep`/`MinerDep` type aliases), `middleware.py`, `permissions.py`, and `security_matrix.py`. Applications import it directly or through a thin shim (e.g. `coordinator_api/auth/__init__.py`).

## Current Auth Patterns by Application

### Coordinator API

**Location**: `apps/coordinator-api/src/coordinator_api/auth/` (shim re-exporting `aitbc/auth/`)
**Auth Method**: JWT Bearer (canonical for customers) + `X-Api-Key` for service/legacy callers
**Implementation**:

- `require_admin_or_client` / `AdminOrClientDep` — `Authorization: Bearer <jwt>` with admin or client role (job submission, payments)
- `require_miner` / `MinerDep` — Bearer JWT first, falls back to `X-Api-Key` (miner register/heartbeat/poll/result)
- `require_admin` / `AdminDep` — Bearer JWT, admin role
- `APIKeyAuthenticator` — `X-Api-Key` header for service callers (configurable `auth_enabled`)
- JWTs are issued by the wallet-signed login flow (`POST /v1/auth/nonce` → `POST /v1/login`)

**Security Level**: High (JWT canonical; API key fallback for service/miner callers)

### Agent Coordinator

**Location**: `apps/agent-coordinator/src/agent_app/` (`routers/auth.py`, `routers/agent_auth.py`, `services/agent_auth.py`)
**Auth Method**: JWT + API Key (via shared `aitbc/auth`)
**Implementation**:

- `routers/auth.py` — token generation/validation/refresh via `aitbc.auth.get_jwt_handler()` and API-key issue/validate/revoke via `aitbc.auth.api_key_manager`

**Security Level**: High (JWT with refresh tokens)
**Features**: Token expiry, refresh tokens, secret key management

> **Note:** `apps/agent-management` was removed from the current checkout. Agent lifecycle and SDK commands now live in the CLI and `apps/agent-coordinator`.

### Exchange

**Location**: `apps/exchange/simple_exchange/` (`server.py`, `main.py`, handlers)
**Auth Method**: API Key (write auth in `ExchangeAPIHandler._require_api_key`)
**Security Level**: Medium

### Wallet

**Location**: `apps/wallet/src/wallet_app/main.py`
**Auth Method**: API Key (`X-API-Key` daemon auth via `settings.api_key`, gated by `auth_enabled`)
**Security Level**: Medium

### Edge API

**Location**: `apps/edge/src/aitbc_edge/config.py`
**Auth Method**: JWT
**Implementation**: JWT secret key configuration
**Security Level**: High

## Current State vs. Earlier Findings

### 1. Mixed Auth Methods (current state)

- **Coordinator API**: JWT Bearer canonical for customers + `X-Api-Key` for service/legacy/miner callers (`require_miner` accepts either)
- **Agent Coordinator**: JWT + API keys (shared `aitbc/auth`)
- **Exchange**: API key on write paths
- **Edge**: JWT only
- **Blockchain node**: `X-API-Key` on admin/control mutations (contracts deploy, governance, escrow router-level, GPU/identity writes, chain control), **tx-signature auth** on `/rpc/transaction` + `/rpc/staking/stake`, peer keys on subscription routes, admin signature on `/rpc/force-sync`
- **Marketplace**: one admin route key-gated

### 2. Environment Bypasses

- `APIKeyAuthenticator` succeeds unconditionally when `auth_enabled` is false — several services expose this flag; it must stay `true` in production

### 3. Header Conventions

- `Authorization: Bearer <jwt>` — customer/user JWT paths
- `X-Api-Key` — coordinator service/legacy, marketplace admin (`APIKeyAuthenticator` default header)
- `X-API-Key` — blockchain node admin/control mutations + escrow + peer subscription routes (tx submit/stake are signature-verified instead)
- The casing difference is real and per-service; both are matched case-insensitively by HTTP headers, but document the exact header each service expects.

### 4. Secret Management

- Env files under `/etc/aitbc/*.env` (mode `0600`, systemd `EnvironmentFile`) + `API_KEY_STORAGE_PATH` digest store for issued keys
- No centralized rotation; rotation is manual per service

### 5. Token Management

- Agent Coordinator has refresh-token support; the coordinator-api issues JWT access tokens via the wallet login flow
- No standardized token expiry times across apps

## Normalization — Implemented State

### Phase 1: Unified Auth Library — ✅ implemented

The shared auth library exists at `aitbc/auth/` and is in use:

- `jwt.py` — `create_access_token` / `verify_access_token` (+ `JWTHandler`/`get_jwt_handler` for the agent-coordinator refresh-token flow)
- `api_key.py` — `APIKeyManager`/`api_key_manager` digest-backed key store
- `dependencies.py` — `require_auth`, `require_admin`, `require_client`, `require_admin_or_client`, `require_miner`, `APIKeyAuthenticator`, and `*Dep` injection aliases
- `middleware.py`, `permissions.py`, `security_matrix.py`

### Phase 2: Security Levels

Define clear security levels:

- **Level 1 (Public)**: No auth required (health checks, public docs)
- **Level 2 (API Key)**: API key authentication (basic operations)
- **Level 3 (JWT)**: JWT authentication (user operations)
- **Level 4 (Admin)**: Admin API key + JWT (admin operations)

### Phase 3: Route Security Matrix — partially implemented

Real route/auth pairs today:

```
Route                          | Method | Auth Level | Implementation
-------------------------------|--------|------------|----------------
/health, /metrics             | GET    | Level 1    | None
/v1/miners/register           | POST   | Level 2/3  | MinerDep (JWT or X-Api-Key)
/v1/jobs                      | POST   | Level 3    | AdminOrClientDep (JWT)
/rpc/transaction              | POST   | Level 2    | Tx `signature` verified against `from` (no API key)
/rpc/escrow/*                 | ALL    | Level 2    | X-API-Key (router-level)
/rpc/subscribe, /rpc/heartbeat| POST   | Peer key   | verify_rpc_peer_key
/rpc/force-sync               | POST   | Level 4    | admin-signed body
/v1/marketplace/parameters/apply | POST | Level 2 | X-Api-Key (marketplace api_key)
```

### Phase 4: Migration Path — status

1. ~~Deploy shared auth library~~ — done (`aitbc/auth/`)
2. Update apps to use shared library — in progress (coordinator + agent-coordinator on it; blockchain node keeps its own `verify_rpc_api_key`/`verify_rpc_peer_key` for peer semantics)
3. Remove environment bypasses — open (`auth_enabled` flags still exist)
4. Standardize header names — open (`X-Api-Key` vs `X-API-Key` differ by service)
5. Implement secret rotation — manual only
6. Add monitoring for auth failures — open

## Implementation Priority

### High Priority (Security Critical)

1. Remove dev mode auth bypass
2. Standardize secret management
3. Add auth failure monitoring
4. Implement rate limiting on auth endpoints

### Medium Priority (Consistency)

1. ~~Create shared auth library~~ — done
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

- [x] Shared auth library exists (`aitbc/auth/`) — rollout to all apps ongoing
- [ ] No environment-based auth bypasses (`auth_enabled` flags still exist)
- [ ] Consistent header names across all apps
- [ ] Documented security matrix for all routes
- [ ] Auth failure monitoring in place
- [ ] Secret rotation strategy implemented
