# Error Codes and Handling

This document defines all error codes used by the AITBC API and how to handle them.

## Error Response Format

All API errors follow this format:

```json
{
  "detail": "Human-readable error message",
  "error_code": "ERROR_CODE",
  "request_id": "req-abc123"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `detail` | string | Human-readable description |
| `error_code` | string | Machine-readable error code |
| `request_id` | string | Request identifier for debugging |

## HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful GET, POST (update) |
| 201 | Created | Successful POST (create) |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid input |
| 401 | Unauthorized | Missing/invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Resource state conflict |
| 422 | Unprocessable Entity | Validation error |
| 429 | Too Many Requests | Rate limited |
| 500 | Internal Server Error | Server error |
| 502 | Bad Gateway | Upstream service error |
| 503 | Service Unavailable | Maintenance/overload |

## Error Codes by Category

### Authentication Errors (AUTH_*)

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `AUTH_MISSING_KEY` | 401 | No API key provided | Include `X-Api-Key` header |
| `AUTH_INVALID_KEY` | 401 | API key is invalid | Check API key is correct |
| `AUTH_EXPIRED_KEY` | 401 | API key has expired | Generate new API key |
| `AUTH_INSUFFICIENT_SCOPE` | 403 | Key lacks required permissions | Use key with correct scope |

**Example:**
```json
{
  "detail": "API key is required for this endpoint",
  "error_code": "AUTH_MISSING_KEY"
}
```

### Job Errors (JOB_*)

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `JOB_NOT_FOUND` | 404 | Job doesn't exist | Check job ID |
| `JOB_ALREADY_CLAIMED` | 409 | Job claimed by another miner | Request different job |
| `JOB_ALREADY_COMPLETED` | 409 | Job already finished | No action needed |
| `JOB_ALREADY_CANCELLED` | 409 | Job was cancelled | Submit new job |
| `JOB_EXPIRED` | 410 | Job deadline passed | Submit new job |
| `JOB_INVALID_STATUS` | 400 | Invalid status transition | Check job state |

**Example:**
```json
{
  "detail": "Job job-abc123 not found",
  "error_code": "JOB_NOT_FOUND"
}
```

### Validation Errors (VALIDATION_*)

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `VALIDATION_MISSING_FIELD` | 422 | Required field missing | Include required field |
| `VALIDATION_INVALID_TYPE` | 422 | Wrong field type | Use correct type |
| `VALIDATION_OUT_OF_RANGE` | 422 | Value outside allowed range | Use value in range |
| `VALIDATION_INVALID_FORMAT` | 422 | Wrong format (e.g., date) | Use correct format |
| `VALIDATION_PROMPT_TOO_LONG` | 422 | Prompt exceeds limit | Shorten prompt |
| `VALIDATION_INVALID_MODEL` | 422 | Model not supported | Use valid model |

**Example:**
```json
{
  "detail": "Field 'prompt' is required",
  "error_code": "VALIDATION_MISSING_FIELD",
  "field": "prompt"
}
```

### Miner Errors (MINER_*)

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `MINER_NOT_FOUND` | 404 | Miner not registered | Register miner first |
| `MINER_ALREADY_REGISTERED` | 409 | Miner ID already exists | Use different ID |
| `MINER_OFFLINE` | 503 | Miner not responding | Check miner status |
| `MINER_CAPACITY_FULL` | 503 | Miner at max capacity | Wait or use different miner |

### Receipt Errors (RECEIPT_*)

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `RECEIPT_NOT_FOUND` | 404 | Receipt doesn't exist | Check receipt ID |
| `RECEIPT_INVALID_SIGNATURE` | 400 | Signature verification failed | Check receipt integrity |
| `RECEIPT_ALREADY_CLAIMED` | 409 | Receipt already processed | No action needed |

### Rate Limit Errors (RATE_*)

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests | Wait and retry |
| `RATE_QUOTA_EXCEEDED` | 429 | Daily/monthly quota hit | Upgrade plan or wait |

**Response includes:**
```json
{
  "detail": "Rate limit exceeded. Retry after 60 seconds",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "retry_after": 60
}
```

### Payment Errors (PAYMENT_*)

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `PAYMENT_INSUFFICIENT_BALANCE` | 402 | Not enough AITBC | Top up balance |
| `PAYMENT_FAILED` | 500 | Payment processing error | Retry or contact support |

### System Errors (SYSTEM_*)

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `SYSTEM_INTERNAL_ERROR` | 500 | Unexpected server error | Retry or report bug |
| `SYSTEM_MAINTENANCE` | 503 | Scheduled maintenance | Wait for maintenance to end |
| `SYSTEM_OVERLOADED` | 503 | System at capacity | Retry with backoff |
| `SYSTEM_UPSTREAM_ERROR` | 502 | Dependency failure | Retry later |

## Error Handling Best Practices

### Retry Logic

```python
import time
import httpx

def request_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = httpx.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error = e.response.json()
            code = error.get("error_code", "")
            
            # Don't retry client errors (except rate limits)
            if e.response.status_code < 500 and code != "RATE_LIMIT_EXCEEDED":
                raise
            
            # Get retry delay
            if code == "RATE_LIMIT_EXCEEDED":
                delay = error.get("retry_after", 60)
            else:
                delay = 2 ** attempt  # Exponential backoff
            
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                raise
```

### JavaScript Error Handling

```javascript
async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  
  if (!response.ok) {
    const error = await response.json();
    
    switch (error.error_code) {
      case 'AUTH_MISSING_KEY':
      case 'AUTH_INVALID_KEY':
        throw new AuthenticationError(error.detail);
      
      case 'RATE_LIMIT_EXCEEDED':
        const retryAfter = error.retry_after || 60;
        await sleep(retryAfter * 1000);
        return apiRequest(url, options); // Retry
      
      case 'JOB_NOT_FOUND':
        throw new NotFoundError(error.detail);
      
      default:
        throw new APIError(error.detail, error.error_code);
    }
  }
  
  return response.json();
}
```

### Logging Errors

Always log the `request_id` for debugging:

```python
import logging

logger = logging.getLogger(__name__)

try:
    result = api_call()
except APIError as e:
    logger.error(
        "API error",
        extra={
            "error_code": e.error_code,
            "detail": e.detail,
            "request_id": e.request_id
        }
    )
```

## Reporting Issues

When reporting errors to support, include:
1. **Error code** and message
2. **Request ID** (from response)
3. **Timestamp** of the error
4. **Request details** (endpoint, parameters)
5. **Steps to reproduce**

## Error Code Reference Table

| Code | HTTP | Category | Retryable |
|------|------|----------|-----------|
| `AUTH_MISSING_KEY` | 401 | Auth | No |
| `AUTH_INVALID_KEY` | 401 | Auth | No |
| `AUTH_EXPIRED_KEY` | 401 | Auth | No |
| `AUTH_INSUFFICIENT_SCOPE` | 403 | Auth | No |
| `JOB_NOT_FOUND` | 404 | Job | No |
| `JOB_ALREADY_CLAIMED` | 409 | Job | No |
| `JOB_ALREADY_COMPLETED` | 409 | Job | No |
| `JOB_ALREADY_CANCELLED` | 409 | Job | No |
| `JOB_EXPIRED` | 410 | Job | No |
| `VALIDATION_MISSING_FIELD` | 422 | Validation | No |
| `VALIDATION_INVALID_TYPE` | 422 | Validation | No |
| `VALIDATION_PROMPT_TOO_LONG` | 422 | Validation | No |
| `VALIDATION_INVALID_MODEL` | 422 | Validation | No |
| `MINER_NOT_FOUND` | 404 | Miner | No |
| `MINER_OFFLINE` | 503 | Miner | Yes |
| `RECEIPT_NOT_FOUND` | 404 | Receipt | No |
| `RATE_LIMIT_EXCEEDED` | 429 | Rate | Yes |
| `RATE_QUOTA_EXCEEDED` | 429 | Rate | No |
| `PAYMENT_INSUFFICIENT_BALANCE` | 402 | Payment | No |
| `SYSTEM_INTERNAL_ERROR` | 500 | System | Yes |
| `SYSTEM_MAINTENANCE` | 503 | System | Yes |
| `SYSTEM_OVERLOADED` | 503 | System | Yes |
