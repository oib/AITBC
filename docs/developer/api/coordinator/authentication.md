---
title: API Authentication
description: Understanding authentication for the Coordinator API
---

# API Authentication

All Coordinator API endpoints require authentication using API keys.

## Getting Started

1. Sign up at [AITBC Dashboard](https://dashboard.aitbc.io)
2. Generate an API key
3. Include the key in your requests

## Authentication Methods

### HTTP Header (Recommended)
```http
X-API-Key: your_api_key_here
```

### Query Parameter
```http
GET /v1/jobs?api_key=your_api_key_here
```

## Example Requests

### cURL
```bash
curl -X GET https://aitbc.bubuit.net/api/v1/jobs \
  -H "X-API-Key: your_api_key_here"
```

### Python
```python
import requests

headers = {
    "X-API-Key": "your_api_key_here"
}

response = requests.get(
    "https://aitbc.bubuit.net/api/v1/jobs",
    headers=headers
)
```

### JavaScript
```javascript
const headers = {
    "X-API-Key": "your_api_key_here"
};

fetch("https://aitbc.bubuit.net/api/v1/jobs", {
    headers: headers
})
.then(response => response.json())
.then(data => console.log(data));
```

## Security Best Practices

- Never expose API keys in client-side code
- Use environment variables in production
- Rotate keys regularly
- Monitor API usage
- Use HTTPS for all requests

## Rate Limits

API requests are rate-limited based on your plan:
- Free: 60 requests/minute
- Pro: 600 requests/minute
- Enterprise: 6000 requests/minute

Rate limit headers are included in responses:
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1640995200
```

## Error Handling

```json
{
  "error": {
    "code": "INVALID_API_KEY",
    "message": "The provided API key is invalid"
  }
}
```

## Key Management

### View Your Keys
Visit the [Dashboard](https://dashboard.aitbc.io/api-keys)

### Revoke a Key
```bash
curl -X DELETE https://aitbc.bubuit.net/api/v1/api-keys/{key_id} \
  -H "X-API-Key: your_master_key"
```

### Regenerate a Key
```bash
curl -X POST https://aitbc.bubuit.net/api/v1/api-keys/{key_id}/regenerate \
  -H "X-API-Key: your_master_key"
```
