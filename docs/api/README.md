# AITBC API Reference

This section provides comprehensive documentation for all AITBC platform APIs.

## Available APIs

- [Coordinator API](./coordinator/) - Job submission, management, and coordination
- [Blockchain Node API](./blockchain/) - Blockchain operations and queries
- [Wallet Daemon API](./wallet/) - Wallet operations and key management

## OpenAPI Specifications

Each API includes an OpenAPI 3.1.0 specification that can be used with API documentation tools like:
- Swagger UI
- Redoc
- Postman
- API clients

## Authentication

Most API endpoints require authentication via the `X-Api-Key` header. API keys can be obtained through the Coordinator API client registration endpoint.

## Quick Start

### Using cURL

```bash
# Submit a job
curl -X POST http://localhost:8203/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-api-key" \
  -d '{
    "payload": {"model": "llama2", "prompt": "Hello world"},
    "ttl_seconds": 900
  }'
```

### Using Python SDK

```python
import aitbc_sdk

client = aitbc_sdk.Client(api_key="your-api-key", base_url="http://localhost:8203")
job = client.submit_job(payload={"model": "llama2", "prompt": "Hello world"})
```

### Using JavaScript SDK

```javascript
import { AITBCClient } from '@aitbc/aitbc-sdk';

const client = new AITBCClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:8203'
});

const job = await client.submitJob({
  payload: { model: 'llama2', prompt: 'Hello world' }
});
```

## Rate Limiting

API endpoints may have rate limits enforced. Check the response headers for rate limit information:
- `X-RateLimit-Limit`: Maximum requests per window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when the window resets

## Error Handling

API errors follow standard HTTP status codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Too Many Requests
- `500` - Internal Server Error

Error responses include a JSON body with details:
```json
{
  "detail": "Error message describing the issue"
}
```

## WebSocket Endpoints

Real-time updates are available via WebSocket connections for:
- Job status updates
- Blockchain events
- Marketplace offers

See individual API documentation for WebSocket connection details.

## Versioning

API versions are specified in the URL path (e.g., `/v1/jobs`). Breaking changes will be introduced in new major versions. Minor versions may add new features without breaking existing functionality.
