# Request ID Propagation

## Current Status

Request ID propagation is not currently implemented in the AITBC codebase. The coordinator API does not have a request ID middleware that would:

1. Generate or accept X-Request-ID headers
2. Forward X-Request-ID to outbound calls (blockchain RPC, Redis)
3. Enable distributed tracing across service boundaries

## Implementation Plan

### 1. Add Request ID Middleware

Create a middleware that:
- Generates a UUID for each incoming request if X-Request-ID header is not present
- Uses the existing X-Request-ID header if present
- Adds the request_id to the logging context
- Includes request_id in all log messages

### 2. Forward Request ID to Outbound Calls

Update outbound call sites to:
- Include X-Request-ID header in HTTP requests
- Include request_id in Redis operations
- Include request_id in blockchain RPC calls

### 3. Integration Points

Key integration points:
- Blockchain RPC calls (apps/blockchain-node)
- Redis operations (RedisStateManager)
- HTTP client calls (AITBCHTTPClient)
- External API calls (marketplace, exchange)

## Example Implementation

### Middleware

```python
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Add to request state
        request.state.request_id = request_id

        # Add to response header
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response
```

### Outbound Call Example

```python
async def make_blockchain_rpc(request_id: str, method: str, params: list):
    headers = {"X-Request-ID": request_id}
    # Make RPC call with request ID
    response = await http_client.post(
        blockchain_rpc_url,
        json={"method": method, "params": params},
        headers=headers
    )
    return response
```

## Benefits

- **Distributed Tracing**: Track requests across service boundaries
- **Debugging**: Correlate logs from multiple services for a single request
- **Performance Analysis**: Measure end-to-end latency across services
- **Error Tracking**: Follow error propagation through the system

## Priority

This is a medium-priority enhancement that should be implemented:
- After v0.5.0 release
- Before v0.6.0 release
- As part of observability depth improvements

## References

- OpenTelemetry distributed tracing
- W3C Trace Context specification
- Request ID best practices
