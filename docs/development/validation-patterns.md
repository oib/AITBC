# Request Validation Patterns

## Overview

This document describes the request validation patterns and middleware for AITBC services.

## Middleware Stack

The coordinator-api uses the following middleware stack (in order of execution):

1. **CORSMiddleware** - CORS handling
2. **RequestIDMiddleware** - Request ID correlation
3. **PerformanceLoggingMiddleware** - Performance tracking
4. **RequestValidationMiddleware** - Request/response size validation
5. **ErrorHandlerMiddleware** - Standardized error responses

## Request Validation Middleware

### Purpose

Validates incoming and outgoing requests/responses to ensure they meet size limits and other constraints.

### Configuration

```python
app.add_middleware(
    RequestValidationMiddleware,
    max_request_size=10*1024*1024,  # 10MB
)
```

### Validation Rules

- **Request size**: Maximum 10MB by default
- **Response size**: Maximum 10MB by default
- **Content-Length header**: Must be valid integer if present

### Error Responses

If validation fails, returns HTTP 413 (Payload Too Large):

```json
{
  "detail": "Request too large. Maximum size is 10485760 bytes"
}
```

## Error Handler Middleware

### Purpose

Standardizes error responses across all endpoints with consistent format and logging.

### Error Response Format

All errors are returned in the following format:

```json
{
  "error": {
    "type": "http_error | internal_error",
    "message": "Error description",
    "status_code": 400 | 500,
    "path": "/api/endpoint"
  }
}
```

### Error Types

- **http_error**: HTTP exceptions (4xx errors)
- **internal_error**: Unhandled exceptions (5xx errors)

### Logging

All errors are logged with context:
- HTTP exceptions: WARNING level
- Internal exceptions: ERROR level with stack trace

## Request ID Correlation

### Purpose

Adds a unique request ID to each request for correlation across distributed systems.

### Implementation

- Generates or retrieves request ID from `X-Request-ID` header
- Binds request ID to logger context
- Adds request ID to response headers
- Logs request start and completion

### Usage

```python
request_id = request.state.request_id
logger = logger.bind(request_id=request_id)
```

## Performance Logging

### Purpose

Tracks request timing and performance metrics.

### Implementation

- Logs request duration in milliseconds
- Adds `X-Process-Time` header to responses
- Logs method, path, and status code

### Response Header

```
X-Process-Time: 0.123
```

## Validation Guidelines

### DO

- Use Pydantic models for request body validation
- Set appropriate size limits for your use case
- Log validation failures with context
- Return standardized error responses
- Include request ID in error logs

### DON'T

- Disable validation in production
- Allow unbounded request sizes
- Return raw exceptions to clients
- Log sensitive information in error messages
- Skip error logging

## Example: Adding Custom Validation

```python
from fastapi import Request, HTTPException
from pydantic import BaseModel, Field, validator

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    
    @validator('username')
    def validate_username(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v

@router.post("/users")
async def create_user(request: CreateUserRequest):
    # Request is automatically validated by FastAPI
    return {"status": "created", "username": request.username}
```

## Rate Limiting

Rate limiting is already implemented using slowapi:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/endpoint")
@limiter.limit("10/minute")
async def endpoint(request: Request):
    return {"status": "ok"}
```

## Configuration

Middleware can be configured in `main.py`:

```python
# Request validation
app.add_middleware(
    RequestValidationMiddleware,
    max_request_size=10*1024*1024,  # 10MB
    max_response_size=10*1024*1024,  # 10MB
)

# Error handling
app.add_middleware(ErrorHandlerMiddleware)
```

## Testing

Test validation middleware:

```python
from fastapi.testclient import TestClient

client = TestClient(app)

# Test request size validation
response = client.post(
    "/endpoint",
    data="x" * 11 * 1024 * 1024,  # 11MB
)
assert response.status_code == 413

# Test error handling
response = client.get("/nonexistent")
assert response.status_code == 404
assert "error" in response.json()
```

## Security Considerations

- Request size limits prevent DoS attacks
- Response size limits prevent memory exhaustion
- Error responses don't leak sensitive information
- Request IDs enable security audit trails
- All validation failures are logged for monitoring
