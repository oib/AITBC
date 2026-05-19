# Rate Limiting Implementation Guide

## Overview

Rate limiting has been implemented for AITBC API endpoints to prevent abuse and ensure fair resource allocation. This guide explains how to apply rate limiting to FastAPI routers.

## Infrastructure

### Rate Limiting Module

Location: `/opt/aitbc/aitbc/rate_limiting.py`

The module provides:
- `@rate_limit()` decorator for endpoint-level rate limiting
- `RateLimitMiddleware` for global middleware-based rate limiting
- Helper functions for managing rate limiters

### Rate Limiter Implementation

The underlying `RateLimiter` class in `aitbc/security_hardening.py` implements a token bucket algorithm.

## Applying Rate Limiting to Routers

### Step 1: Import the decorator

```python
from fastapi import Request
from aitbc.rate_limiting import rate_limit
```

### Step 2: Add Request parameter

Add `request: Request` as the first parameter (after any path parameters) to each endpoint:

```python
@router.post("/workflows")
async def create_workflow(
    request: Request,  # Add this
    workflow_data: AgentWorkflowCreate,
    session: Session = Depends(...),
    current_user: str = Depends(...),
):
    ...
```

### Step 3: Apply the decorator

Add the `@rate_limit` decorator before the endpoint:

```python
@router.post("/workflows")
@rate_limit(rate=100, per=60)  # 100 requests per minute
async def create_workflow(
    request: Request,
    workflow_data: AgentWorkflowCreate,
    session: Session = Depends(...),
    current_user: str = Depends(...),
):
    ...
```

### Rate Limit Guidelines

Recommended rate limits by endpoint type:

- **Write operations** (POST, PUT, DELETE): 50-100 requests per minute
- **Read operations** (GET): 200-500 requests per minute
- **Health/test endpoints**: 1000 requests per minute
- **Execution/long-running operations**: 50 requests per minute

### Example: Complete Router

See `/opt/aitbc/apps/coordinator-api/src/app/routers/agent_router.py` for a complete example.

## Custom Rate Limiting

### Custom Key Function

To rate limit by something other than IP address (e.g., API key, user ID):

```python
def custom_key(request: Request) -> str:
    return request.headers.get("X-API-Key", "unknown")

@router.post("/endpoint")
@rate_limit(rate=100, per=60, key_func=custom_key)
async def endpoint(request: Request, ...):
    ...
```

### Custom Error Message

```python
@router.post("/endpoint")
@rate_limit(rate=100, per=60, error_message="Custom limit message")
async def endpoint(request: Request, ...):
    ...
```

## Global Middleware

For global rate limiting across all endpoints, use the middleware:

```python
from aitbc.rate_limiting import RateLimitMiddleware

app.add_middleware(
    RateLimitMiddleware,
    rate=100,
    per=60
)
```

## Testing

Rate limiting tests are in `/opt/aitbc/tests/test_rate_limiting.py`.

Run tests:
```bash
python3 -m pytest -c /dev/null --rootdir "$PWD" --import-mode=importlib tests/test_rate_limiting.py -v
```

## Remaining Work

There are 70+ router files across the codebase. The following routers need rate limiting applied:

### Coordinator-API (50+ routers)
- `/opt/aitbc/apps/coordinator-api/src/app/routers/*.py`
- `/opt/aitbc/apps/coordinator-api/src/app/contexts/*/routers/*.py`

### Other Services
- `/opt/aitbc/apps/agent-coordinator/src/app/routers/*.py`
- `/opt/aitbc/apps/pool-hub/src/app/routers/*.py`
- `/opt/aitbc/apps/agent-management/src/app/routers/*.py`
- `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py`
- `/opt/aitbc/apps/exchange/*.py`
- `/opt/aitbc/apps/wallet/src/app/api_rest.py`

## Priority Order

1. **High Priority**: Public-facing APIs (coordinator-api, exchange, wallet)
2. **Medium Priority**: Internal service APIs (agent-coordinator, pool-hub)
3. **Low Priority**: Admin/management APIs
