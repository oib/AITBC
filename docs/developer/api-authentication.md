---
title: API Authentication
description: Understanding and implementing API authentication
---

# API Authentication

All AITBC API endpoints require authentication using API keys.

## Getting API Keys

1. Visit the [AITBC Dashboard](https://dashboard.aitbc.io)
2. Create an account or sign in
3. Navigate to API Keys section
4. Generate a new API key

## Using API Keys

### HTTP Header
```http
X-API-Key: your_api_key_here
```

### Environment Variable
```bash
export AITBC_API_KEY="your_api_key_here"
```

### SDK Configuration
```python
from aitbc import AITBCClient

client = AITBCClient(api_key="your_api_key")
```

## Security Best Practices

- Never commit API keys to version control
- Use environment variables in production
- Rotate keys regularly
- Use different keys for different environments
- Monitor API key usage

## Rate Limits

API requests are rate-limited based on your plan:
- Free: 60 requests/minute
- Pro: 600 requests/minute
- Enterprise: 6000 requests/minute

## Error Handling

```python
from aitbc.exceptions import AuthenticationError

try:
    client.jobs.create({...})
except AuthenticationError:
    print("Invalid API key")
```

## Key Management

### View Your Keys
```bash
aitbc api-keys list
```

### Revoke a Key
```bash
aitbc api-keys revoke <key_id>
```

### Regenerate a Key
```bash
aitbc api-keys regenerate <key_id>
```
